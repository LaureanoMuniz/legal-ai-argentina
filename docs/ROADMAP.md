# Roadmap

Cada fase termina con: código + tests + (cuando aplica) un experimento en
`experiments/` + una decisión en `DECISIONS.md`. No se avanza a la siguiente
sin medir la actual.

| Fase | Qué | Métrica / entregable | Estado |
|---|---|---|---|
| 0 | Arquitectura, docs, repo | README, ARCHITECTURE, ROADMAP, DECISIONS | hecha |
| 1 | Ingestion reproducible desde Infoleg | `data/raw` completo para el corpus laboral, manifest, tests del fetcher | hecha |
| 2 | Parser con estructura jurídica | `documents/articles/relations.jsonl`, versiones original/current, tests con fixtures reales | siguiente |
| 3 | RAG baseline: vector → top-k → Claude → respuesta con fuentes | Postgres + pgvector, FastAPI, OTel → Langfuse, latencia baseline | |
| 4 | Benchmark de ~50 preguntas en 8 categorías | `eval/benchmark.jsonl`, recall@k / MRR / nDCG del baseline | |
| 5 | BM25 (`pg_search`) e híbrido con RRF | vector vs BM25 vs híbrido, mismo benchmark | |
| 6 | Reranking (bge-reranker local vs Cohere) | ganancia por categoría, latencia y costo; cuándo empeora | |
| 7 | Query expansion / decomposition, contextual retrieval | query original vs expandida | |
| 8 | Generación fundamentada: claims + fuentes + abstención | % claims soportados, abstención correcta | |
| 9 | Retrieval temporal: reconstrucción de versiones, filtro por fecha | tests explícitos de Temporal Misgrounding (versión vigente vs histórica) | |
| 10 | Knowledge graph legal (Postgres → Neo4j si hace falta) | casos donde el vector falla por depender de relaciones | |
| 11 | GraphRAG como segundo camino | vector vs híbrido vs grafo vs híbrido+grafo en preguntas multi-hop | |
| 12 | Agente con tools explícitas (Pydantic AI) | decisiones trazadas; comparación contra pipeline fijo | |
| 13 | Observabilidad completa | trazas por request con candidatos, scores, contexto y citas | |
| 14 | Evaluación humana (abogados) | interfaz de etiquetado, dataset, regresiones | |
| 15 | MCP server | `search_laws`, `get_article`, `get_law_version`, `find_related_legislation` | |

## Fase 1 en detalle

1. Descargar los tres ZIP de datos.jus.gob.ar a `data/raw/infoleg/catalog/<fecha>/` con hash y manifest.
2. Cargar el CSV principal y resolver `corpus/laboral.yaml` a `id_norma`s (seeds + modificatorias a profundidad 1).
3. Descargar `norma.htm`, `texact.htm` y las dos páginas de vínculos por norma, con User-Agent de navegador, reintentos, rate limit y caché en disco.
4. CLI `legal-ai ingest catalog|resolve|fetch`.
5. Tests: parsing del CSV, resolución del manifest, fetcher con respuestas grabadas (sin red en CI).

Resultado (catálogo 2026-09-12): 266 normas resueltas (6 seeds + 260
modificatorias: 189 decretos, 77 leyes). 834 archivos HTML descargados, todos
HTTP 200, 0 fallos. 249 normas con texto original, 53 con texto actualizado,
17 sin ningún link de texto en el catálogo. 89 MB en `data/raw/infoleg`.

## Problemas que esperamos encontrar (y medir)

- **Temporal Misgrounding**: preguntar por 2021 y recibir el texto de 2026.
- **Confusión entre normas similares**: LCT vs. Ley de Empleo en preguntas de registración.
- **Artículos derogados** que siguen apareciendo como evidencia.
- **Referencias cruzadas** ("conforme al artículo 245") que el vector no sigue.
- **Preguntas sin respuesta en el corpus** donde el LLM contesta con conocimiento general.
