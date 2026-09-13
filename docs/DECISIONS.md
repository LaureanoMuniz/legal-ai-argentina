# Decisiones de arquitectura

Formato ADR: contexto, decisión, alternativas descartadas, consecuencias.
Una decisión no se borra: si cambia, se agrega una nueva que la reemplaza.

## ADR-001: Python

**Contexto.** Hay que elegir lenguaje para retrieval, embeddings, evaluación y API.

**Decisión.** Python 3.12 con `uv`, `ruff`, `pyright`, `pytest`.

**Alternativas.** TypeScript: creció para agentes y front, pero embeddings
open-weight, rerankers, Ragas/DeepEval y el grueso del ecosistema salen
primero en Python.

**Consecuencias.** Acceso directo a `sentence-transformers` y a todo el
tooling de evaluación. La API puede exponerse a cualquier front.

## ADR-002: Postgres + pgvector + pg_search como único motor

**Contexto.** Necesitamos búsqueda vectorial, BM25, filtros por fecha y
metadata relacional (versiones, relaciones entre normas).

**Decisión.** PostgreSQL 17 con `pgvector` (HNSW) y ParadeDB `pg_search`
(BM25 sobre Tantivy), en Docker Compose. Acceso con SQLAlchemy 2.0 Core +
Alembic + psycopg 3.

**Alternativas.**
- SQLite + numpy: suficiente para el corpus inicial, pero no es lo que se usa
  en producción y no enseña nada transferible. Descartado por pedido explícito.
- Qdrant / Weaviate: híbrido incluido y mejores latencias en benchmarks
  sintéticos, pero es una segunda base que sincronizar con la metadata legal,
  que sí o sí vive en Postgres.
- Postgres FTS (`tsvector` + `ts_rank`): no es BM25 real. Se medirá contra
  `pg_search` como experimento.

**Consecuencias.** Una sola fuente de verdad; el SQL de retrieval queda
visible; si el volumen crece, `pgvectorscale` es el siguiente paso sin cambiar
de motor.

## ADR-003: Infoleg vía datos.jus.gob.ar como fuente

**Contexto.** Se necesita legislación argentina oficial, con metadata,
fechas y relaciones de modificación.

**Decisión.** Base Infoleg del Ministerio de Justicia (CC BY 4.0, mensual):
CSV de normas + dos CSV de relaciones, y descarga de los HTML de texto
original y actualizado desde `servicios.infoleg.gob.ar`.

**Alternativas.** argentina.gob.ar/normativa es un buscador sobre la misma
base, sin API ni descarga masiva. datos.gob.ar espeja el mismo dataset. SAIJ
tiene jurisprudencia, fuera de alcance por ahora.

**Consecuencias.** El fetcher necesita User-Agent de navegador (403 sin él),
caché y respeto de rate limit. No hay estado de vigencia ni versiones
históricas: se infieren y reconstruyen (ADR-006).

## ADR-004: Corpus inicial de derecho laboral

**Contexto.** El corpus debe ser chico, real, con reformas y con referencias
cruzadas, y evaluable por los dos abogados disponibles.

**Decisión.** Ley 20.744 (LCT) más las leyes que la modifican y complementan,
declaradas en `corpus/laboral.yaml` por número de norma y expandidas con las
modificatorias a profundidad 1.

**Alternativas.** Código Civil y Comercial: enorme y poco modificado, flojo
para temporal. Defensa del consumidor: chico, pero menos denso en relaciones.

**Consecuencias.** Preguntas cotidianas (despido, preaviso, indemnización),
muchas versiones por artículo (reformas 2024 y 2026), grafo natural de
relaciones.

## ADR-005: El artículo es la unidad; el chunk apunta a una versión

**Contexto.** Chunking por tokens rompe la estructura jurídica y hace
imposible citar.

**Decisión.** Parser que produce `documents → articles → article_versions →
chunks`. Un artículo normalmente es un chunk. Cada chunk lleva un prefijo de
contexto (norma, título, capítulo, artículo, epígrafe, vigencia) para
contextual retrieval. Las citas son `article_id@version`.

**Alternativas.** Chunks de N tokens con overlap: baseline conocido, pero sin
identidad jurídica. Se puede medir como control si hace falta.

**Consecuencias.** Citas exactas, filtros temporales posibles, y un parser
que requiere tests contra HTML real.

## ADR-006: Dos versiones por artículo desde el inicio

**Contexto.** Infoleg entrega texto original y texto actualizado, y notas
inline con la norma y fecha de cada modificación.

**Decisión.** Parsear ambos textos y emitir versiones `original` y `current`
con `effective_from` / `effective_until` derivados de las notas. Las versiones
intermedias (`reconstructed`) se abordan en la Fase 9 a partir de las normas
modificatorias.

**Consecuencias.** El problema de Temporal Misgrounding se puede medir desde
la Fase 3, no recién en la 9.

## ADR-007: Embeddings y reranker open-weight como baseline, API como comparación

**Contexto.** Hay que elegir modelos de embedding y reranking para castellano
jurídico, y no hay claves de API en el entorno.

**Decisión.** `bge-m3` (embeddings) y `bge-reranker-v2-m3` (reranking)
corriendo localmente como baseline reproducible. Voyage (embeddings) y Cohere
Rerank (reranking) vía API como segundo brazo del experimento cuando haya
claves.

**Alternativas.** OpenAI text-embedding-3, Gemini Embedding, Qwen3-Embedding,
multilingual-e5. Se pueden agregar al mismo harness de comparación.

**Consecuencias.** Se puede correr todo sin pagar. Cuál gana en este corpus
se decide con el benchmark, no por leaderboard.

## ADR-008: Claude Opus 5 con structured outputs nativos

**Contexto.** El generador debe devolver respuesta, claims con fuentes y
señal de evidencia insuficiente, de forma verificable.

**Decisión.** `claude-opus-5` vía SDK oficial de Anthropic, adaptive thinking,
`output_config.format` con esquema Pydantic. Sonnet 5 / Haiku 4.5 para
reescritura de queries y como juez, si el costo lo justifica y se mide.

**Alternativas.** Instructor u otros wrappers de JSON: innecesarios con
structured outputs nativos. Modelos locales vía Ollama: un modelo chico falla
de formas que no se distinguen de fallas del RAG.

**Consecuencias.** Requiere `ANTHROPIC_API_KEY`. Prompt caching sobre el
system prompt y el contexto para latencia y costo.

## ADR-009: OpenTelemetry + Langfuse

**Contexto.** Hay que poder explicar por qué una respuesta salió mal:
candidatos, scores, contexto, prompt, salida.

**Decisión.** Instrumentar con OpenTelemetry usando las GenAI semantic
conventions y exportar a Langfuse self-hosted. Langfuse también guarda
datasets, scores y etiquetas humanas.

**Alternativas.** Arize Phoenix: OTel-nativo y muy bueno para debug de RAG;
queda como alternativa de exportador sin cambiar la instrumentación. JSON a
disco: no es lo que se usa en producción.

**Consecuencias.** Compose suma Langfuse (con su Postgres y ClickHouse). La
instrumentación es vendor-neutral.

## ADR-010: Sin framework de orquestación hasta la Fase 12

**Contexto.** LangChain/LlamaIndex/LangGraph esconden retrieval y prompts
detrás de abstracciones.

**Decisión.** Pipeline explícito en funciones propias hasta que exista un
agente. Para la Fase 12, Pydantic AI (type-safe, instrumentación OTel nativa).

**Alternativas.** LangGraph: mayor adopción, más pesado; queda documentado
como alternativa si el agente necesita grafos de estado complejos.

## ADR-011: Código en inglés, documentación y prompts en castellano

**Decisión.** Identificadores, schema y archivos en inglés. Docs, benchmark,
prompts e interfaz de evaluación en castellano, idioma del corpus y de los
evaluadores.

## ADR-012: `data/raw` inmutable, `data/processed` regenerable

**Decisión.** Nada en `raw` se edita a mano ni se reescribe sin `--force`.
Cada archivo lleva `fetched_at` y sha256. `processed` se borra y regenera con
cada corrida del parser. Los experimentos referencian la fecha del catálogo
que usaron.

## ADR-013: Métricas propias primero, frameworks de evaluación como contraste

**Decisión.** recall@k, MRR, nDCG y el juez LLM se implementan a mano con
tests. Ragas y DeepEval se agregan después para comparar sus scores con los
propios, no para reemplazarlos.

**Consecuencias.** Se entiende qué mide cada número antes de confiar en él.

## ADR-014: El corpus incluye todos los tipos de norma vinculados a las semillas

**Contexto.** El plan original filtraba la expansión a leyes y decretos,
asumiendo que las resoluciones eran ruido administrativo. Al mirar las 665
normas excluidas: 650 resoluciones, muchas del Ministerio de Trabajo y del
Consejo del Salario Mínimo, con topes indemnizatorios del art. 245, promedios
de remuneraciones y salario mínimo. Es decir, los números que la LCT delega.

**Decisión.** `expand.tipos` queda opcional en el manifest y en `laboral` se
deja en `null` (todos los tipos). El corpus pasa de 266 a 931 normas.

**Alternativas.** Mantener el filtro y agregar resoluciones a mano: decide
sin medir. Filtrar por organismo: mismo problema.

**Consecuencias.** Más ruido potencial en retrieval (53 resoluciones de
salario mínimo casi idénticas), que es exactamente lo que el benchmark tiene
que detectar. Cada norma conserva `tipo_norma` y `reason`, así que un filtro
por tipo en la consulta se puede evaluar como experimento en la Fase 5. 163 de
las nuevas normas no tienen texto en Infoleg: quedan con metadata sola.

## ADR-015: La versión "original" de la LCT es el texto ordenado de 1976

**Contexto.** Infoleg no tiene el cuerpo de la Ley 20.744 de 1974: su
`norma.htm` es la ley aprobatoria (3 artículos). El texto vigente es el texto
ordenado por Decreto 390/76, cuyo `norma.htm` trae los 277 artículos como
anexo, con la numeración que se usa hasta hoy.

**Decisión.** El manifest permite declarar `original_from` en una semilla.
Para la LCT apunta al Decreto 390/76; el parser toma los artículos del anexo
como versión `original`, con `effective_from` 1976-05-21 y
`source_document_id` 229909. La versión de 1974 con la numeración vieja queda
fuera del alcance. Un documento que sirve de `original_from` no incluye su
anexo como artículos propios, para no duplicar.

**Consecuencias.** Toda cita "original" de la LCT es al t.o. 1976, y así se
etiqueta. Si una fuente futura trae el texto de 1974, entra como una versión
más, no reemplaza a esta.

## ADR-016: Parser propio por líneas, sin librería de HTML

**Contexto.** El HTML de Infoleg es plano: `<p>`, `<br>`, `<b>`, `<span>`,
sin clases ni estructura semántica; el `<b>` a veces envuelve el `<p>`.

**Decisión.** Aplanar a líneas de texto y reconocer estructura con expresiones
regulares probadas contra las variantes reales de encabezado, con golden
files de cuatro normas reales (LCT actualizada, anexo del Decreto 390/76,
Resolución 384/2004, Ley 25.323). Las advertencias del parser son salida de
primera clase (`parse_report.json`), no logs.

**Alternativas.** selectolax/BeautifulSoup: una dependencia para recorrer un
árbol que no significa nada. Un LLM para extraer estructura: no determinista,
caro para 933 normas y opaco para debuggear.

**Consecuencias.** Cada variante nueva es un caso de test. Las normas sin
artículos numerados (comunicaciones del BCRA, circulares, decretos de
promulgación) quedan con `front_matter` y sin artículos, listadas en el
reporte.

## ADR-017: Las notas de Infoleg son la autoridad sobre cambios; el texto se compara por similitud

**Contexto.** Las dos copias de un mismo artículo (anexo del Decreto 390/76 y
`texact.htm`) difieren en transcripción. Con igualdad exacta, 120 artículos
de la LCT aparecían "cambiados sin nota".

**Decisión.** Un artículo `current` sin nota fechada cuenta como sin cambios
si su similitud normalizada con el `original` es ≥ 0,9 (`effective_from` = la
fecha del original). Con nota fechada, entera o parcial, la fecha de la nota
manda. Por debajo de 0,9 y sin nota, se emite advertencia y se usa la fecha
del documento actual.

**Consecuencias.** En la LCT quedan 2 advertencias reales (arts. 89 y 147,
notas compuestas o de capítulo). En anexos de resoluciones que Infoleg
reescribe entero sin nota por artículo quedan cientos, y son honestas: no
sabemos la fecha de ese cambio.

## ADR-018: Baseline de chunks: una versión vigente por artículo, con prefijo de contexto

**Decisión.** El chunk baseline es la versión `current` (o la `original` si no
hay actualizada), sólo `vigente`, con texto, fuera de anexos. Se embebe
`context_prefix + "\n" + text`. Artículos de más de 2.500 caracteres se
parten por incisos. Anexos, derogados y preámbulos quedan para experimentos
de la Fase 5.

**Alternativas.** Chunks de N tokens con solapamiento: pierde la identidad
jurídica (ADR-005). Indexar todas las versiones: mezcla vigente e histórico
antes de tener el filtro temporal de la Fase 9.

**Consecuencias.** En el corpus laboral: 9.055 chunks sobre 8.764 artículos;
2.558 artículos quedan afuera (anexos, derogados, sin texto). Una pregunta
sobre un artículo derogado no puede encontrar evidencia hasta la Fase 9.

## ADR-019: Embedder intercambiable con un fallback determinista

**Decisión.** `Embedder` es un protocolo; `bge-m3` es el modelo del baseline y
`HashingEmbedder` (feature hashing de unigramas y bigramas, 1024 dimensiones)
es el fallback sin descarga que usan los tests y sirve como control: si un
modelo de 2 GB no supera al hashing en el benchmark, algo está mal.

**Consecuencias.** Los embeddings se cachean en disco por `(modelo, sha256 del
texto)`, así rehacer chunks no recalcula lo que no cambió. La columna
`chunks.embedding_model` dice con qué modelo está cada vector; mezclar modelos
en una misma búsqueda es un error de datos, no de código.

## ADR-020: Trazas OTel siempre a disco, OTLP opcional

**Decisión.** Cada request escribe sus spans (GenAI semantic conventions) en
`data/traces/spans.jsonl` con un exportador propio de unas 40 líneas, y además
a un endpoint OTLP si está configurado. Langfuse se levanta en la Fase 13; la
instrumentación no cambia.

**Alternativas.** Levantar Langfuse ya: tres contenedores más (Postgres,
ClickHouse, web) antes de tener una sola pregunta respondida. Loguear a mano:
sin `trace_id` que una la respuesta con sus spans.

**Consecuencias.** `AskResponse.trace_id` permite abrir el JSONL y ver los
candidatos, el tamaño del contexto y los tokens de esa pregunta exacta.

## ADR-021: Benchmark de retrieval a nivel artículo, con categorías que el baseline no puede ganar

**Contexto.** Veinte preguntas de humo alcanzan para saber si algo está roto,
no para comparar retrievers. Hace falta un conjunto fijo, con categorías que
representen los fallos que esperamos (ROADMAP, "Problemas que esperamos
encontrar") y con métricas de ranking, no un sí/no.

**Decisión.** `eval/benchmark.jsonl`: 50 preguntas en 8 categorías (directa,
multi-artículo, negación, confundible, derogado, temporal, sin respuesta en el
corpus, referencia cruzada). La unidad de acierto es el artículo (`25552:245`),
no el chunk ni la versión: los chunks recuperados se deduplican por artículo
conservando el orden y sobre esa lista se calculan recall@k, precision@k, MRR,
nDCG@k y hit@k, por pregunta, por categoría y en total. Las preguntas sin
respuesta en el corpus se corren y se cronometran pero no se puntúan: la
abstención es una métrica de generación (Fase 8). Las categorías derogado y
temporal se puntúan igual que las demás aunque el baseline no pueda ganarlas:
la tabla por categoría hace visible la deuda en vez de esconderla.

**Artículos esperados.** Los eligió el ingeniero leyendo los textos en la base
(no de memoria) y se verificó que cada id exista en `articles`. Son
provisorios hasta la revisión de abogados de la Fase 14. Una pregunta puede
tener un artículo esperado discutible; el benchmark registra `notes` para eso.

**Alternativas.** Puntuar por chunk: premia partir artículos. Puntuar por
versión: no tiene sentido hasta que el índice tenga más de una versión (Fase
9). Usar un LLM como juez de relevancia en vez de artículos esperados: más
flexible, pero no reproducible sin fijar modelo y prompt; queda para
contrastar en la Fase 8.

**Consecuencias.** `k` cuenta chunks; si un artículo aparece en dos chunks,
ocupa dos lugares del top-k y el recall lo paga. Es deliberado: es el
comportamiento que ve el modelo en el contexto.

## ADR-022: Híbrido por fusión de scores normalizados, no RRF; vector sigue siendo el que manda

**Contexto.** La Fase 5 agregó BM25 (pg_search, stemmer español) sobre los
mismos chunks y lo comparó con el vector (bge-m3) en el benchmark de la Fase
4. BM25 solo perdió en casi todas las categorías; RRF a pesos iguales (la
receta habitual) quedó por debajo del vector solo en nDCG (0,56 contra 0,60),
con cualquier pool y peso probado.

**Decisión.** El modo `hybrid` fusiona por combinación convexa de scores
normalizados por min-max dentro de cada lista (pool de 24 por fuente):
`0,8 · vector + 0,2 · BM25`. Pasa a ser el default de `retrieval_mode`. RRF
queda disponible como modo `rrf` para seguir comparando. El peso vive en
`Settings.hybrid_alpha`.

**Por qué no RRF.** RRF ignora la magnitud de los scores: el primer resultado
de BM25 vale lo mismo que el primero del vector aunque BM25 esté adivinando.
Con una fuente claramente más débil, eso diluye a la fuerte. La fusión por
scores deja que el vector mande y que BM25 sólo desempate o rescate
coincidencias exactas (números de norma, "derógase").

**Consecuencias.** La ganancia medida es de una pregunta en 44 y +0,02 de
nDCG: del tamaño del ruido. El default se adopta porque no empeora hit ni
recall en ninguna categoría y porque la coincidencia exacta de términos es
una propiedad que el benchmark actual casi no prueba. Si el benchmark de la
Fase 14 muestra otra cosa, el default vuelve a `vector` sin tocar código.
Min-max por lista es sensible a la distribución de scores de cada consulta;
alternativas (z-score, calibración) se prueban cuando haya un reranker con el
que compararlas (Fase 6).

## ADR-023: Reranker local disponible, apagado por default

**Decisión.** `Retriever` acepta un `Reranker` (cross-encoder
`bge-reranker-v2-m3`, local) y un `pool`. Sobre el vector con pool 50 sube
nDCG@8 de 0,58 a 0,67 y negación de 0,50 a 0,70, pero cuesta 3,7 s por
pregunta en CPU/MPS y con pool 30 la ganancia casi desaparece porque los
artículos que hay que rescatar están en las posiciones 30 a 50. Encima de la
reescritura de la pregunta (ADR-024) no mejora. Queda apagado por default
(`LEGAL_AI_RERANKER_MODEL` vacío) y disponible con `--rerank --pool N`.

**Alternativas.** Cohere Rerank por API: pendiente, sin clave. Pool 100:
más latencia sin evidencia de ganancia adicional.

## ADR-024: Reescritura de la pregunta con Claude, con caché y multi-query, como default

**Decisión.** Antes de buscar, Sonnet 5 reformula la pregunta con el
vocabulario de la ley (salida estructurada `query` + `terms`). Se busca con
la reescritura y con la pregunta original, y se fusionan por RRF
(`multi-query`). Las reescrituras se cachean en `data/cache/rewrites/` por
pregunta y modelo. Default: `hybrid + rewrite(claude-sonnet-5) + multi`.

**Por qué.** Es la única técnica que cerró la brecha de vocabulario medida en
el debug (art. 12: fuera del top-8 → posición 2; 242/244: fuera de los 200 →
top-8). hit@8 0,80 → 0,86, recall 0,72 → 0,84 sobre 44 preguntas. Costo
$0,004 y 2,7 s por reescritura con Sonnet 5.

**Por qué multi-query.** La reescritura sola pierde preguntas "puntero" ("¿qué
ley sustituyó el 92 bis?") al abstraerlas; conservar la pregunta original las
recupera. RRF entre dos listas cuesta MRR (0,68 → 0,64 con Opus); se acepta
porque el modelo lee los 8 fragmentos.

**Consecuencias.** Sin `ANTHROPIC_API_KEY` el sistema degrada a híbrido sin
reescritura y lo dice. La reescritura es un punto de fallo nuevo (errores
transitorios de la API: se reintenta 5 veces) y una fuente de sesgo: si el
modelo "adivina" la respuesta al reformular, la búsqueda se sesga hacia ella;
el prompt le prohíbe responder y el benchmark lo vigila.

## ADR-025: Un juez LLM mide el sostén de cada afirmación; la abstención se mide aparte

**Decisión.** La calidad de la generación se mide con tres números
independientes: (1) abstención correcta en preguntas sin respuesta y
abstención falsa en preguntas con el artículo esperado en el contexto, que
salen de `insufficient_evidence` sin ningún modelo; (2) citas fuera del
contexto, que es un chequeo de conjuntos; (3) sostén de cada afirmación por
los fragmentos que cita, dictado por Sonnet 5 como juez con salida
estructurada (`supported | partial | unsupported`), más un booleano de si el
conjunto responde la pregunta.

**Por qué un juez y no Ragas/DeepEval.** El juez propio ve exactamente los
fragmentos citados por id, en castellano, con instrucciones estrictas sobre
números y plazos; el prompt y el modelo están fijos y versionados, así que
dos corridas son comparables. Ragas queda como contraste en la Fase 14 si
hace falta.

**Límites.** El juez no sabe derecho: sólo compara afirmación con fragmento.
Una afirmación sostenida por un fragmento equivocado (versión histórica, otra
norma) sale "supported". Por eso `cited_expected` y la revisión humana (Fase
14) existen. Costo del juez: unos 4.000 tokens por respuesta.

## ADR-026: Versiones históricas reconstruidas desde las leyes modificatorias, con filtro por fecha en el índice

**Decisión.** Las versiones intermedias no se piden a Infoleg (no existen):
se reconstruyen desde el texto que cada ley modificatoria transcribe. Se
guardan como `version_kind = reconstructed`, `status = historico`, con rango
de vigencia encadenado. El índice contiene todas las versiones con texto y la
búsqueda filtra por `as_of`; por default sólo lo vigente hoy.

**Validación.** La última reconstruida de cada artículo debe coincidir con el
texto vigente: 70/76 en la LCT. Ese número es la medida de calidad de la
reconstrucción y se recalcula en cada parseo.

**Límites.** Sólo cubre cambios cuya ley modificatoria está en el corpus y
usa la forma "sustitúyese… por el siguiente:". Derogaciones sin texto y
modificaciones parciales ("sustitúyese el inciso c)") no generan versión.
El `as_of` extraído por el reescritor es una interpretación del modelo; el
usuario puede fijarlo explícitamente.

## ADR-027: Referencias entre artículos en Postgres; expansión de un salto, opcional

**Decisión.** Las citas "artículo N" dentro de los textos se guardan como
aristas en `article_references`. El retriever puede expandir con vecinos de
un salto. Medido: recall +0,02, hit −0,02. Queda apagado por default y
disponible para el agente y para GraphRAG multi-salto si el benchmark de la
Fase 14 muestra preguntas que lo necesiten. Neo4j no se justifica con un
salto y 5.184 aristas.

## ADR-028: Un mismo juego de herramientas para el agente y para el MCP server

**Decisión.** `legal_ai.tools.Toolbox` implementa cuatro operaciones
(`search_laws`, `get_article`, `get_law_version`, `find_related_legislation`)
sobre el retriever y Postgres. El agente (Pydantic AI, Claude) y el servidor
MCP (`legal-ai mcp`, stdio) las exponen sin lógica propia. El agente decide
qué buscar y qué leer; devuelve el mismo `GroundedAnswer` que el pipeline
fijo, y sus fuentes se validan contra lo que las herramientas devolvieron.

**Por qué.** Comparar agente contra pipeline fijo sólo tiene sentido si usan
el mismo índice y el mismo esquema de respuesta; y un cliente MCP externo
(Claude Desktop, Claude Code) tiene que ver exactamente lo que ve el agente.

**Consecuencias.** El agente cuesta más llamadas por pregunta (se mide en
`bench agent`) y puede fallar en la validación de salida; el benchmark
registra esos errores en vez de cortarse.

## ADR-029: Observabilidad: JSONL siempre, OTLP opcional, panel "por debajo del capó" en la UI

**Decisión.** Cada request escribe sus spans a `data/traces/spans.jsonl`;
`legal-ai traces` los resume (requests, p50/p95 por etapa, tokens, costo).
Con `LEGAL_AI_OTLP_ENDPOINT` los mismos spans van a cualquier backend OTLP;
`docker-compose.observability.yml` levanta Arize Phoenix como ejemplo (un
contenedor). La UI muestra por cada pregunta el plan (reescritura, fecha),
los candidatos con score y origen, la latencia por etapa, tokens y costo, y
los spans crudos. Langfuse queda como opción documentada, no como
dependencia: su stack self-hosted (Postgres, ClickHouse, Redis, MinIO) no se
justifica para un usuario.

## ADR-030: Descomposición de la pregunta con fusión por cuota

**Decisión.** El reescritor devuelve `subqueries` (0 a 3) cuando la pregunta
abarca varios institutos o está en negativo y la ley trata cada excepción en
un artículo distinto. Se busca con cada una y el top-k se arma reservando dos
lugares por sub-búsqueda y llenando el resto con el ranking principal
(`quota_merge`), en vez de fusionar todo por RRF. Activado por default.

**Por qué cuota y no RRF.** RRF promedia posiciones: con cinco listas, el
primer resultado de una sub-búsqueda queda detrás de los primeros de las
listas principales, que ya estaban. La cuota garantiza que cada instituto
esté representado en el contexto que ve el modelo. Medido sobre las 7
preguntas que se descomponen: nDCG 0,63 (RRF) contra 0,76 (cuota), con el
mismo hit. En el agregado, negación pasó de 0,67/0,57 a 1,00/0,82.

**Costo.** Una sub-búsqueda es una consulta más a Postgres (unos 30 ms cada
una); el reescritor ya devolvía el campo, así que no hay llamadas extra al
LLM.

## ADR-031: Las derogaciones de otras normas cierran la vigencia

**Decisión.** El parser extrae "Derógase el artículo N de la Ley X" y
"Derógase la Ley X" de los textos del corpus y marca las versiones afectadas
como `derogado` con `effective_until` en la fecha del Boletín de la norma que
deroga. Antes sólo se sabía de una derogación si Infoleg la anotaba dentro del
artículo derogado.

**Consecuencias.** 90 versiones cambiaron de estado, entre ellas todas las de
la Ley 25.250 (deuda abierta desde la Fase 4) y nueve artículos de la LCT
derogados por la Ley 27.802. El índice por defecto deja de ofrecerlas y
siguen disponibles con `as_of` o `historical`. Una pregunta del benchmark
(b25) quedó expuesta como mal etiquetada: pedía como derecho vigente un
recargo de una ley derogada en 2023.

**Límite.** Sólo se reconocen las formas directas. "Derógase el último párrafo
del artículo 29" (derogación parcial) y "Derógase toda disposición que se
oponga" quedan afuera a propósito: no se puede saber qué texto sobrevive.

