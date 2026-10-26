"""Contrats partagés entre les modules : la « langue commune » de l'équipe.

Toute modification de ce fichier passe par une Pull Request relue par les trois membres,
car Streamlit (Hala), Airflow (Meryem) et le pipeline (Douae) en dépendent.

Fonctions publiques attendues (implémentées aux étapes 3 et 4) :
    dmh.pipeline.runner.run_pipeline(source_path, dataset, triggered_by) -> RunResult   [Douae]
    dmh.quality.checks.assess_quality(df, schema) -> QualityReport                      [Douae]
    dmh.metrics.publisher.publish_run_metrics(result) -> None                           [Hala]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

ColumnType = Literal["int", "float", "str", "date", "bool"]
IssueType = Literal[
    "missing_column", "missing_value", "duplicate", "format_error", "unexpected_column"
]


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class ColumnSpec:
    """Une colonne attendue dans un jeu de données (définie dans config/datasets/*.yaml)."""

    name: str
    dtype: ColumnType
    required: bool = True
    unique: bool = False


@dataclass(frozen=True)
class DatasetSchema:
    name: str
    columns: tuple[ColumnSpec, ...]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass(frozen=True)
class QualityIssue:
    """Un problème détecté. `column` vaut None pour un problème portant sur la ligne entière."""

    check: IssueType
    column: str | None
    row_count: int
    message: str


@dataclass
class QualityReport:
    rows_total: int
    missing_by_column: dict[str, int] = field(default_factory=dict)
    duplicate_rows: int = 0
    format_errors_by_column: dict[str, int] = field(default_factory=dict)
    issues: list[QualityIssue] = field(default_factory=list)
    score: float = 100.0  # 0 à 100, formule documentée dans dmh.quality


@dataclass
class RunResult:
    """Résultat d'une exécution, enregistré dans PostgreSQL et affiché partout."""

    run_id: str
    dataset: str
    source_file: str
    triggered_by: str  # "streamlit", "airflow", "cli", "test"
    started_at: datetime
    status: RunStatus = RunStatus.RUNNING
    finished_at: datetime | None = None
    rows_read: int = 0
    rows_valid: int = 0
    rows_rejected: int = 0
    quality: QualityReport | None = None
    error: str | None = None
    is_demo: bool = False  # True pour les jeux de données fictifs (data/sample/demo_*.csv)

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
