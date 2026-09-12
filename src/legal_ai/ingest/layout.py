from datetime import date
from pathlib import Path


class RawLayout:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "raw" / "infoleg"

    def catalog_dir(self, snapshot_date: date) -> Path:
        return self.root / "catalog" / snapshot_date.isoformat()

    def catalog_dates(self) -> list[date]:
        catalog_root = self.root / "catalog"
        if not catalog_root.exists():
            return []
        dates: list[date] = []
        for child in catalog_root.iterdir():
            if not child.is_dir():
                continue
            try:
                dates.append(date.fromisoformat(child.name))
            except ValueError:
                continue
        return sorted(dates)

    def norm_dir(self, id_norma: int) -> Path:
        return self.root / "normas" / str(id_norma)


class ProcessedLayout:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "processed"

    def corpus_dir(self, name: str) -> Path:
        return self.root / name

    def resolved_path(self, name: str) -> Path:
        return self.corpus_dir(name) / "resolved.json"
