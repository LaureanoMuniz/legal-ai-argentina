# Phase 5: BM25 and Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BM25 retrieval (ParadeDB `pg_search`, Spanish stemmer) over the same chunks, fuse it with the vector list by Reciprocal Rank Fusion written in Python, optionally deduplicate by article, and measure vector vs BM25 vs hybrid on the Phase 4 benchmark.

**Architecture:** Migration 0002 creates `chunks_bm25` on `embed_text`. `retrieval/bm25.py` is one SQL statement using `paradedb.match(..., conjunction_mode => false)` and `paradedb.score(id)`. `retrieval/fusion.py` has `rrf(lists, k, rrf_k=60)` and `dedupe_by_article(candidates, k)`. `Retriever` gains `mode` (`vector | bm25 | hybrid`) and `dedupe` (pool `3k`, cut to `k` distinct articles). `Settings.retrieval_mode` and `retrieval_dedupe` set the default; CLI flags override per run. Spans are named `retrieval.<mode>`.

**Tech Stack:** pg_search 0.25.9, pgvector 0.8.4, SQLAlchemy Core, Alembic, pytest.

**Spec:** `docs/ARCHITECTURE.md` (*Retrieval*: bm25, híbrido), `docs/ROADMAP.md` (Fase 5), ADR-002, ADR-021.

## Global Constraints

- Same benchmark, same `k = 8`, same index and catalog as Phase 4, so numbers are comparable.
- RRF is explicit Python, not a database extension feature, so the fusion can be read and changed.
- The default retrieval mode changes only after the benchmark says which wins, and the change is recorded in an ADR.

## Tasks

- [x] Probe `pg_search` syntax on the live database before writing the migration (index creation, `paradedb.match`, `paradedb.score`).
- [x] Migration `0002_bm25_index.py`; `retrieval/bm25.py`; `retrieval/fusion.py`; `Retriever(mode, dedupe)`; `parse_mode`; settings; CLI `--retriever`, `--dedupe` on `search`, `ask`, `bench run`; `BenchmarkReport.retriever`.
- [x] Tests: RRF ordering, tie determinism, dedupe, mode parsing, BM25 and hybrid on the mini corpus, empty BM25 result.
- [x] `legal-ai db upgrade`; `bench run` for `bm25`, `hybrid`, `vector --dedupe`, `hybrid --dedupe` with bge-m3.
- [x] ADR-022 (BM25 + RRF, pool factor, what the benchmark said); ROADMAP Fase 5 table; ARCHITECTURE retrieval section; README commands; Lesson 5 + quiz; set the default `retrieval_mode` to the winner.
- [ ] Commit, push, republish the cuaderno.
