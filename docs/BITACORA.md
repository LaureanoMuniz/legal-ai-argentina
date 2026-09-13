# Bitácora de adversidades

Todo lo que salió mal, cómo se detectó, cómo se arregló y qué quedó aprendido.
En orden cronológico. Los números coinciden con las "Complicaciones" del
cuaderno (`cuaderno/index.html`); las entradas sin número aparecieron durante
las fases 8 a 15 y todavía no tienen lección.

| # | Fase | Qué pasó | Cómo se detectó | Qué se hizo | Lección |
|---|---|---|---|---|---|
| 1 | 1 | Los textos de las normas no están en el CSV de Infoleg, sólo las URLs | Leyendo el catálogo | Ingestion en dos etapas: catálogo (ZIP mensual) y textos (HTML por norma, con caché) | Separar índice de contenido |
| 2 | 1 | El servidor devuelve 403 sin `User-Agent` de navegador | Primer `curl` | UA de navegador, ritmo de 0,5 s, reintentos sólo en 429/5xx | Un 403 no se reintenta |
| 3 | 1 | No hay columna de vigente/derogado en el catálogo | Buscándola | El estado se deriva de las notas dentro del HTML, y el esquema lo marca como derivado | El contrato de datos real se documenta, no se asume |
| 4 | 1 | Infoleg no tiene versiones históricas consolidadas | Leyendo `texact.htm` | Modelo bitemporal por artículo; reconstrucción en Fase 9 | El problema "Temporal Misgrounding" existe porque la fuente no lo resuelve |
| 5 | 1 | Un filtro por tipo de norma dejaba afuera los topes indemnizatorios | Revisando las 134 normas excluidas | Se quitó el filtro; el corpus pasó de 266 a 931 normas (ADR-014) | Recall primero; filtrar con el benchmark |
| 6 | 1 | `id_norma` no es único: 4.489 repetidos (resoluciones conjuntas) | Cargando el catálogo | Se documentó; el resolver se queda con la última fila | Las claves de la fuente no son las de tu modelo |
| 7 | 2 | El "texto original" de la LCT tiene 3 artículos: el cuerpo está en el anexo del Decreto 390/76 | Golden file de la LCT | `original_from` en el manifest; `source_document_id` en cada versión (ADR-015) | Los textos ordenados son la unidad real |
| 8 | 2 | Las leyes modificatorias transcriben artículos y el parser los tomaba por propios (917 falsos encabezados) | Primera pasada sobre 933 normas | Detección de cita por línea con ":" y cambio de estilo; bajó a 48 | Documentos embebidos rompen parsers planos |
| 9 | 2 | Nota de "Capítulo VIII derogado" colgada del art. 89 propagó 44 derogaciones en vez de 16 | Golden file | Propagar sólo si el número de capítulo coincide | Eventos de contenedor ≠ eventos de artículo |
| 10 | 2 | Dos transcripciones del mismo texto (anexo vs actualizado): 120 falsos cambios | Comparación de versiones | Similitud normalizada ≥ 0,9 y autoridad de las notas (ADR-017) | Igualdad exacta casi nunca es la pregunta |
| 11 | 2 | Notas compuestas con paréntesis anidados | Art. 147 LCT | Un nivel de anidación, partición en eventos | Saber cuándo dejar el regex |
| 12 | 2 | Los anexos son 2.377 artículos y a veces duplican leyes enteras | Contando | Entran con identidad propia y marca `annex`; deduplicar se decide midiendo | Recall primero, otra vez |
| 13 | 2 | "Antecedentes Normativos" es un log sin payload | Leyendo el final de `texact.htm` | Se guarda como historial (321 eventos); es el índice de la Fase 9 | Event sourcing sin eventos completos |
| 14 | 3 | "role legal_ai does not exist": una Postgres de Homebrew escuchaba en el 5432 | Migración fallida | Contenedor en el 5433 | Cuando el error no cuadra, preguntate con quién hablás |
| 15 | 3 | Los derogados no se indexan y la pregunta del art. 28 no puede acertar | Benchmark de humo | Anotado como falla esperada hasta la Fase 9 | La deuda se deja visible |
| 16 | 3 | 80 segundos para embeber con hashing | `time` | Hipótesis: 9.055 UPDATE de a uno; pendiente medir | No inventar la causa |
| 17 | 3 | El vector siempre devuelve k candidatos: no sabe abstenerse | Preguntas sin respuesta | La abstención se mide en la generación | Retrieval y abstención son etapas distintas |
| 18 | 4 | Cero en todo el benchmark con hashing, sin error: la columna tenía vectores de otro modelo | Benchmark | Filtro `embedding_model = :model` y comandos que se niegan sin índice de ese modelo | El modelo es parte del esquema |
| 19 | 4 | La Ley 25.250, derogada entera, sigue vigente en el índice | Pregunta b32 | Seguimiento del parser: propagar `deroga` a nivel norma | Las derogaciones de norma no tienen nota por artículo |
| 20 | 4 | Una columna de vectores = un modelo a la vez | Comparando embedders | Caché en disco; tabla por modelo si hace falta | Diseñar para comparar |
| 21 | 5 | La hipótesis "BM25 arregla negación" era falsa | Benchmark | El stemmer no une renunciar/irrenunciabilidad; se pasó a reescritura | Sólo cuenta el benchmark, no la prueba a mano |
| 22 | 5 | RRF a pesos iguales empeora al vector | Barrido de pools y pesos | Fusión por scores normalizados con 0,8 al vector (ADR-022) | Una fuente débil diluye a la fuerte |
| 23 | 5 | Una pregunta más no es una victoria | 44 preguntas | Se adoptó por "no peor" y se dejó cómo volver atrás | Distinguir mejor de no peor |
| 24 | 5b | Un salto de línea del HTML no es un salto de línea: 1 de cada 4 epígrafes partidos | Leyendo un chunk | Saltos del fuente como espacios | HTML tiene semántica de espacios |
| 25 | 5b | El arreglo correcto rompió vínculos, 84 artículos y la jerarquía | Tests y diff del corpus | Una regla y un test por caso; un anexo falso de 15 artículos desapareció | Regenerar goldens y mirar el diff campo por campo |
| 26 | 5b | El bug era real y no movió las métricas | Benchmark tras el arreglo | Se dejó documentado como resultado | Calidad de datos ≠ calidad de retrieval |
| 27 | 5b | Un "Artículo 92 bis" citado se hizo pasar por artículo de la Ley 27.742 | Debug pregunta por pregunta | Si la línea anterior termina en ":" y nombra el artículo, es cita | La numeración esperada no prueba nada |
| 28 | 6 | El sondeo del reranker prometía 0,67 y el sistema dio 0,62 | Primera corrida real | Pool 50 sobre el vector, no 30 sobre el híbrido | El pool decide qué se puede rescatar |
| 29 | 7 | Reescribir la pregunta también pierde preguntas "puntero" | Benchmark | Multi-query: original + reescrita, fusionadas | No elegir cuando podés fusionar |
| 30 | 7 | Dos corridas murieron por errores transitorios de la API | Log | Caché de reescrituras y 5 reintentos | Una llamada de red por pregunta es un punto de fallo |
| 31 | 7 | `messages.parse` no acepta `cache_control` arriba | Primera llamada real | Va en el bloque `system` | Verificar el SDK instalado, no el recuerdo |
| 32 | 7 | La caché de embeddings vivía en `data/processed`, que el parser borra | 10 minutos de re-embebido | `data/cache/` | Lo caro de recalcular no vive en una salida descartable |
| 33 | 9 | Las versiones reconstruidas se calculaban y se perdían: la función no las agregaba a la lista | Re-parseo con 0 reconstruidas | `extend` explícito y test que lo verifica | Un test que mira sólo el retorno no ve la mutación que falta |
| 34 | 9 | La LCT de 1976 no tiene art. 92 bis: el "original" de un artículo incorporado no existe | Cadena de versiones | La cadena arranca en la primera reconstrucción | "Original" es relativo al texto ordenado |

Las entradas se agregan al final de cada fase, con la métrica que las hizo
visibles cuando la hubo.
