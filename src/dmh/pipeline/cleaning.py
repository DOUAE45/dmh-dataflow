"""Nettoyage configurable : normalisation puis séparation lignes valides / rejetées."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from dmh.contracts import QualityReport
from dmh.ingestion.datasets import DatasetConfig
from dmh.quality.checks import check_rows

REJECT_REASON_COLUMN = "_reject_reason"


@dataclass
class CleaningResult:
    valid: pd.DataFrame  # colonnes du schéma, typées, prêtes pour PostgreSQL
    rejected: pd.DataFrame  # lignes d'origine + colonne _reject_reason (quarantaine)
    report: QualityReport


def normalize(df: pd.DataFrame, config: DatasetConfig) -> pd.DataFrame:
    """Applique les options `cleaning` du YAML. Ne modifie pas le DataFrame reçu."""
    out = df.rename(columns=config.cleaning.rename)
    for col in config.cleaning.lowercase:
        if col in out.columns:
            out[col] = out[col].str.lower()
    return out


def clean(
    df: pd.DataFrame, config: DatasetConfig, existing_keys: Mapping[str, set] | None = None
) -> CleaningResult:
    """`df` doit déjà être normalisé (voir `normalize`)."""
    checked = check_rows(df, config.schema, config.cleaning.date_format, existing_keys)
    valid_mask = checked.valid_mask

    valid = checked.parsed.loc[valid_mask].reset_index(drop=True)
    rejected = df.loc[~valid_mask].copy()
    rejected[REJECT_REASON_COLUMN] = checked.reasons.loc[~valid_mask]
    # Numéro de ligne dans le fichier d'origine (ligne 1 = en-tête), pour retrouver l'erreur.
    rejected.insert(0, "_source_line", rejected.index + 2)

    return CleaningResult(
        valid=valid, rejected=rejected.reset_index(drop=True), report=checked.report
    )
