from sqlalchemy import inspect, text

from legal_ai.db.schema import metadata


def test_migration_creates_tables_and_extensions(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert {"documents", "articles", "article_versions", "relations", "history", "chunks"} <= names
    assert set(metadata.tables) <= names
    with db_engine.connect() as conn:
        extensions = {r[0] for r in conn.execute(text("SELECT extname FROM pg_extension"))}
        assert {"vector", "pg_search"} <= extensions
        indexes = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'")
            )
        }
        assert "chunks_embedding_hnsw" in indexes
