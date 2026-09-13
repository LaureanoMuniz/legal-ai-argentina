# Roadmap

Cada fase termina con: código + tests + (cuando aplica) un experimento en
`experiments/` + una decisión en `DECISIONS.md`. No se avanza a la siguiente
sin medir la actual.

| Fase | Qué | Métrica / entregable | Estado |
|---|---|---|---|
| 0 | Arquitectura, docs, repo | README, ARCHITECTURE, ROADMAP, DECISIONS | hecha |
| 1 | Ingestion reproducible desde Infoleg | `data/raw` completo para el corpus laboral, manifest, tests del fetcher | hecha |
| 2 | Parser con estructura jurídica | `documents/articles/relations.jsonl`, versiones original/current, tests con fixtures reales | hecha |
| 3 | RAG baseline: vector → top-k → Claude → respuesta con fuentes | Postgres + pgvector, FastAPI, OTel a JSONL, benchmark de humo con latencias | hecha |
| 4 | Benchmark de ~50 preguntas en 8 categorías | `eval/benchmark.jsonl`, recall@k / MRR / nDCG del baseline | hecha |
| 5 | BM25 (`pg_search`) e híbrido | vector vs BM25 vs RRF vs fusión por scores, mismo benchmark | hecha |
| 6 | Reranking (bge-reranker local vs Cohere) | ganancia por categoría, latencia y costo; cuándo empeora | siguiente |
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
- Epígrafes partidos en dos líneas: se anotó como "casos aislados"; eran una
  de cada cuatro versiones actualizadas. Corregido tras la Fase 5 (ver
  "Corrección del parser").
- 194 relaciones de notas sin resolver a un `id_norma` (la norma
  modificatoria no está en el corpus).

## Fase 3 en detalle

Corrida del 2026-09-12 sobre el corpus laboral (catálogo 2026-09-12), en
Postgres 17 (ParadeDB) dentro de Colima, Apple Silicon.

- Carga: 933 documentos, 11.322 artículos, 15.327 versiones, 13.136
  relaciones, 321 eventos de historial.
- Chunks: 9.055 sobre 8.764 artículos; 2.558 artículos sin chunk (anexos,
  derogados, sin texto).
- Embeddings: hashing, 9.055 chunks en 1 min 20 s (`time`); bge-m3, 9.055
  chunks en unos 11 minutos incluyendo la descarga del modelo (2,4 GB). En una
  muestra de 60 s bge-m3 embebió 960 chunks.

Benchmark de humo (`bench smoke --no-generate`, 20 preguntas, k = 8). Sin
generación las 2 preguntas `not_in_corpus` fallan por definición, y la
pregunta sobre el art. 28 derogado no puede acertar porque el baseline no
indexa derogados: el techo es 17/20.

| Embedder | hit@8 | retrieval p50 / p95 | experimento |
|---|---|---|---|
| hashing-1024 | 0,35 (7/20) | 6 / 14 ms | `experiments/2026-09-12-phase3-hashing-retrieval-only.json` |
| bge-m3 | 0,65 (13/20) | 49 / 125 ms | `experiments/2026-09-12-phase3-bgem3-retrieval-only.json` |

La latencia de bge-m3 incluye embeber la pregunta con el modelo en CPU; la
consulta SQL es la misma en ambos casos.

Fallas de bge-m3 que valen la pena mirar en la Fase 4:

- s11 "jornada máxima": trae los arts. 190, 198, 199 y 200 de la LCT (todos de
  jornada) pero no el 196, que remite a la Ley 11.544. El artículo esperado
  está mal elegido o hace falta la Ley 11.544 en el corpus.
- s14 "falta de registración": ninguno de los esperados (Ley 24.013 art. 8,
  Ley 25.323 art. 1); trae artículos de otras normas de empleo. Caso típico de
  confusión entre normas parecidas.
- s17 "renunciar a derechos" (art. 12, irrenunciabilidad): trae artículos del
  Título IV de la LCT. Vocabulario jurídico ("irrenunciabilidad") que la
  pregunta no usa: candidato a query expansion (Fase 7) o BM25 (Fase 5).
- s18 "casos sin indemnización": trae el 245 dos veces (dos chunks del mismo
  artículo) y no el 242/247. Deduplicar por artículo al armar el contexto es
  una mejora pendiente.

No se corrió con generación: `.env` no tenía `ANTHROPIC_API_KEY` en esta
sesión. Queda para el arranque de la Fase 4: `legal-ai ask` y `bench smoke
--name phase3-baseline`, y mirar qué hace el modelo con s15 y s16.

Pendientes técnicos de esta fase:

- `index embed` actualiza fila por fila; medir cuánto del tiempo es base de
  datos y pasar a un `UPDATE ... FROM unnest(...)` por lote.
- Artículos partidos en varios chunks aparecen repetidos en el top-k.
- Las 14 normas sin artículos numerados siguen sin chunk.

## Fase 4 en detalle

Corrida del 2026-09-13 (UTC) sobre el índice de la Fase 3, catálogo
2026-09-12, `legal-ai bench run`, k = 8 chunks, métricas a nivel artículo
sobre las 44 preguntas puntuables (las 6 `not_in_corpus` se corren pero no se
puntúan). Cada celda es hashing / bge-m3.

| Categoría | n | hit@8 | recall@8 | MRR | nDCG@8 |
|---|---|---|---|---|---|
| overall | 44 | 0,41 / 0,80 | 0,36 / 0,72 | 0,19 / 0,60 | 0,21 / 0,60 |
| direct | 8 | 0,62 / 1,00 | 0,62 / 1,00 | 0,23 / 0,71 | 0,32 / 0,78 |
| multi_article | 7 | 0,43 / 1,00 | 0,29 / 0,79 | 0,23 / 0,74 | 0,21 / 0,69 |
| negation | 6 | 0,17 / 0,67 | 0,06 / 0,56 | 0,17 / 0,67 | 0,08 / 0,56 |
| confusable | 6 | 0,33 / 1,00 | 0,33 / 0,92 | 0,08 / 0,75 | 0,14 / 0,78 |
| derogated | 5 | 0,00 / 0,00 | 0,00 / 0,00 | 0,00 / 0,00 | 0,00 / 0,00 |
| temporal | 6 | 0,50 / 0,67 | 0,50 / 0,67 | 0,11 / 0,31 | 0,20 / 0,40 |
| cross_reference | 6 | 0,67 / 1,00 | 0,58 / 0,92 | 0,42 / 0,89 | 0,42 / 0,84 |

Retrieval p50 / p95: hashing 26 / 28 ms; bge-m3 46 / 50 ms (incluye embeber la
pregunta en CPU). Reportes: `experiments/2026-09-13-phase4-hashing.json`,
`experiments/2026-09-13-phase4-bgem3.json`.

Lectura:

- bge-m3 supera al control de hashing en todas las categorías puntuables. Es
  la condición mínima (ADR-019) y se cumple con margen.
- `derogated` es 0 por diseño: el baseline no indexa versiones derogadas
  (ADR-018). Es el número contra el que se va a medir la Fase 9.
- `negation` es la categoría más floja de bge-m3: b16 ("¿cuándo el despido
  no genera indemnización?") trae el art. 245 y no el 242/244; b21 ("¿puede
  renunciar a sus derechos?") no llega al art. 12, cuyo texto dice
  "irrenunciabilidad". Candidatas a BM25/híbrido (Fase 5) y a expansión de
  consultas (Fase 7).
- `temporal`: el baseline ignora `as_of`; b36 (edad mínima antes de la Ley
  26.390) y b37 (tope del art. 245 en 2010) fallan del todo, y b37 trae las
  resoluciones de topes que sí están en el corpus. Las que aciertan lo hacen
  con la versión vigente, no con la de la fecha pedida: acierto de artículo,
  no de versión.
- Multi-artículo: recall 0,79. b09 trae el 178 pero no el 182; b13 trae el 52
  en la posición 5 y no el 55. El contexto que ve el modelo tiene la mitad de
  la respuesta.
- b32 ("¿está vigente la Ley 25.250?") devuelve artículos de la propia Ley
  25.250 marcados como vigentes: la Ley 25.877 la derogó entera en su art. 1 y
  Infoleg no pone nota por artículo. Seguimiento para el parser: propagar la
  relación `deroga` a nivel norma al estado de las versiones.

Hallazgo de método: la primera corrida con hashing dio 0,00 en todo porque la
columna `embedding` tenía vectores de bge-m3 y la consulta no filtraba por
modelo. Ahora `retrieve_vector` filtra `embedding_model = :model` y los
comandos se niegan a correr sin chunks de ese modelo. Comparar dos modelos
obligó a re-embeber dos veces (la caché evitó recalcular); si la Fase 5
compara más embedders, hace falta una tabla de vectores por modelo.

Otros seguimientos:

- 8 artículos con id `…#2`: números de artículo repetidos dentro de una misma
  norma (por ejemplo `27971:51#2`). El parser los desambigua así; revisar si
  son errores de Infoleg o artículos distintos.
- Los artículos esperados los eligió el ingeniero leyendo los textos en la
  base; son provisorios hasta la revisión de abogados (Fase 14). El campo
  `notes` de cada pregunta registra las dudas.

## Fase 5 en detalle

Mismo benchmark, índice y catálogo que la Fase 4, k = 8, bge-m3 como
embedder. Cada celda es hit@8 / nDCG@8. Reportes en
`experiments/2026-09-13-phase5-*.json`.

| Categoría | n | vector | bm25 | rrf | hybrid α=0,8 |
|---|---|---|---|---|---|
| overall | 44 | 0,80 / 0,60 | 0,66 / 0,43 | 0,75 / 0,56 | 0,82 / 0,62 |
| direct | 8 | 1,00 / 0,78 | 1,00 / 0,67 | 1,00 / 0,75 | 1,00 / 0,77 |
| multi_article | 7 | 1,00 / 0,69 | 0,86 / 0,48 | 0,86 / 0,70 | 1,00 / 0,69 |
| negation | 6 | 0,67 / 0,56 | 0,33 / 0,15 | 0,67 / 0,45 | 0,67 / 0,56 |
| confusable | 6 | 1,00 / 0,78 | 0,33 / 0,27 | 0,67 / 0,45 | 1,00 / 0,77 |
| derogated | 5 | 0,00 / 0,00 | 0,20 / 0,20 | 0,20 / 0,20 | 0,20 / 0,09 |
| temporal | 6 | 0,67 / 0,40 | 0,67 / 0,43 | 0,67 / 0,42 | 0,67 / 0,41 |
| cross_reference | 6 | 1,00 / 0,84 | 1,00 / 0,69 | 1,00 / 0,82 | 1,00 / 0,86 |

Totales: vector: hit 0,80, recall 0,72, MRR 0,60, nDCG 0,60 | bm25: hit 0,66, recall 0,61, MRR 0,39, nDCG 0,43 | rrf: hit 0,75, recall 0,70, MRR 0,55, nDCG 0,56 | hybrid α=0,8: hit 0,82, recall 0,75, MRR 0,61, nDCG 0,62.

Latencia de retrieval (p50): vector p50 46 ms · bm25 p50 16 ms · rrf p50 74 ms · hybrid α=0,8 p50 64 ms. BM25 solo es el más rápido; el híbrido
paga el vector más BM25 más la fusión.

Lectura:

- **BM25 solo pierde contra el vector** en todo salvo `derogated` (encuentra
  "Derógase la Ley 25.250" por el término exacto) y `temporal`. En
  `confusable` da 0,33 de hit: "período de prueba" y "vacaciones" aparecen
  igual en la LCT y en la Ley 26.844, y BM25 no sabe que "casas particulares"
  decide la norma. El vector sí.
- **La hipótesis de la Fase 4 era falsa**: BM25 no levanta `negation` (nDCG
  0,15). El stemmer español no une "renunciar" con "irrenunciabilidad" y las
  palabras de negación son de baja rareza. Queda para expansión de consultas
  (Fase 7).
- **RRF a pesos iguales empeora al vector** (nDCG 0,56 contra 0,60): reparte
  el ranking entre una lista fuerte y una débil. Se probaron pools de 8, 16 y
  24, pesos 1:1, 2:1 y 3:1 y k=10 y 60 (script de barrido, no versionado):
  ninguna combinación superó al vector.
- **La fusión por scores normalizados** (min-max por lista, 0,8 vector +
  0,2 BM25, pool 24) da hit 0,82, recall 0,75, MRR 0,61, nDCG 0,62: una
  pregunta más que el vector (b32, la ley derogada) y un poco mejor en orden.
  Con 44 preguntas, la diferencia es del tamaño del ruido. Se adopta como
  default (ADR-022) porque no empeora hit ni recall en ninguna categoría y
  suma la coincidencia exacta de términos, que va a importar más cuando el
  benchmark tenga preguntas por número de norma o artículo.
- **Deduplicar por artículo no cambió ninguna métrica**: las 8 preguntas cuyo
  top-8 cambió sumaron artículos que no eran los esperados. El costo de
  latencia (pool 24 en HNSW) no se justifica hoy; queda desactivado.

Seguimientos:

- Las variantes híbridas tuvieron p95 altos en la primera corrida (más de
  500 ms) que no se repitieron en la segunda; medir con más repeticiones antes
  de sacar conclusiones de latencia.
- Barrido de fusión como comando reproducible (`bench sweep`) en vez de un
  script suelto.

## Corrección del parser tras la Fase 5 (2026-09-13)

Al inspeccionar los fallos del benchmark apareció un bug del parser: 1.168 de
las 4.686 versiones actualizadas (2.271 de 15.327 en total) empezaban en
minúscula porque Infoleg parte el epígrafe con un salto de línea del fuente
HTML y el conversor lo tomaba como línea nueva. El prefijo del art. 12 decía
"Protección." y el texto empezaba "de los trabajadores. Irrenunciabilidad.".
Los nombres de capítulo también quedaban cortados ("...por justa").

Arreglo: los saltos de línea del fuente son espacios, salvo antes de un
encabezado de artículo sin etiqueta (84 casos en 50 archivos) y dentro de las
celdas de las páginas de vínculos. La jerarquía acepta nombre sin separador y
se parte cuando dos marcadores comparten línea; los epígrafes seguidos de una
oración sin guion se reconocen. Resultado sobre el corpus: 11.322 → 11.367
artículos, 15.327 → 15.376 versiones, versiones en minúscula 2.271 → 16,
epígrafes basura (la primera línea del cuerpo tomada como título) 689 menos,
epígrafes nuevos 195, 15 artículos de un anexo falso eliminados, 105 de un
anexo real recuperados. Historial (321) y relaciones (13.136) sin cambio.
Goldens regenerados; LCT sigue con 293 artículos, 16 derogados y 1
advertencia.

Efecto en el benchmark (mismas 44 preguntas, k = 8, bge-m3, todo el corpus
re-embebido; cada celda es hit@8 / nDCG@8):

| Categoría | vector antes | vector después | híbrido antes | híbrido después |
|---|---|---|---|---|
| overall | 0,80 / 0,60 | 0,77 / 0,60 | 0,82 / 0,62 | 0,80 / 0,59 |
| direct | 1,00 / 0,78 | 1,00 / 0,77 | 1,00 / 0,77 | 1,00 / 0,77 |
| multi_article | 1,00 / 0,69 | 1,00 / 0,72 | 1,00 / 0,69 | 1,00 / 0,69 |
| negation | 0,67 / 0,56 | 0,67 / 0,56 | 0,67 / 0,56 | 0,67 / 0,50 |
| confusable | 1,00 / 0,78 | 1,00 / 0,81 | 1,00 / 0,77 | 1,00 / 0,77 |
| derogated | 0,00 / 0,00 | 0,00 / 0,00 | 0,20 / 0,09 | 0,00 / 0,00 |
| temporal | 0,67 / 0,40 | 0,67 / 0,39 | 0,67 / 0,41 | 0,67 / 0,39 |
| cross_reference | 1,00 / 0,84 | 0,83 / 0,76 | 1,00 / 0,86 | 1,00 / 0,82 |

Totales: vector antes: hit 0,80, recall 0,72, MRR 0,60, nDCG 0,60 | vector después: hit 0,77, recall 0,70, MRR 0,61, nDCG 0,60 | híbrido antes: hit 0,82, recall 0,75, MRR 0,61, nDCG 0,62 | híbrido después: hit 0,80, recall 0,72, MRR 0,58, nDCG 0,59.

Lectura honesta: **el bug era real y había que arreglarlo, pero no movió el
retrieval**. Cambiaron cuatro preguntas, dos para cada lado, dentro del ruido.
Lo que se aprende de los casos:

- b09 (embarazo) y b23 (vacaciones en casas particulares) suben una o dos
  posiciones: el prefijo completo ayuda un poco.
- b32 / b50 ("¿está vigente la Ley 25.250?" → Ley 25.877 art. 1, "Derógase la
  Ley 25.250") bajan de la posición 3 a la 19 en el vector: el prefijo ahora
  incluye "TITULO PRELIMINAR DEL ORDENAMIENTO DEL REGIMEN LABORAL" y el
  artículo tiene una sola línea; el prefijo largo diluye al texto corto.
  Contextual retrieval no es gratis para artículos de una oración.
- b21 ("¿puede renunciar a sus derechos?") sigue en la posición 47 aunque el
  prefijo ahora dice "Irrenunciabilidad": el problema es semántico (la
  pregunta no usa la palabra y el modelo no une renunciar con
  irrenunciabilidad), no de datos. Candidato a reranker y a reescritura.
- b16 (242/244) sigue fuera de los 200 primeros.

Reportes: `experiments/2026-09-13-phase5b-parserfix-{vector,hybrid}.json`.
El default sigue en `hybrid` (ADR-022); con el índice nuevo empata al vector
en nDCG (0,59 contra 0,60) y sigue sin empeorar hit ni recall en ninguna
categoría, pero la ventaja que se midió en la Fase 5 desapareció: es ruido.

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
