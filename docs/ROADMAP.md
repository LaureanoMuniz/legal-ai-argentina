# Roadmap

Cada fase termina con: código + tests + (cuando aplica) un experimento en
`experiments/` + una decisión en `DECISIONS.md`. No se avanza a la siguiente
sin medir la actual.

| Fase | Qué | Métrica / entregable | Estado |
|---|---|---|---|
| 0 | Arquitectura, docs, repo | README, ARCHITECTURE, ROADMAP, DECISIONS | hecha |
| 1 | Ingestion reproducible desde Infoleg | `data/raw` completo para el corpus laboral, manifest, tests del fetcher | hecha |
| 2 | Parser con estructura jurídica | `documents/articles/relations.jsonl`, versiones original/current, tests con fixtures reales | hecha |
| 3 | RAG baseline: vector → top-k → Claude → respuesta con fuentes | Postgres + pgvector, FastAPI, OTel → Langfuse, latencia baseline | siguiente |
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

Resultado (catálogo 2026-09-12, tras ADR-014): 931 normas resueltas (6 seeds
+ 925 modificatorias: 630 resoluciones, 189 decretos, 77 leyes, 29 otras).
2.748 archivos HTML descargados, todos HTTP 200, 0 fallos. 751 normas con
texto original, 135 con texto actualizado, 180 sin ningún link de texto en el
catálogo. 112 MB en `data/raw/infoleg`.

## Fase 2 en detalle

Resultado (`legal-ai parse laboral`, catálogo 2026-09-12): 933 documentos,
751 con texto. 11.322 artículos (8.945 principales, 2.377 en anexos), 15.327
versiones (10.641 `original`, 4.686 `current`, 189 derogadas), 13.136
relaciones (13.074 de las páginas de vínculos, 62 de notas), 321 eventos de
historial. 893 advertencias en 101 documentos. LCT: 293 artículos, 16
derogados, 75 sustituidos, 1 advertencia (nota de Capítulo VIII colgada del
art. 89). Parsear todo tarda unos 3 segundos.

Seguimientos:

- Anexos de resoluciones que Infoleg reescribe entero: 557 artículos con texto
  distinto y sin nota fechada (similitud < 0,9). La nota está a nivel anexo
  ("Anexo sustituido por Res. X"); modelar notas de anexo.
- Decreto 27/2018 (305736): el texto actualizado no tiene encabezados de
  artículo (192 "faltan en actual"). Revisar el HTML.
- 14 normas con texto y sin artículos numerados (comunicaciones BCRA,
  circulares, decretos de promulgación): decidir en Fase 3 si se indexan como
  un solo chunk.
- Epígrafes partidos en dos líneas ("Formas de pago. Prestaciones" /
  "complementarias.") y números con espacio ("ARTICULO 3 1"): casos aislados.
- 194 relaciones de notas sin resolver a un `id_norma` (la norma
  modificatoria no está en el corpus).

## Problemas que esperamos encontrar (y medir)

- **Temporal Misgrounding**: preguntar por 2021 y recibir el texto de 2026.
- **Confusión entre normas similares**: LCT vs. Ley de Empleo en preguntas de registración.
- **Artículos derogados** que siguen apareciendo como evidencia.
- **Referencias cruzadas** ("conforme al artículo 245") que el vector no sigue.
- **Preguntas sin respuesta en el corpus** donde el LLM contesta con conocimiento general.

## Notas para fases futuras

- **Fase 4, benchmark**: incluir "¿cuál es el tope indemnizatorio vigente para
  el convenio de comercio?" en la categoría "la respuesta no está en el corpus".
  La regla (art. 245 LCT) está; el monto vive en resoluciones que el manifest
  filtra. Debe medir abstención, no invención.
- **Manifest laboral**: el filtro `tipos: [Ley, Decreto]` se quitó (ADR-014);
  el corpus pasó de 266 a 931 normas. Medir en la Fase 5 si filtrar por tipo
  en la consulta mejora o empeora el retrieval.
- **Fase 2, modelo de documentos**: el catálogo tiene 4.489 `id_norma`
  repetidos. Son resoluciones conjuntas: una fila por organismo firmante, cada
  una con su propio `numero_norma`. En el corpus laboral hay 17. El resolver
  hoy se queda con la última fila; `documents` debe guardar la lista de
  (organismo, número) en vez de un solo par.
