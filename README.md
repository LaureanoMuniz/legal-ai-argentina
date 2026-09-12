# Legal AI Argentina

Sistema de respuesta a preguntas sobre legislación argentina real, construido
como laboratorio de AI Engineering: desde un RAG simple hasta retrieval
temporal, knowledge graph, agentes y MCP, con evaluación humana de abogados
en cada etapa.

> **Esto no es asesoramiento jurídico.** Es un proyecto de ingeniería para
> estudiar cómo fallan y cómo se miden los sistemas de recuperación y
> generación sobre textos legales. Ninguna respuesta del sistema debe usarse
> para tomar decisiones legales.

## Objetivo

Aprender, con datos reales y métricas, el ciclo completo:

```
pregunta → retrieval → ranking → contexto → LLM → respuesta → evidencia → evaluación
```

y descubrir los problemas reales de cada etapa antes de taparlos con una
librería. Cada decisión de diseño que genere un problema interesante se hace
explícita y se mide.

## Corpus

Derecho laboral argentino, desde fuentes oficiales:

- **Ley 20.744** (Ley de Contrato de Trabajo, texto ordenado por Decreto
  390/76): ~290 artículos, decenas de artículos sustituidos, derogados e
  incorporados por leyes posteriores (24.013, 25.323, 25.877, 27.742, 27.802,
  entre otras).
- Las leyes que la modifican y complementan, resueltas desde la base de
  Infoleg.

Fuente: [Infoleg](https://www.infoleg.gob.ar) vía el dataset abierto del
Ministerio de Justicia en
[datos.jus.gob.ar](https://datos.jus.gob.ar/dataset/base-de-datos-legislativos-infoleg)
(CC BY 4.0, actualización mensual). Los textos originales nunca se editan a
mano: `data/raw/` es inmutable y `data/processed/` se regenera con scripts.

## Arquitectura (resumen)

| Capa | Herramienta |
|---|---|
| Lenguaje | Python 3.12, `uv`, `ruff`, `pyright`, `pytest` |
| Base de datos | PostgreSQL 17 + pgvector (HNSW) + ParadeDB `pg_search` (BM25) |
| Acceso a datos | SQLAlchemy 2.0 Core + Alembic + psycopg 3 |
| Embeddings | `bge-m3` local (baseline) y Voyage vía API (comparación) |
| Reranking | `bge-reranker-v2-m3` local y Cohere Rerank vía API (comparación) |
| LLM | Claude Opus 5 con structured outputs |
| API | FastAPI (async, SSE) |
| Observabilidad | OpenTelemetry (GenAI semantic conventions) → Langfuse self-hosted |
| Evaluación | Métricas propias de retrieval + juez LLM propio; Ragas/DeepEval como contraste |
| Agentes | Pydantic AI (Fase 12) |
| Infra local | Docker Compose |

Detalle en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Decisiones y
alternativas descartadas en [docs/DECISIONS.md](docs/DECISIONS.md). Fases y
estado en [docs/ROADMAP.md](docs/ROADMAP.md).

## Estructura del repositorio

```
legal-ai/
├── corpus/              manifests de corpus (qué normas entran y por qué)
├── data/
│   ├── raw/             descargas inmutables (CSV de Infoleg, HTML de normas)
│   └── processed/       salida reproducible de los scripts de parsing
├── docs/                ARCHITECTURE, ROADMAP, DECISIONS (ADRs)
├── eval/                benchmark de preguntas y resultados de evaluación humana
├── experiments/         un JSON por experimento: config, métricas, fecha
├── migrations/          Alembic
├── src/legal_ai/
│   ├── ingest/          catálogo Infoleg, manifest, descarga con caché
│   ├── parse/           HTML → documentos y artículos con metadata jurídica
│   ├── index/           embeddings, carga en Postgres
│   ├── retrieval/       vector, BM25, híbrido, reranking, expansión
│   ├── generation/      prompts, structured outputs, citas
│   ├── eval/            métricas, runner de benchmark
│   ├── observability/   instrumentación OTel
│   └── api/             FastAPI
└── tests/
```

## Cómo ejecutar

Requisitos: Docker Desktop, `uv`.

```bash
uv sync                      # instala dependencias en .venv
docker compose up -d         # Postgres (pgvector + pg_search), Langfuse
cp .env.example .env         # completar claves cuando haga falta
uv run legal-ai ingest catalog        # descarga la base de Infoleg a data/raw
uv run legal-ai ingest fetch laboral  # descarga las normas del manifest
uv run legal-ai parse laboral         # genera data/processed
uv run pytest
```

Los comandos que todavía no existen están marcados en el roadmap.

## Estado

Fases 0 (arquitectura) y 1 (ingestion) completas. Fase 2 (parser) es la siguiente.

Hay un cuaderno de aprendizaje por fase en `docs/cuaderno/` (se publica como
página HTML): qué se construyó, qué problema real apareció y qué hace la
industria con ese problema.
