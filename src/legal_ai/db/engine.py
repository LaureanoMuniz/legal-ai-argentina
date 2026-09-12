from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parents[3]


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def _alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade_database(url: str) -> None:
    command.upgrade(_alembic_config(url), "head")


def ensure_database(url: str) -> None:
    target = make_url(url)
    maintenance = target.set(database="postgres")
    engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    engine.dispose()
