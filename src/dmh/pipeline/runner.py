"""Orchestration d'une exécution complète du pipeline.

    archivage (data/raw) -> lecture -> normalisation -> contrôle qualité -> nettoyage
    -> quarantaine (data/quarantine) -> stockage PostgreSQL -> métriques

Usage : python -m dmh.pipeline.runner data/sample/demo_sales.csv demo_sales
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from dmh.config import get_settings
from dmh.contracts import RunResult, RunStatus
from dmh.db import repository
from dmh.db.connection import get_engine
from dmh.ingestion.datasets import load_dataset_config
from dmh.ingestion.reader import read_csv
from dmh.pipeline.cleaning import clean, normalize

logger = logging.getLogger(__name__)


class SchemaMismatchError(ValueError):
    """Le fichier ne contient pas les colonnes obligatoires du jeu de données."""


def run_pipeline(
    source_path: str | Path,
    dataset: str,
    triggered_by: str,
    *,
    engine: Engine | None = None,
) -> RunResult:
    """Traite un fichier et enregistre l'exécution, qu'elle réussisse ou non.

    Ne lève pas d'exception pour un fichier invalide : le statut FAILED et le message sont
    dans le résultat (et en base). Lève seulement si la base elle-même est inaccessible.
    """
    engine = engine or get_engine()
    settings = get_settings()
    source = Path(source_path)
    result = RunResult(
        run_id=str(uuid.uuid4()),
        dataset=dataset,
        source_file=source.name,
        triggered_by=triggered_by,
        started_at=datetime.now(UTC),
        is_demo=source.name.startswith("demo_"),
    )

    repository.create_tables(engine)
    with engine.begin() as conn:
        repository.save_run(conn, result)  # visible tout de suite comme "running"

    try:
        config = load_dataset_config(dataset)
        archived = _archive(source, settings.raw_dir, result.run_id)
        df = normalize(read_csv(archived), config)
        result.rows_read = len(df)

        cleaned = clean(df, config)
        result.quality = cleaned.report
        missing = [i.column for i in cleaned.report.issues if i.check == "missing_column"]
        if missing:
            raise SchemaMismatchError(f"Colonnes obligatoires absentes : {', '.join(missing)}")

        result.rows_valid = len(cleaned.valid)
        result.rows_rejected = len(cleaned.rejected)
        if result.rows_rejected:
            _write_quarantine(cleaned.rejected, settings.quarantine_dir, result.run_id, source)

        result.status = RunStatus.SUCCESS
        result.finished_at = datetime.now(UTC)
        # Données et statut final dans la même transaction : SUCCESS => données présentes.
        with engine.begin() as conn:
            repository.store_valid_rows(conn, config.schema, cleaned.valid, result.run_id)
            repository.save_run(conn, result)
    except Exception as exc:  # toute erreur de traitement est enregistrée, pas propagée
        logger.exception("Échec de l'exécution %s", result.run_id)
        result.status = RunStatus.FAILED
        result.error = f"{type(exc).__name__}: {exc}"
        result.rows_valid = 0
        result.finished_at = datetime.now(UTC)
        with engine.begin() as conn:
            repository.save_run(conn, result)

    _publish_metrics(result)
    return result


def _archive(source: Path, raw_dir: Path, run_id: str) -> Path:
    """Copie le fichier reçu dans data/raw ; l'original n'est jamais modifié."""
    if not source.is_file():
        raise FileNotFoundError(f"Fichier introuvable : {source}")
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{run_id}_{source.name}"
    shutil.copy2(source, target)
    return target


def _write_quarantine(rejected, quarantine_dir: Path, run_id: str, source: Path) -> Path:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / f"{run_id}_{source.stem}_rejected.csv"
    rejected.to_csv(target, index=False)
    return target


def _publish_metrics(result: RunResult) -> None:
    """L'envoi des métriques ne doit jamais faire échouer le pipeline."""
    try:
        from dmh.metrics.publisher import publish_run_metrics
    except ImportError:
        return  # module de Hala pas encore livré (étape 4)
    try:
        publish_run_metrics(result)
    except Exception:
        logger.warning("Envoi des métriques impossible pour %s", result.run_id, exc_info=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lance le pipeline DMH sur un fichier CSV.")
    parser.add_argument("source", type=Path, help="chemin du fichier CSV")
    parser.add_argument("dataset", help="nom du jeu de données (config/datasets/<nom>.yaml)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = run_pipeline(args.source, args.dataset, triggered_by="cli")
    print(f"{result.status.upper()}  run_id={result.run_id}")
    print(f"  lignes lues={result.rows_read}  valides={result.rows_valid}", end="")
    print(f"  rejetées={result.rows_rejected}")
    if result.quality:
        print(f"  score qualité={result.quality.score}")
        for issue in result.quality.issues:
            print(f"  - {issue.message}")
    if result.error:
        print(f"  erreur : {result.error}")
    return 0 if result.status is RunStatus.SUCCESS else 1


if __name__ == "__main__":
    sys.exit(main())
