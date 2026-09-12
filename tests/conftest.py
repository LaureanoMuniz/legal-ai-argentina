import csv
import io
import zipfile
from pathlib import Path

import pytest

NORM_COLUMNS = [
    "id_norma",
    "tipo_norma",
    "numero_norma",
    "clase_norma",
    "organismo_origen",
    "fecha_sancion",
    "numero_boletin",
    "fecha_boletin",
    "pagina_boletin",
    "titulo_resumido",
    "titulo_sumario",
    "texto_resumido",
    "observaciones",
    "texto_original",
    "texto_actualizado",
    "modificada_por",
    "modifica_a",
]
RELATION_COLUMNS = [
    "id_norma_modificatoria",
    "id_norma_modificada",
    "tipo_norma",
    "nro_norma",
    "clase_norma",
    "organismo_origen",
    "fecha_boletin",
    "titulo_sumario",
    "titulo_resumido",
]


def write_csv_zip(
    path: Path, inner_name: str, columns: list[str], rows: list[dict[str, str]]
) -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, ("﻿" + buffer.getvalue()).encode("utf-8"))
    return path


LCT = {
    "id_norma": "25552",
    "tipo_norma": "Ley",
    "numero_norma": "20744",
    "organismo_origen": "HONORABLE CONGRESO DE LA NACION ARGENTINA",
    "fecha_sancion": "1974-09-05",
    "numero_boletin": "23003",
    "fecha_boletin": "1974-09-27",
    "pagina_boletin": "2",
    "titulo_resumido": "REGIMEN",
    "titulo_sumario": "LEY DE CONTRATO DE TRABAJO",
    "texto_resumido": "REGIMEN DEL CONTRATO DE TRABAJO.",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/norma.htm",
    "texto_actualizado": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/texact.htm",
    "modificada_por": "263",
    "modifica_a": "21",
}
LEY_BASES = {
    "id_norma": "401266",
    "tipo_norma": "Ley",
    "numero_norma": "27742",
    "fecha_sancion": "2024-06-27",
    "fecha_boletin": "2024-07-08",
    "titulo_sumario": "BASES Y PUNTOS DE PARTIDA PARA LA LIBERTAD DE LOS ARGENTINOS",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/400000-404999/401266/norma.htm",
    "modificada_por": "116",
    "modifica_a": "38",
}
DECRETO_390 = {
    "id_norma": "229909",
    "tipo_norma": "Decreto",
    "numero_norma": "390",
    "fecha_sancion": "1976-05-13",
    "fecha_boletin": "1976-05-21",
    "titulo_sumario": "CONTRATO DE TRABAJO",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/225000-229999/229909/norma.htm",
}
RESOLUCION_X = {
    "id_norma": "999001",
    "tipo_norma": "Resolución",
    "numero_norma": "15",
    "fecha_boletin": "2022-11-11",
    "titulo_sumario": "ALGO",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/995000-999999/999001/norma.htm",
}
LEY_SN = {
    "id_norma": "183290",
    "tipo_norma": "Ley",
    "numero_norma": "S/N",
    "fecha_boletin": "1853-05-25",
}
LEY_1_A = {
    "id_norma": "1001",
    "tipo_norma": "Ley",
    "numero_norma": "1",
    "fecha_sancion": "1862-09-01",
}
LEY_1_B = {
    "id_norma": "1002",
    "tipo_norma": "Ley",
    "numero_norma": "1",
    "fecha_sancion": "1900-01-01",
}

FIXTURE_NORMS = [LCT, LEY_BASES, DECRETO_390, RESOLUCION_X, LEY_SN, LEY_1_A, LEY_1_B]
FIXTURE_RELATIONS = [
    {
        "id_norma_modificatoria": "401266",
        "id_norma_modificada": "25552",
        "tipo_norma": "Ley",
        "nro_norma": "20744",
        "fecha_boletin": "1974-09-27",
    },
    {
        "id_norma_modificatoria": "229909",
        "id_norma_modificada": "25552",
        "tipo_norma": "Ley",
        "nro_norma": "20744",
        "fecha_boletin": "1974-09-27",
    },
    {
        "id_norma_modificatoria": "999001",
        "id_norma_modificada": "25552",
        "tipo_norma": "Ley",
        "nro_norma": "20744",
        "fecha_boletin": "1974-09-27",
    },
    {
        "id_norma_modificatoria": "25552",
        "id_norma_modificada": "1001",
        "tipo_norma": "Ley",
        "nro_norma": "1",
        "fecha_boletin": "",
    },
]


@pytest.fixture
def norms_zip(tmp_path: Path) -> Path:
    return write_csv_zip(
        tmp_path / "normas.zip", "base-infoleg-normativa-nacional.csv", NORM_COLUMNS, FIXTURE_NORMS
    )


@pytest.fixture
def relations_zip(tmp_path: Path) -> Path:
    return write_csv_zip(
        tmp_path / "modificatorias.zip",
        "base-complementaria-infoleg-normas-modificatorias.csv",
        RELATION_COLUMNS,
        FIXTURE_RELATIONS,
    )
