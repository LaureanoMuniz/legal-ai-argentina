# Arquitectura

## Principio

Cada etapa del pipeline es una función explícita con entrada y salida
inspeccionables. No hay cadenas mágicas: se puede correr el retrieval sin el
LLM, el LLM con un contexto fijo, o el parser sobre un HTML suelto.

```
pregunta
  → (opcional) reescritura / expansión
  → retrieval: vector | BM25 | híbrido (RRF)
  → (opcional) reranking
  → construcción de contexto (artículos + metadata + versión)
  → LLM con structured output
  → respuesta + claims + citas (document_id:artículo:versión)
  → traza OTel → Langfuse
  → evaluación (benchmark automático + humana)
```

## Fuente de datos

Infoleg publica en datos.jus.gob.ar tres tablas (CSV, CC BY 4.0, mensual):

| Tabla | Contenido |
|---|---|
| `base-infoleg-normativa-nacional` | Una fila por norma: `id_norma`, tipo, número, organismo, fechas, títulos, resumen, links a `norma.htm` (texto original) y `texact.htm` (texto actualizado), contadores `modificada_por` / `modifica_a`. |
| `normas-modificatorias` | Aristas `id_norma_modificatoria → id_norma_modificada`. |
| `normas-modificadas` | Las mismas aristas desde el otro lado. |

Los textos **no** están en el CSV; se descargan de
`servicios.infoleg.gob.ar/infolegInternet/anexos/<rango>/<id>/{norma,texact}.htm`.
El servidor exige un `User-Agent` de navegador (devuelve 403 sin él). El HTML
es regular: `<p><b>Art. 92 bis.</b>` y notas inline de modificación:

```
(Artículo sustituido por art. 91 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: ...)
(Artículo derogado por art. 207 de la Ley N° 27.802 B.O. 6/3/2026. ...)
(Artículo incorporado por art. ... de la Ley N° ... B.O. ...)
```

Limitaciones que condicionan el diseño:

- No hay columna de estado (vigente/derogada). Se infiere de las notas.
- No hay versiones históricas consolidadas. Infoleg guarda el original, el
  vigente, y la lista de normas modificatorias. Las versiones intermedias hay
  que reconstruirlas (Fase 9).
- La página de vínculos (`verVinculos.do?modo=2&id=`) lista las
  modificatorias con fecha y descripción; es la fuente para las aristas con
  contexto que el CSV no tiene.
- El "texto original" de la LCT (`norma.htm` de 25552) es la ley aprobatoria
  de 1974 (3 artículos). El cuerpo vigente es el texto ordenado por Decreto
  390/76, cuyo `norma.htm` sí trae los 277 artículos como anexo. El manifest lo
  declara con `original_from` y el parser usa ese anexo como versión
  `original` (ADR-015).
- Al final de `texact.htm` hay una sección "Antecedentes Normativos" con el
  historial de sustituciones por artículo (norma, artículo, fecha B.O.), sin
  los textos anteriores. Se guarda en `history.jsonl` como índice para la
  Fase 9.
- Las leyes modificatorias citan adentro el texto de los artículos que
  reemplazan ("Sustitúyese el artículo 245 por el siguiente: 'Artículo 245.
  — ...'"). El parser detecta la cita por la línea introductoria con ":" o por
  el cambio de estilo del encabezado ("ARTICULO" anfitrión vs "Artículo"
  citado) y la deja en el cuerpo del artículo anfitrión.
- Las dos copias de un mismo texto (anexo del Decreto 390/76 y `texact.htm`
  de la LCT) difieren en transcripción ("rigen"/"rige", puntuación). La
  igualdad exacta no sirve para detectar cambios: se usa similitud
  normalizada con umbral 0,9 y las notas de Infoleg como autoridad.
- Una nota puede derogar un capítulo entero ("Capítulo VIII derogado por...")
  y estar colgada del último artículo numerado anterior, porque el capítulo
  derogado tenía artículos sin número (Ley 24.576). Solo se propaga si el
  número de capítulo coincide con el del artículo que la porta.

## Layout de datos

`data/cache/` guarda lo que es caro de recalcular y no es salida de
ningún paso: los embeddings por `(modelo, sha256 del texto)`. Vive fuera de
`data/processed/`, que el parser borra y regenera entero en cada corrida.

```
data/raw/infoleg/
  catalog/<YYYY-MM-DD>/            los 3 ZIP tal cual se bajaron + manifest.json (sha256, url, fetched_at)
  normas/<id_norma>/
    norma.htm                      texto original
    texact.htm                     texto actualizado (si existe)
    vinculos_modifica.htm          modo=1
    vinculos_modificada_por.htm    modo=2
    meta.json                      url, fetched_at, http status, sha256
data/processed/<corpus>/
  resolved.json            manifest resuelto a id_norma (fecha de catálogo, motivo)
  documents.jsonl          una norma por línea, con lista de (organismo, número)
  articles.jsonl           identidad de cada artículo y su jerarquía
  article_versions.jsonl   texto por versión (original | current) con vigencia
  relations.jsonl          aristas con evidencia (infoleg_vinculos | texact_note)
  history.jsonl            eventos de "Antecedentes Normativos" por artículo
  parse_report.json        conteos y advertencias por norma
```

Reglas: `raw` nunca se reescribe salvo `--force`; `processed` se regenera
completo con cada corrida del parser. Todo archivo trae `fetched_at` y hash.

## Corpus manifest

`corpus/laboral.yaml` declara qué entra y por qué, por número de norma, no por
`id_norma`. El `id_norma` se resuelve contra el catálogo:

```yaml
name: laboral
description: Ley de Contrato de Trabajo y su entorno normativo
seeds:
  - {tipo: Ley, numero: 20744, why: "núcleo del corpus"}
  - {tipo: Ley, numero: 24013, why: "Ley de Empleo: registración, multas"}
  - {tipo: Ley, numero: 25323, why: "agravamiento indemnizatorio"}
  - {tipo: Ley, numero: 25877, why: "ordenamiento laboral 2004"}
  - {tipo: Ley, numero: 27742, why: "Ley Bases 2024: reforma laboral"}
  - {tipo: Ley, numero: 27802, why: "reforma laboral 2026"}
expand:
  modificatorias_de_seeds: true    # incluir toda norma que modifique una seed
  max_depth: 1
```

## Modelo de datos

Dos ideas centrales: **el artículo es la unidad jurídica**, y **cada artículo
tiene versiones**. El chunk es la unidad de retrieval y apunta a una versión.

```
documents            una norma (id_norma de Infoleg)
document_relations   aristas modifica / deroga / reglamenta / complementa
articles             un artículo dentro de una norma (identidad estable: "92 bis")
article_versions     texto de un artículo en un rango de vigencia
chunks               unidad indexada: texto + prefijo de contexto + embedding + BM25
```

### documents

| campo | origen |
|---|---|
| `id_norma` (PK) | CSV |
| `tipo_norma`, `numero_norma`, `clase_norma`, `organismo_origen` | CSV |
| `fecha_sancion`, `fecha_boletin`, `numero_boletin`, `pagina_boletin` | CSV |
| `titulo_resumido`, `titulo_sumario`, `texto_resumido` | CSV |
| `url_original`, `url_actualizado` | CSV |
| `numeros`, `organismos` | listas: las resoluciones conjuntas tienen una fila por firmante |
| `has_original_text`, `has_current_text` | derivado |
| `original_source_document_id` | id de la norma de la que se toma el `original` (229909 para la LCT) |
| `front_matter` | encabezado y preámbulo (VISTO / CONSIDERANDO) antes del primer artículo |

### document_relations

| campo | nota |
|---|---|
| `source_id`, `target_id` | ids de Infoleg |
| `kind` | `modifies` (CSV) y, cuando el parser lo detecta, `repeals`, `substitutes_article`, `incorporates_article`, `regulates` |
| `article_number` | si la relación es a nivel artículo |
| `evidence` | de dónde salió: `infoleg_csv`, `infoleg_vinculos`, `texact_note` |

### articles

| campo | nota |
|---|---|
| `id` | `<id_norma>:<article_number>` normalizado, ej. `25552:92bis` |
| `document_id` | |
| `article_number` | como aparece: `92 bis` |
| `ordinal` | posición en el texto, para ordenar `bis`/`ter` |
| `heading` | epígrafe del artículo, ej. `Período de prueba` |
| `titulo`, `capitulo`, `seccion` | jerarquía en la que está |

### article_versions

| campo | nota |
|---|---|
| `id` | |
| `article_id` | |
| `version_kind` | `original` (de `norma.htm`), `current` (de `texact.htm`), `reconstructed` (Fase 9) |
| `text` | |
| `status` | `vigente`, `derogado`, `sustituido` |
| `effective_from` | fecha B.O. de la norma que introdujo este texto; para `original`, fecha B.O. de la norma |
| `effective_until` | `null` si vigente; fecha B.O. de la sustitución/derogación si no |
| `modified_by_document_id`, `modified_by_article` | de la nota inline |
| `text_with_notes` | texto tal como está en Infoleg, con las notas |
| `source_document_id`, `source_url` | de dónde se leyó el texto |
| `similarity_to_original` | similitud normalizada entre `current` y `original` |
| `unchanged_from_original` | `true` si no hay nota fechada y la similitud es ≥ 0,9 |
| `text_sha256` | |

Parsear `norma.htm` y `texact.htm` por separado da dos versiones de cada
artículo desde la Fase 2. Cuando coinciden, es la misma versión con
`effective_from` original. Cuando difieren, la actual tiene la nota de
modificación con la fecha. Eso es la semilla del retrieval temporal.

### chunks

| campo | nota |
|---|---|
| `id` | |
| `article_version_id` | |
| `chunk_index` | casi siempre 0: un artículo = un chunk. Artículos largos se parten por inciso. |
| `text` | |
| `context_prefix` | "Ley 20.744, Título X, Capítulo IV, Art. 245 (Indemnización por antigüedad), vigente desde ..." (contextual retrieval) |
| `token_count` | |
| `embedding` | `vector(1024)` con índice HNSW |
| índice BM25 | `pg_search` sobre `context_prefix || text` |

Regla del baseline (ADR-018): por artículo se indexa una sola versión, la
`current` si existe y si no la `original`, sólo si está `vigente`, tiene texto
y no pertenece a un anexo. El texto embebido es `context_prefix + "\n" + text`;
artículos de más de 2.500 caracteres se parten por inciso. El embedder es
intercambiable (ADR-019): `bge-m3` es el baseline y `HashingEmbedder` (feature
hashing, 1024 dimensiones, sin descarga) es el fallback de tests y el control
del benchmark.

## Retrieval

Todas las variantes devuelven la misma estructura: lista de
`(chunk_id, score, rank, retriever)` para poder fusionar y trazar.

- **vector** (Fase 3, `retrieval/vector.py`): coseno sobre el índice HNSW.

  ```sql
  SELECT id, version_id, article_id, document_id, context_prefix, text,
         1 - (embedding <=> CAST(:q AS vector)) AS score
  FROM chunks
  WHERE embedding IS NOT NULL
  ORDER BY embedding <=> CAST(:q AS vector)
  LIMIT :k
  ```
- **bm25** (Fase 5, `retrieval/bm25.py`): índice `chunks_bm25` de pg_search
  sobre `embed_text`, tokenizer default con stemmer español (migración 0002).

  ```sql
  SELECT id, version_id, article_id, document_id, context_prefix, text,
         paradedb.score(id) AS score
  FROM chunks
  WHERE id @@@ paradedb.match('embed_text', :q, conjunction_mode => false)
  ORDER BY score DESC, id
  LIMIT :k
  ```
- **híbrido** (`retrieval/fusion.py`): 24 candidatos de cada fuente; el modo
  `hybrid` combina scores normalizados por min-max (`alpha · vector +
  (1 - alpha) · bm25`, alpha 0,8); el modo `rrf` usa Reciprocal Rank Fusion
  (k = 60). Los dos en Python, explícitos. `hybrid` es el default (ADR-022).
- **dedupe por artículo** (opcional): pool de 3k, primer chunk de cada
  artículo, corte en k. Medido sin efecto en la Fase 5; apagado por default.
- **reranking**: cross-encoder sobre los top-N del híbrido.
- **filtros temporales**: `effective_from <= fecha AND (effective_until IS NULL OR effective_until > fecha)`.

## Generación

Claude Opus 5 con `output_config.format` (structured outputs). Esquema:

```json
{
  "answer": "...",
  "claims": [{"claim": "...", "sources": ["25552:245@current"]}],
  "confidence": "high|medium|low",
  "insufficient_evidence": false
}
```

Cada `source` referencia `article_id@version`. Un claim sin fuente en el
contexto es un fallo medible (Fase 8).

## Observabilidad

Instrumentación con OpenTelemetry usando las GenAI semantic conventions
(`gen_ai.*`). Un span por etapa: `query_rewrite`, `retrieval.vector`,
`retrieval.bm25`, `fusion`, `rerank`, `context`, `llm`, `parse_output`. Los
candidatos y scores van como atributos del span.

Desde la Fase 3 cada request escribe sus spans en `data/traces/spans.jsonl`
(un exportador propio, una línea JSON por span) y además a un endpoint OTLP
HTTP si `LEGAL_AI_OTLP_ENDPOINT` está definido (ADR-020). El stack de Langfuse
self-hosted, que guarda datasets, scores y etiquetas de evaluadores humanos,
es tarea de la Fase 13; la instrumentación no cambia.

## Evaluación

- **Retrieval**: recall@k, precision@k, MRR, nDCG@k y hit@k contra
  `eval/benchmark.jsonl` (50 preguntas, 8 categorías, `expected_articles`,
  `as_of` para las temporales), a nivel artículo, por categoría (ADR-021).
  `legal-ai bench run` escribe el reporte en `experiments/`.
- **Generación**: claims soportados / total, abstención correcta, exactitud
  de versión; juez LLM propio con structured output, contrastado con Ragas.
- **Humana**: etiquetas `correct | partially_correct | incorrect | unsupported
  | wrong_source | wrong_version | incomplete` + comentario, guardadas como
  dataset y convertibles a tests de regresión.
- **Sistema**: latencia p50/p95 por etapa, tokens, costo.

Cada experimento escribe `experiments/<fecha>-<nombre>.json` con la config
completa y las métricas.

## Infra local

`docker-compose.yml`: `postgres` (imagen ParadeDB, incluye pgvector y
`pg_search`) en el puerto 5433 del host para no chocar con una Postgres local.
Langfuse se agrega en la Fase 13. En macOS el runtime de contenedores es
Colima (Docker Engine + Compose sin Docker Desktop). Modelos open-weight corren en el host con `sentence-transformers`.
