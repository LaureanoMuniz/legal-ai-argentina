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
- Las 925 normas que Infoleg vincula como modificatorias o complementarias
  de esas leyes: resoluciones (topes indemnizatorios, salario mínimo,
  registración), decretos y otras leyes. Se incluyen todos los tipos; filtrar
  es una decisión que se toma con el benchmark, no antes (ADR-014).

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
├── cuaderno/            páginas HTML de aprendizaje por fase (con cuestionarios)
├── docs/                ARCHITECTURE, ROADMAP, DECISIONS (ADRs), planes por fase
├── eval/                benchmark de preguntas y resultados de evaluación humana
├── experiments/         un JSON por experimento: config, métricas, fecha
├── migrations/          Alembic
├── src/legal_ai/
│   ├── ingest/          catálogo Infoleg, manifest, descarga con caché
│   ├── parse/           HTML → documentos y artículos con metadata jurídica
│   ├── db/              esquema SQLAlchemy, engine, migraciones
│   ├── index/           carga en Postgres, chunks, embeddings
│   ├── retrieval/       vector, BM25 (pg_search), fusión híbrida (reranking en Fase 6)
│   ├── generation/      prompt, structured output, validación de fuentes
│   ├── observability/   OpenTelemetry → JSONL / OTLP
│   ├── api/             FastAPI
│   ├── pipeline.py      pregunta → retrieval → contexto → Claude, con spans
│   ├── eval/            métricas de ranking y runner del benchmark
│   └── bench.py         benchmark de humo → experiments/
└── tests/
```

## Cómo ejecutar

Requisitos: `uv`, y un runtime de contenedores con Docker Compose (en macOS,
Colima: `brew install colima docker docker-compose && colima start`).

```bash
uv sync                      # dependencias; agregar --extra embeddings para bge-m3 (torch)
docker compose up -d         # Postgres 17 con pgvector + pg_search, en el puerto 5433
cp .env.example .env         # ANTHROPIC_API_KEY sólo si querés generación con Claude

uv run legal-ai ingest catalog        # descarga la base de Infoleg a data/raw
uv run legal-ai ingest fetch laboral  # descarga las normas del manifest
uv run legal-ai parse laboral         # HTML → documents/articles/versions/relations/history .jsonl

uv run legal-ai db upgrade            # crea la base y aplica migraciones
uv run legal-ai index load laboral    # JSONL → Postgres
uv run legal-ai index chunk laboral   # una versión vigente por artículo, con prefijo de contexto
uv run legal-ai index embed laboral   # bge-m3 (o --model hashing, sin descarga)

uv run legal-ai search "¿Cuánto dura el período de prueba?"   # retrieval (--retriever vector|bm25|rrf|hybrid, --rewrite, --rerank --pool N)
uv run legal-ai ask "¿Cuánto dura el período de prueba?"      # retrieval + Claude con citas
uv run legal-ai serve                                          # UI en http://127.0.0.1:8000 + API (/ask, /ask/stream, /trace, /feedback)
uv run legal-ai bench smoke --no-generate                      # 20 preguntas de humo → experiments/
uv run legal-ai bench run --retriever hybrid                   # benchmark de retrieval: 50 preguntas, métricas por categoría
uv run legal-ai bench generate                                 # generación + juez: abstención, afirmaciones sostenidas, costo
uv run legal-ai bench agent --limit 20                         # agente con herramientas, mismas preguntas y juez
uv run legal-ai traces                                         # resumen de los spans: latencia por etapa, tokens, costo
uv run legal-ai mcp                                            # servidor MCP por stdio para Claude Desktop / Claude Code

uv run pytest                # los tests de base saltan si Postgres no está levantado
```

Cada `ask` deja sus spans en `data/traces/spans.jsonl`; la respuesta trae el
`trace_id` para buscarlos.

## Estado

Las 15 fases del plan están construidas y medidas sobre el corpus laboral:
ingestion, parser con versiones, índice en Postgres, benchmark de 50
preguntas, BM25 e híbrido, reranker, reescritura de la pregunta con Claude,
generación con citas medida por un juez, retrieval temporal con versiones
reconstruidas, grafo de referencias, agente con herramientas, observabilidad,
interfaz de preguntas con feedback y servidor MCP. Los números de cada fase,
con su fecha y su archivo en `experiments/`, están en `docs/ROADMAP.md`; las
decisiones en `docs/DECISIONS.md`; lo que salió mal y cómo se arregló en
`docs/BITACORA.md`.

Números finales sobre 50 preguntas (detalle y archivos en el roadmap):
retrieval hit@8 0,91 y nDCG@8 0,76 (desde 0,77 / 0,60 en la Fase 3), las 6
preguntas con fecha con la versión correcta, negación 1,00 de hit tras la
descomposición de consultas, generación con 0,96 de afirmaciones sostenidas
por sus fuentes según un juez, 0 citas inventadas y abstención en las 6
preguntas sin respuesta en el corpus.

Lo que falta es lo que no se puede hacer sin gente: etiquetas de abogados
sobre las respuestas (la interfaz ya las guarda) y un benchmark revisado por
ellos.

## La interfaz

`uv run legal-ai serve` y abrir http://127.0.0.1:8000. A la izquierda hay un
catálogo de preguntas para probar; cada respuesta muestra las afirmaciones con
sus fuentes (clic para leer el artículo con todas sus versiones), botones para
calificarla, y un panel "por debajo del capó" con lo que pasó en esa request:
cómo se reescribió la pregunta, qué fecha se interpretó, qué fragmentos se
recuperaron y por qué camino, cuánto tardó cada etapa, tokens y costo, y los
spans crudos. Necesita Postgres levantado y `ANTHROPIC_API_KEY` en `.env`.

## Cuaderno

`cuaderno/` tiene páginas HTML de aprendizaje, una por etapa: qué se
construyó, qué problema real apareció, qué hace la industria con ese problema
y un cuestionario para autoevaluarse. Se abren directo en el navegador.
