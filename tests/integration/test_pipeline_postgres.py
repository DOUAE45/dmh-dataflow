"""Pipeline complet sur le vrai PostgreSQL.  Lancement : pytest -m integration"""

from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from dmh.contracts import RunStatus
from dmh.db import repository
from dmh.db.connection import get_engine
from dmh.ingestion.datasets import load_dataset_config
from dmh.pipeline.runner import run_pipeline

pytestmark = pytest.mark.integration


def test_demo_run_roundtrip(monkeypatch, tmp_path):
    # Jeu de données à part (table data_it_demo_sales) : la vraie base peut déjà contenir
    # la démo, dont les order_id seraient alors rejetés comme « déjà chargés ».
    yaml = Path("config/datasets/demo_sales.yaml").read_text(encoding="utf-8")
    (tmp_path / "it_demo_sales.yaml").write_text(
        yaml.replace("name: demo_sales", "name: it_demo_sales"), encoding="utf-8"
    )
    monkeypatch.setenv("DMH_DATASETS_DIR", str(tmp_path))
    monkeypatch.setenv("DMH_DATA_DIR", str(tmp_path))
    engine = get_engine()
    table = repository.data_table(load_dataset_config("it_demo_sales").schema)

    result = run_pipeline("data/sample/demo_sales.csv", "it_demo_sales", "test")
    rerun = None
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

        rerun = run_pipeline("data/sample/demo_sales.csv", "it_demo_sales", "test")
        assert (rerun.rows_valid, rerun.rows_rejected) == (0, 20)
    finally:
        run_ids = [r.run_id for r in (result, rerun) if r]
        with engine.begin() as conn:
            table.drop(conn, checkfirst=True)
            conn.execute(
                delete(repository.runs_table).where(repository.runs_table.c.run_id.in_(run_ids))
            )
