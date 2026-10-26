"""Lecture / écriture des exécutions et des données dans PostgreSQL.

Seul point d'accès à la base pour les autres modules (Streamlit, Airflow, métriques).

Tables :
  pipeline_runs   une ligne par exécution (statut, volumes, score, erreur)
  quality_issues  problèmes détectés, liés à une exécution
  data_<dataset>  lignes valides, avec _run_id pour savoir quelle exécution les a chargées
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Connection,
    Date,
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    insert,
    inspect,
    select,
)

from dmh.contracts import DatasetSchema, QualityIssue, QualityReport, RunResult, RunStatus
from dmh.db.connection import get_engine

metadata = MetaData()

runs_table = Table(
    "pipeline_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("dataset", String(64), nullable=False, index=True),
    Column("source_file", Text, nullable=False),
    Column("triggered_by", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("finished_at", DateTime(timezone=True)),
    Column("duration_seconds", Float),
    Column("rows_read", Integer, nullable=False, default=0),
    Column("rows_valid", Integer, nullable=False, default=0),
    Column("rows_rejected", Integer, nullable=False, default=0),
    Column("quality_score", Float),
    Column("duplicate_rows", Integer),
    Column("missing_by_column", JSON),
    Column("format_errors_by_column", JSON),
    Column("error", Text),
    Column("is_demo", Boolean, nullable=False, default=False),
)

issues_table = Table(
    "quality_issues",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "run_id",
        String(36),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("check_type", String(32), nullable=False),
    Column("column_name", Text),
    Column("row_count", Integer, nullable=False),
    Column("message", Text, nullable=False),
)

SQL_TYPES = {"int": BigInteger, "float": Float, "str": Text, "date": Date, "bool": Boolean}


def create_tables(engine: Engine | None = None) -> None:
    """Crée les tables de suivi si elles n'existent pas (sans effet sinon)."""
    metadata.create_all(engine or get_engine(), tables=[runs_table, issues_table])


def data_table(schema: DatasetSchema) -> Table:
    """Table des lignes valides d'un jeu de données (nom validé dans ingestion.datasets)."""
    columns = [Column(c.name, SQL_TYPES[c.dtype]) for c in schema.columns]
    return Table(
        f"data_{schema.name}",
        MetaData(),
        Column("_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
        Column("_run_id", String(36), nullable=False, index=True),
        Column("_loaded_at", DateTime(timezone=True), nullable=False),
        *columns,
    )


def existing_keys(conn: Connection, schema: DatasetSchema) -> dict[str, set]:
    """Valeurs déjà chargées pour chaque colonne `unique` (vide si la table n'existe pas encore).

    Toutes les valeurs sont lues en mémoire : suffisant pour les volumes du projet.
    """
    unique = [c.name for c in schema.columns if c.unique]
    if not unique or not inspect(conn).has_table(f"data_{schema.name}"):
        return {}
    table = data_table(schema)
    return {
        name: set(conn.execute(select(table.c[name]).distinct()).scalars()) - {None}
        for name in unique
    }


def store_valid_rows(conn: Connection, schema: DatasetSchema, df: pd.DataFrame, run_id: str) -> int:
    table = data_table(schema)
    table.create(conn, checkfirst=True)
    if df.empty:
        return 0
    rows = df[schema.column_names].copy()
    for spec in schema.columns:
        if spec.dtype == "date":
            rows[spec.name] = rows[spec.name].dt.date
    records = rows.astype(object).where(rows.notna(), None).to_dict("records")
    loaded_at = datetime.now(UTC)
    for record in records:
        record["_run_id"] = run_id
        record["_loaded_at"] = loaded_at
    conn.execute(insert(table), records)
    return len(records)


def save_run(conn: Connection, result: RunResult) -> None:
    """Insère ou remplace l'exécution et ses problèmes qualité."""
    quality = result.quality
    values = {
        "dataset": result.dataset,
        "source_file": result.source_file,
        "triggered_by": result.triggered_by,
        "status": str(result.status),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_seconds": result.duration_seconds,
        "rows_read": result.rows_read,
        "rows_valid": result.rows_valid,
        "rows_rejected": result.rows_rejected,
        "quality_score": quality.score if quality else None,
        "duplicate_rows": quality.duplicate_rows if quality else None,
        "missing_by_column": quality.missing_by_column if quality else None,
        "format_errors_by_column": quality.format_errors_by_column if quality else None,
        "error": result.error,
        "is_demo": result.is_demo,
    }
    updated = conn.execute(
        runs_table.update().where(runs_table.c.run_id == result.run_id).values(**values)
    ).rowcount
    if not updated:
        conn.execute(insert(runs_table).values(run_id=result.run_id, **values))

    conn.execute(delete(issues_table).where(issues_table.c.run_id == result.run_id))
    if quality and quality.issues:
        conn.execute(
            insert(issues_table),
            [
                {
                    "run_id": result.run_id,
                    "check_type": i.check,
                    "column_name": i.column,
                    "row_count": i.row_count,
                    "message": i.message,
                }
                for i in quality.issues
            ],
        )


def get_run(run_id: str, engine: Engine | None = None) -> RunResult | None:
    runs = _load_runs(select(runs_table).where(runs_table.c.run_id == run_id), engine)
    return runs[0] if runs else None


def list_runs(
    dataset: str | None = None, limit: int = 100, engine: Engine | None = None
) -> list[RunResult]:
    """Exécutions les plus récentes d'abord."""
    query = select(runs_table).order_by(runs_table.c.started_at.desc()).limit(limit)
    if dataset:
        query = query.where(runs_table.c.dataset == dataset)
    return _load_runs(query, engine)


def _load_runs(query, engine: Engine | None) -> list[RunResult]:
    with (engine or get_engine()).connect() as conn:
        rows = conn.execute(query).mappings().all()
        if not rows:
            return []
        ids = [r["run_id"] for r in rows]
        issues: dict[str, list[QualityIssue]] = {}
        for i in conn.execute(
            select(issues_table).where(issues_table.c.run_id.in_(ids)).order_by(issues_table.c.id)
        ).mappings():
            issues.setdefault(i["run_id"], []).append(
                QualityIssue(i["check_type"], i["column_name"], i["row_count"], i["message"])
            )
    return [_to_result(r, issues.get(r["run_id"], [])) for r in rows]


def _to_result(row, issues: list[QualityIssue]) -> RunResult:
    quality = None
    if row["quality_score"] is not None:
        quality = QualityReport(
            rows_total=row["rows_read"],
            missing_by_column=row["missing_by_column"] or {},
            duplicate_rows=row["duplicate_rows"] or 0,
            format_errors_by_column=row["format_errors_by_column"] or {},
            issues=issues,
            score=row["quality_score"],
        )
    return RunResult(
        run_id=row["run_id"],
        dataset=row["dataset"],
        source_file=row["source_file"],
        triggered_by=row["triggered_by"],
        started_at=row["started_at"],
        status=RunStatus(row["status"]),
        finished_at=row["finished_at"],
        rows_read=row["rows_read"],
        rows_valid=row["rows_valid"],
        rows_rejected=row["rows_rejected"],
        quality=quality,
        error=row["error"],
        is_demo=row["is_demo"],
    )
