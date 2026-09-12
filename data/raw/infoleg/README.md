# data/raw/infoleg

Descargas inmutables. Nada acá se edita a mano. Se regenera con:

    uv run legal-ai ingest catalog
    uv run legal-ai ingest resolve laboral
    uv run legal-ai ingest fetch laboral

- `catalog/<fecha>/`: los tres ZIP de datos.jus.gob.ar + `manifest.json` (sha256, tamaño, URL, fecha).
- `normas/<id_norma>/`: `norma.htm` (texto original), `texact.htm` (texto actualizado, si Infoleg lo tiene),
  `vinculos_modifica.htm`, `vinculos_modificada_por.htm`, `meta.json` (URL, status, sha256, fecha por archivo).
