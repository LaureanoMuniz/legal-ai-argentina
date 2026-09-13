# Phases 6 and 7: Reranking and Query Rewriting (executed inline)

Both phases were executed directly from the debug findings of 2026-09-13
rather than from a written plan; this file records what was built and how it
was measured so the trail stays complete.

**Phase 6.** `retrieval/rerank.py` (`Reranker` protocol, `BgeReranker`,
`OverlapReranker` for tests, `rerank()`), `Retriever(reranker, pool)`, CLI
`--rerank --pool`, settings `reranker_model`, `rerank_pool`. Measured with
`bench run` at pools 20/30/50 over vector and hybrid; ADR-023.

**Phase 7.** `retrieval/rewrite.py` (`Rewrite` schema, `ClaudeRewriter` with
disk cache and token accounting), `Retriever(rewriter, multi_query)`, CLI
`--rewrite --multi`, settings `rewrite_model`, `rewrite_multi_query`. Measured
with Opus 5 and Sonnet 5, with and without multi-query and reranking; ADR-024.
Pointer/quoted-article chunk split (`chunking.split_quoted`) measured in the
same round.

Results and per-question readings: `docs/ROADMAP.md` (Fase 6 y 7 en detalle).
