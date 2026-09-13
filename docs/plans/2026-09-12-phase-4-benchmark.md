# Phase 4: Retrieval Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reproducible retrieval benchmark of 50 questions in 8 categories over the laboral corpus, scored with recall@k, precision@k, MRR, nDCG@k and hit@k at article level, aggregated per category, run for hashing and bge-m3 and recorded in `experiments/`.

**Architecture:** `eval/benchmark.jsonl` holds one question per line with `expected_articles` (article ids from Phase 2), a category and, for temporal questions, an `as_of` date the baseline does not yet honour. `legal_ai.eval.metrics` has pure ranking functions over article-id lists. `legal_ai.eval.benchmark` loads questions, runs the `Retriever`, dedupes chunks to articles preserving rank, scores each question and aggregates overall and per category. `not_in_corpus` questions are loaded and timed but not scored: abstention is a generation metric (Phase 8). The CLI is `legal-ai bench run`.

**Tech Stack:** Python 3.12, Pydantic, existing `Retriever` and Postgres index from Phase 3, pytest.

**Spec:** `docs/ARCHITECTURE.md` (*Evaluación → Retrieval*), `docs/ROADMAP.md` (Fase 4, "Notas para fases futuras"), `docs/DECISIONS.md` (ADR-014 on recall first).

## Global Constraints

- Every `expected_articles` id must exist in the `articles` table; verify with a query before committing the file.
- Expected articles are best-effort by the engineer, checked against the article texts in the database, and labelled as pending lawyer review in ADR-021. They are not legal advice.
- `k` is the number of chunks retrieved; metrics are computed over the deduplicated article list. Duplicated chunks of the same article therefore cost recall, on purpose.
- Derogated and temporal questions are scored like the others: the baseline is expected to fail them, and the per-category table makes that visible instead of hiding it.
- No invented numbers: every figure in docs comes from `experiments/*.json`.

## File Structure

```
eval/benchmark.jsonl                 50 questions, 8 categories
src/legal_ai/eval/__init__.py
src/legal_ai/eval/metrics.py         dedupe_ordered, recall_at_k, precision_at_k, reciprocal_rank, ndcg_at_k, hit_at_k
src/legal_ai/eval/benchmark.py       Question, QuestionScore, Aggregate, BenchmarkReport, load_questions, score_question, aggregate, run_benchmark, write_report
src/legal_ai/cli.py                  bench run
tests/eval/test_metrics.py
tests/eval/test_benchmark.py         well-formedness of the repo file + runner on the mini corpus
```

---

### Task 1: Questions grounded in the parsed corpus

- [x] Query `articles` and `article_versions` for the LCT (headings, status, modifying law) and for Leyes 24.013, 25.323, 25.877, 26.844, 26.727, 27.742, 27.802 to pick ids.
- [x] Write `eval/benchmark.jsonl`: 8 direct, 7 multi_article, 6 negation, 6 confusable, 5 derogated, 6 temporal (`as_of`), 6 not_in_corpus (empty expected), 6 cross_reference.
- [x] Verify every expected id exists in `articles` and list which have no chunk (the derogated ones).

### Task 2: Metrics and runner

- [x] `metrics.py` with pure functions and `tests/eval/test_metrics.py` (perfect, partial and empty cases for each metric).
- [x] `benchmark.py`: `run_benchmark(retriever, questions_path, k, name, embedding_model, catalog_date) -> BenchmarkReport`; `write_report(report, experiments_dir) -> Path`.
- [x] `tests/eval/test_benchmark.py`: the repo file has 50 unique ids and the 8 categories; unscored questions have `None` metrics; the runner aggregates by category on the mini corpus.
- [x] CLI `bench run [--k 8] [--model] [--name] [--questions]` printing an overall + per-category table and the misses.

### Task 3: Real run and docs

- [ ] `legal-ai bench run --model hashing --name phase4-hashing` and `legal-ai bench run --name phase4-bgem3`.
- [ ] `docs/ROADMAP.md`: Fase 4 hecha, Fase 5 siguiente, "Fase 4 en detalle" with the per-category table from the two JSON files and the misses worth acting on.
- [ ] `docs/DECISIONS.md`: ADR-021 (benchmark design: categories, article-level scoring, expected articles pending lawyer review, derogated/temporal scored as honest failures).
- [ ] `docs/ARCHITECTURE.md` *Evaluación*: point to `eval/benchmark.jsonl` and `bench run`.
- [ ] `cuaderno/index.html`: Lección 4 with quiz; republish the artifact.
- [ ] Commit, merge to main, push.
