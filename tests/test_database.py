from pathlib import Path

from src.database import Database


def test_database_uses_explicit_db_path(tmp_path: Path) -> None:
    db_path = tmp_path / "explicit.db"

    db = Database(db_path=db_path)
    db.create_job("isolated explicit database")

    assert db_path.exists()


def test_database_uses_runtime_db_path_env(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "env.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    db = Database()
    db.create_job("isolated env database")

    assert db_path.exists()
