import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from dmh.contracts import RunStatus
from dmh.db import repository
from dmh.ingestion.datasets import load_dataset_config
from dmh.pipeline.runner import run_pipeline

SAMPLE = "data/sample/demo_sales.csv"


@pytest.fixture
def engine():
    # SQLite en mémoire : teste l'orchestration sans PostgreSQL.
    return create_engine("sqlite://", poolclass=StaticPool)


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("DMH_DB_PASSWORD", "unused")
    monkeypatch.setenv("DMH_DATA_DIR", str(tmp_path))


def test_successful_run_stores_rows_and_history(engine, tmp_path):
    result = run_pipeline(SAMPLE, "demo_sales", "test", engine=engine)

    assert result.status is RunStatus.SUCCESS, result.error
    assert (result.rows_read, result.rows_valid, result.rows_rejected) == (20, 12, 8)
    assert result.is_demo

    table = repository.data_table(load_dataset_config("demo_sales").schema)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(table)).scalar() == 12

    saved = repository.get_run(result.run_id, engine=engine)
    assert saved.status is RunStatus.SUCCESS
    assert saved.quality.score == 60.0
    assert len(saved.quality.issues) == len(result.quality.issues)

    assert list((tmp_path / "raw").iterdir())[0].name == f"{result.run_id}_demo_sales.csv"
    assert len(list((tmp_path / "quarantine").iterdir())) == 1


def test_missing_file_is_recorded_as_failed(engine):
    result = run_pipeline("absent.csv", "demo_sales", "test", engine=engine)

    assert result.status is RunStatus.FAILED
    assert "FileNotFoundError" in result.error
    assert repository.list_runs(engine=engine)[0].status is RunStatus.FAILED


def test_missing_required_column_fails_without_loading(engine, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("order_id,product\n1,Clavier\n")

    result = run_pipeline(bad, "demo_sales", "test", engine=engine)

    assert result.status is RunStatus.FAILED
    assert "SchemaMismatchError" in result.error
    assert result.quality.score == 0.0
    assert result.rows_valid == 0
