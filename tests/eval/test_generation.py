import json
from pathlib import Path

from legal_ai.eval.generation import aggregate, run_generation_benchmark, write_report
from legal_ai.eval.judge import ClaimVerdict, ClaudeJudge, Judgement, build_judge_message
from legal_ai.generation.schema import Claim, GroundedAnswer
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.generation.test_claude import make_client
from tests.test_pipeline_api import indexed


class ScriptedGenerator:
    def __init__(self, answers):
        self.answers = answers
        self.model = "fake"

    def generate(self, question, candidates):
        from legal_ai.generation.claude import Generation, Usage

        answer = self.answers.pop(0)
        known = {c.version_id for c in candidates}
        unsupported = sorted({s for c in answer.claims for s in c.sources if s not in known})
        return Generation(
            answer=answer,
            usage=Usage(input_tokens=1000, output_tokens=100),
            model="fake",
            stop_reason="end_turn",
            unsupported_sources=unsupported,
        )


class FakeJudge:
    model = "claude-sonnet-5"
    input_tokens = 500
    output_tokens = 50

    def judge(self, question, answer, candidates):
        return Judgement(
            verdicts=[
                ClaimVerdict(index=i + 1, verdict="supported" if i == 0 else "partial", reason="ok")
                for i in range(len(answer.claims))
            ],
            answers_question=True,
        )


def test_judge_message_lists_claims_with_cited_fragments():
    from legal_ai.retrieval.types import Candidate

    cand = Candidate(
        chunk_id="a#0",
        version_id="25552:92bis@current",
        article_id="25552:92bis",
        document_id=25552,
        score=1,
        rank=1,
        retriever="v",
        context_prefix="Ley 20744 · Art. 92 bis",
        text="seis meses",
    )
    answer = GroundedAnswer(
        answer="x",
        claims=[Claim(claim="Dura seis meses", sources=["25552:92bis@current", "zzz"])],
        confidence="high",
        insufficient_evidence=False,
    )
    msg = build_judge_message("¿cuánto?", answer, [cand])
    assert (
        "AFIRMACIÓN 1: Dura seis meses" in msg
        and "seis meses" in msg
        and "no presente en el contexto" in msg
    )


def test_claude_judge_parses_and_counts_tokens():
    parsed = Judgement(
        verdicts=[ClaimVerdict(index=1, verdict="supported", reason="r")], answers_question=True
    )
    client, messages = make_client(parsed)
    judge = ClaudeJudge(client, "claude-sonnet-5")
    answer = GroundedAnswer(
        answer="x",
        claims=[Claim(claim="c", sources=[])],
        confidence="low",
        insufficient_evidence=False,
    )
    out = judge.judge("q", answer, [])
    assert (
        out.verdicts[0].verdict == "supported" and judge.calls == 1 and judge.input_tokens == 1200
    )
    assert messages.calls[0]["output_format"] is Judgement
    empty = judge.judge(
        "q", GroundedAnswer(answer="", claims=[], confidence="low", insufficient_evidence=True), []
    )
    assert empty.verdicts == [] and judge.calls == 1


def test_generation_benchmark_measures_abstention_support_and_cost(db, tmp_path: Path):
    indexed(db, tmp_path)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "a",
                "category": "direct",
                "question": "período de prueba seis meses",
                "expected_articles": ["25552:92bis"],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "b",
                "category": "not_in_corpus",
                "question": "tope comercio",
                "expected_articles": [],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "c",
                "category": "direct",
                "question": "período de prueba",
                "expected_articles": ["25552:92bis"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    answers = [
        GroundedAnswer(
            answer="Seis meses [25552:92bis@current].",
            claims=[
                Claim(claim="Dura seis meses.", sources=["25552:92bis@current"]),
                Claim(claim="Otra cosa.", sources=["25552:92bis@current"]),
            ],
            confidence="high",
            insufficient_evidence=False,
        ),
        GroundedAnswer(answer="", claims=[], confidence="low", insufficient_evidence=True),
        GroundedAnswer(answer="", claims=[], confidence="low", insufficient_evidence=True),
    ]
    pipeline = Pipeline(
        Retriever(db, HashingEmbedder()),
        ScriptedGenerator(answers),
        setup_tracing("t", None, tmp_path / "s.jsonl"),
    )
    report = run_generation_benchmark(
        pipeline,
        FakeJudge(),
        questions,
        k=5,
        name="t",
        catalog_date="2026-09-12",
        llm_model="claude-opus-5",
    )
    assert report.n == 3 and report.overall.answered == 1 and report.overall.abstained == 2
    assert (
        report.overall.claims == 2
        and report.overall.claim_support_rate == 0.5
        and report.overall.claim_partial_rate == 0.5
    )
    assert report.not_in_corpus_abstention == 1.0
    assert report.answerable_false_abstention == 0.5
    assert report.overall.cited_expected_rate == 1.0 and report.unsupported_source_citations == 0
    assert report.estimated_cost_usd > 0 and report.judge_input_tokens == 500
    path = write_report(report, tmp_path / "exp")
    assert path.exists()
    assert aggregate([]).claim_support_rate is None
