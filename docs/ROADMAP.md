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
| 6 | Reranking (bge-reranker local vs Cohere) | ganancia por categoría, latencia y costo; cuándo empeora | hecha (local; Cohere pendiente) |
| 7 | Query expansion / decomposition, contextual retrieval | query original vs expandida | hecha (reescritura + multi-query) |
| 8 | Generación fundamentada: claims + fuentes + abstención | % claims soportados, abstención correcta | siguiente (primer smoke medido) |
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

## Segunda pasada de debug del retrieval (2026-09-13)

Cuatro sospechosos que la primera pasada no había revisado, medidos sobre las
44 preguntas puntuables con el índice re-parseado:

1. **Índice HNSW aproximado vs búsqueda exacta.** Con `enable_indexscan =
   off` el top-8 es idéntico en las 44 preguntas (hit 0,77, nDCG 0,60 en
   ambos; `ef_search` 40, `iterative_scan` off). El índice no pierde nada.
2. **¿El prefijo de contexto diluye el texto?** Coseno pregunta–chunk con y
   sin prefijo para los esperados y sus competidores: el prefijo sube el
   coseno en todos los casos (art. 12: 0,511 → 0,572). En b32 el prefijo
   favorece más a los competidores (artículos de la propia Ley 25.250, cuyo
   prefijo dice "Ley 25250") que al esperado ("Derógase la Ley 25.250",
   0,602 → 0,604). El prefijo no es el problema; el nombre de la norma en el
   prefijo compite con la mención de la norma en la pregunta.
3. **Reformular la pregunta con el vocabulario de la ley.** Con la misma
   búsqueda exacta: b21 "Irrenunciabilidad de los derechos del trabajador…"
   pone al art. 12 en la posición 1 (desde la 45); b16 "Despido con justa
   causa por injuria… abandono de trabajo" pone al 242 en la 1 y al 244 en
   la 8 (desde fuera de los 200); b09 sube el 182 de la 36 a la 7; b13 sube
   el 55 de la 29 a la 3. Es la confirmación del cubo "vocabulario": la
   pregunta lega y el texto legal no comparten palabras y bge-m3 no cierra la
   brecha. La reescritura automática necesita un LLM (Fase 7) o un glosario.
4. **Reranker sobre los 50 primeros** (`BAAI/bge-reranker-v2-m3`, cross-
   encoder, local en MPS, sondeo sin versionar): hit@8 0,77 → 0,84, recall
   0,70 → 0,81, MRR 0,61 → 0,65, nDCG 0,60 → 0,67. Por categoría (nDCG):
   negación 0,56 → 0,70 (art. 12 de la 45 a la 1), referencia cruzada 0,76 →
   0,94, temporal 0,39 → 0,53, directa 0,77 → 0,83; confundible baja 0,81 →
   0,73 (los artículos de la Ley 26.844 pierden frente a los de la LCT con el
   mismo tema). Latencia 3,6 s por pregunta (p50) con pool 50 en esta
   máquina: hay que medir pools de 20 y 30, y Cohere por API.

Hallazgos laterales:

- **Un artículo citado se filtró como artículo propio**: en la Ley 27.742 el
  "Artículo 92 bis: Período de prueba…" citado tras "Sustitúyese el artículo
  92 bis… por el siguiente:" quedó como `401266:92bis`, porque 92 sigue a 91 y
  la heurística de cita sólo actuaba cuando la numeración no era la esperada.
  Ese chunk salía segundo en la pregunta del período de prueba. Regla nueva:
  si la línea anterior termina en ":" y nombra ese mismo artículo, es cita.
  Test agregado.
- **Duplicados exactos** entre normas (986 pares de versiones con el mismo
  texto, más de 120 caracteres) casi no entran al top-8: 2 de 347 candidatos.
  Los cuasi-duplicados sí compiten (la Ley 26.088 art. 1, que transcribe el
  art. 66 LCT, es el primer resultado de b21), pero no son la causa
  principal.
- **Etiquetas**: el art. 182 (indemnización especial) está en el capítulo de
  despido por matrimonio; el 178 (embarazo) remite a él. b09 es en realidad
  una pregunta de referencia cruzada: sin seguir la remisión, el 182 no
  aparece por semántica.

Efecto del arreglo del artículo citado, re-parseado y re-embebido (vector:
hit 0,75, recall 0,68, MRR 0,59, nDCG 0,58; híbrido: hit 0,77, recall
0,70, MRR 0,56, nDCG 0,57): b01 y b33 suben una posición porque el chunk
duplicado ya no compite, y b45 ("¿qué ley sustituyó el 92 bis y con qué
artículo?") cae de la posición 1 a fuera del top-8: el chunk del art. 91 de
la Ley 27.742 era antes una sola oración ("Sustitúyese el artículo 92 bis…
por el siguiente:"), que calzaba exacto con la pregunta, y ahora incluye el
texto citado completo, que la diluye. Un artículo que consiste en "puntero +
texto citado" mezcla dos cosas; separarlos en dos chunks es un experimento de
chunking para la Fase 7. Reportes:
`experiments/2026-09-13-phase5c-quotefix-{vector,hybrid}.json`.

Otro hallazgo de método: la caché de embeddings vivía en
`data/processed/<corpus>/embeddings/`, y `legal-ai parse` borra ese
directorio entero. Cada re-parseo obligó a re-embeber los 9.100 chunks
(unos 10 minutos) aunque casi ningún texto hubiera cambiado. La caché pasa a
`data/cache/embeddings/`.

Conclusión de las dos pasadas: el índice, el prefijo y el parser están bien
(el parser tenía bugs y se arreglaron, sin efecto en las métricas). Los
fallos que quedan son de orden dentro de los primeros 50 (reranker, ganancia
medida) y de vocabulario entre pregunta y ley (reescritura, ganancia medida
a mano, pendiente de automatizar). La Fase 6 implementa el reranker con pool
y latencia medidos; la Fase 7, la reescritura.

## Fase 6 en detalle: reranking

Cross-encoder `BAAI/bge-reranker-v2-m3` local (MPS) sobre el pool del
retriever; la pregunta original y `prefijo + texto` de cada chunk se leen
juntos y se reordena. Corrida del 2026-09-13, mismas 44 preguntas, k = 8.

| Configuración | hit@8 | recall@8 | MRR | nDCG@8 | retrieval p50 | nota |
|---|---|---|---|---|---|---|
| híbrido (base, chunks partidos) | 0,80 | 0,72 | 0,57 | 0,58 | 70 ms |  |
| vector (base) | 0,77 | 0,70 | 0,58 | 0,58 | 50 ms |  |
| híbrido + rerank pool 20 | 0,77 | 0,72 | 0,60 | 0,60 | 2223 ms | índice previo al corte de chunks |
| híbrido + rerank pool 30 | 0,77 | 0,73 | 0,60 | 0,61 | 2732 ms | ídem |
| híbrido + rerank pool 50 | 0,82 | 0,79 | 0,63 | 0,65 | 3545 ms |  |
| vector + rerank pool 30 | 0,77 | 0,74 | 0,60 | 0,62 | 2558 ms | índice previo |
| vector + rerank pool 50 | 0,84 | 0,81 | 0,65 | 0,67 | 3605 ms | mejor sin LLM |

- El pool importa más que el modelo de fusión: con pool 30 el art. 12 (posición
  45 en el vector) no entra y la ganancia casi desaparece; con pool 50 entra y
  sube a la posición 1. El híbrido de 50 lo pierde al fusionar. Por eso el
  mejor sin LLM es vector + rerank 50.
- Por categoría: negación 0,56 → 0,70 de nDCG, referencia cruzada 0,76 →
  0,94, temporal 0,39 → 0,59; confundibles baja 0,81 → 0,73.
- Costo: 2,2 a 3,7 s por pregunta en esta máquina según el pool. Cohere
  Rerank por API queda pendiente (sin clave).
- Decisión (ADR-023): disponible, apagado por default. Encima de la
  reescritura no suma y agrega segundos.

## Fase 7 en detalle: reescritura de la pregunta

Claude reescribe la pregunta con el vocabulario de la ley (salida
estructurada: `query` + `terms`), con caché en disco por pregunta y modelo.
`multi-query` fusiona por RRF los resultados de la pregunta original y de la
reescrita. Reescribir 50 preguntas: Sonnet 5, p50 2,7 s por llamada, $0,22 en
total a precio de lista; Opus 5, p50 5,2 s, unos $0,007 por llamada.

| Configuración | hit@8 | recall@8 | MRR | nDCG@8 | retrieval p50 | nota |
|---|---|---|---|---|---|---|
| híbrido + reescritura Opus 5 | 0,84 | 0,81 | 0,68 | 0,69 | 100 ms |  |
| vector + reescritura Opus 5 | 0,84 | 0,81 | 0,67 | 0,68 | 60 ms |  |
| híbrido + reescritura Opus 5 + multi-query | 0,86 | 0,83 | 0,64 | 0,66 | 173 ms |  |
| vector + reescritura Opus 5 + multi-query | 0,86 | 0,83 | 0,62 | 0,65 | 114 ms |  |
| híbrido + reescritura Sonnet 5 | 0,82 | 0,81 | 0,63 | 0,66 | 94 ms |  |
| híbrido + reescritura Sonnet 5 + multi-query | 0,86 | 0,84 | 0,62 | 0,64 | 249 ms | default nuevo |
| vector + reescritura Opus 5 + rerank 50 | 0,80 | 0,77 | 0,63 | 0,65 | 3473 ms |  |
| híbrido + reescritura Opus 5 + rerank 50 | 0,82 | 0,80 | 0,64 | 0,66 | 3513 ms |  |

Por categoría (hit@8 / nDCG@8):

| Config | direct | multi_article | negation | confusable | derogated | temporal | cross_reference |
|---|---|---|---|---|---|---|---|
| híbrido base | 1,00 / 0,71 | 1,00 / 0,68 | 0,67 / 0,50 | 1,00 / 0,77 | 0,00 / 0,00 | 0,67 / 0,47 | 1,00 / 0,76 |
| vector + rerank 50 | 1,00 / 0,83 | 1,00 / 0,68 | 0,83 / 0,70 | 0,83 / 0,73 | 0,20 / 0,09 | 0,83 / 0,59 | 1,00 / 0,94 |
| híbrido + Sonnet + multi (default) | 1,00 / 0,80 | 1,00 / 0,68 | 0,83 / 0,55 | 1,00 / 0,91 | 0,20 / 0,09 | 0,83 / 0,55 | 1,00 / 0,78 |
| híbrido + Opus (sin multi) | 1,00 / 0,74 | 0,86 / 0,76 | 1,00 / 0,76 | 1,00 / 0,88 | 0,20 / 0,13 | 0,83 / 0,67 | 0,83 / 0,77 |

- La reescritura rescata las dos preguntas de vocabulario: b21 (art. 12) pasa
  de fuera del top-8 a la posición 2 y b16 (242/244) de fuera de los 200 a la
  5 con Opus. Es exactamente lo que la segunda pasada de debug había medido a
  mano.
- Reescribir también pierde: b13 y b45 (preguntas "puntero", del tipo "¿qué
  ley sustituyó…?") se abstraen y dejan de calzar. `multi-query` las recupera
  al conservar la pregunta original: hit 0,84 → 0,86, a costa de MRR (RRF
  reparte las primeras posiciones).
- Rerank encima de la reescritura no mejora (0,66 contra 0,69 de nDCG): el
  cross-encoder ve la pregunta original y reordena candidatos que la
  reescritura ya había ordenado bien.
- Quedan 6 fallos en la mejor configuración: b16 (con Sonnet), los 4
  derogados sin chunk y b36 (temporal). El techo de esta fase para lo
  alcanzable es 38 de 39.
- Decisión (ADR-024): default `hybrid + reescritura Sonnet 5 + multi-query`.
  Sin `ANTHROPIC_API_KEY` el sistema degrada a híbrido sin reescritura.

## Fase 8, anticipo: primer smoke con generación

`bench smoke` con Claude Opus 5 sobre las 20 preguntas de humo (retriever
híbrido sin reescritura, 2026-09-13): hit@8 0,80; abstención correcta en las
2 preguntas sin respuesta en el corpus (s15, s16) y también en s11 (jornada:
la Ley 11.544 no está), s14, s17, s18 y s20; **0 fuentes citadas fuera del
contexto en 20 respuestas**; 67,771 tokens de entrada y
24,955 de salida, $0.96 a precio de lista, p50 total
15.5 s por pregunta (la generación domina). Reporte:
`experiments/2026-09-13-phase3-baseline-generation.json`. La Fase 8 mide
claims soportados con un juez y la abstención sobre el benchmark grande.

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
