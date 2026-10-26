"""Pipeline complet sur le vrai PostgreSQL.  Lancement : pytest -m integration"""

import pytest
from sqlalchemy import delete, func, select

from dmh.contracts import RunStatus
from dmh.db import repository
from dmh.db.connection import get_engine
from dmh.ingestion.datasets import load_dataset_config
from dmh.pipeline.runner import run_pipeline

pytestmark = pytest.mark.integration


def test_demo_run_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("DMH_DATA_DIR", str(tmp_path))
    engine = get_engine()
    table = repository.data_table(load_dataset_config("demo_sales").schema)

    result = run_pipeline("data/sample/demo_sales.csv", "demo_sales", "test")
    try:
        assert result.status is RunStatus.SUCCESS, result.error
        with engine.connect() as conn:
            loaded = conn.execute(
                select(func.count()).select_from(table).where(table.c._run_id == result.run_id)
            ).scalar()
        assert loaded == result.rows_valid == 12

        saved = repository.get_run(result.run_id)
        assert saved.quality.missing_by_column["quantity"] == 1
        assert saved.started_at.tzinfo is not None
    finally:
        with engine.begin() as conn:
            conn.execute(delete(table).where(table.c._run_id == result.run_id))
            conn.execute(
                delete(repository.runs_table).where(repository.runs_table.c.run_id == result.run_id)
            )
