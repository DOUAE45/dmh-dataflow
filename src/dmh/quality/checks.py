"""Contrôles qualité d'un jeu de données.

Une ligne est **rejetée** si au moins une de ces règles est violée :
  - une colonne obligatoire est absente du fichier (toutes les lignes sont alors rejetées) ;
  - une valeur obligatoire est manquante ;
  - une valeur n'a pas le format attendu (nombre, date, booléen) ;
  - la ligne est le doublon exact d'une ligne précédente ;
  - une colonne `unique` reprend une valeur déjà vue sur une ligne précédente ;
  - une colonne `unique` reprend une valeur déjà chargée par une exécution précédente
    (seulement si `existing_keys` est fourni, ce que fait le pipeline).

Score qualité = 100 × lignes valides / lignes totales, arrondi à 0,1 (100 pour un fichier
sans ligne). Le même calcul sert au rapport et au nettoyage : le score affiché correspond
toujours exactement à la part des lignes chargées dans PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from dmh.contracts import DatasetSchema, QualityIssue, QualityReport
from dmh.quality.parsing import parse_column


@dataclass
class RowCheck:
    """Résultat détaillé, ligne par ligne, utilisé par le nettoyage."""

    parsed: pd.DataFrame  # colonnes du schéma, converties dans leur type
    reasons: pd.Series  # motifs de rejet séparés par "; ", chaîne vide si la ligne est valide
    report: QualityReport

    @property
    def valid_mask(self) -> pd.Series:
        return self.reasons == ""


def assess_quality(
    df: pd.DataFrame, schema: DatasetSchema, date_format: str = "%Y-%m-%d"
) -> QualityReport:
    return check_rows(df, schema, date_format).report


def check_rows(
    df: pd.DataFrame,
    schema: DatasetSchema,
    date_format: str = "%Y-%m-%d",
    existing_keys: Mapping[str, set] | None = None,
) -> RowCheck:
    """`existing_keys` : valeurs déjà en base par colonne `unique` (repository.existing_keys)."""
    report = QualityReport(rows_total=len(df))
    reasons: list[pd.Series] = []

    def flag(mask: pd.Series, reason: str) -> None:
        reasons.append(pd.Series(reason, index=df.index).where(mask, ""))

    expected = set(schema.column_names)
    for col in df.columns:
        if col not in expected:
            report.issues.append(
                QualityIssue("unexpected_column", col, 0, f"Colonne non déclarée ignorée : {col}")
            )

    parsed = pd.DataFrame(index=df.index)
    for spec in schema.columns:
        if spec.name not in df.columns:
            parsed[spec.name] = pd.Series(pd.NA, index=df.index, dtype="object")
            if spec.required:
                report.issues.append(
                    QualityIssue(
                        "missing_column",
                        spec.name,
                        len(df),
                        f"Colonne obligatoire absente : {spec.name}",
                    )
                )
                flag(pd.Series(True, index=df.index), f"colonne absente : {spec.name}")
            continue

        values = df[spec.name]
        missing = values.isna()
        report.missing_by_column[spec.name] = int(missing.sum())
        if spec.required and missing.any():
            report.issues.append(
                QualityIssue(
                    "missing_value",
                    spec.name,
                    int(missing.sum()),
                    f"{int(missing.sum())} valeur(s) manquante(s) dans {spec.name}",
                )
            )
            flag(missing, f"{spec.name} manquant")

        converted, ok = parse_column(values, spec.dtype, date_format)
        parsed[spec.name] = converted
        bad = ~ok
        report.format_errors_by_column[spec.name] = int(bad.sum())
        if bad.any():
            report.issues.append(
                QualityIssue(
                    "format_error",
                    spec.name,
                    int(bad.sum()),
                    f"{int(bad.sum())} valeur(s) au mauvais format ({spec.dtype}) dans {spec.name}",
                )
            )
            flag(bad, f"{spec.name} : format {spec.dtype} invalide")

    # Doublons exacts, comparés sur les colonnes du fichier après normalisation.
    exact_dup = df.duplicated(keep="first")
    report.duplicate_rows = int(exact_dup.sum())
    if exact_dup.any():
        report.issues.append(
            QualityIssue(
                "duplicate",
                None,
                report.duplicate_rows,
                f"{report.duplicate_rows} ligne(s) en double",
            )
        )
        flag(exact_dup, "ligne en double")

    # Clé unique répétée sur une ligne qui n'est pas un doublon exact (contenu différent).
    for spec in schema.columns:
        if not spec.unique or spec.name not in df.columns:
            continue
        key = parsed[spec.name]
        repeated = key.notna() & key.duplicated(keep="first") & ~exact_dup
        if repeated.any():
            report.issues.append(
                QualityIssue(
                    "duplicate",
                    spec.name,
                    int(repeated.sum()),
                    f"{int(repeated.sum())} valeur(s) répétée(s) dans {spec.name} (unique)",
                )
            )
            flag(repeated, f"{spec.name} déjà utilisé")

        # Clé déjà chargée en base par une exécution précédente (relance du même fichier).
        known = (existing_keys or {}).get(spec.name)
        if known:
            comparable = key.dt.date if spec.dtype == "date" else key  # la base renvoie des dates
            in_db = key.notna() & comparable.isin(known)
            if in_db.any():
                report.issues.append(
                    QualityIssue(
                        "duplicate",
                        spec.name,
                        int(in_db.sum()),
                        f"{int(in_db.sum())} valeur(s) de {spec.name} déjà chargée(s) en base",
                    )
                )
                flag(in_db, f"{spec.name} déjà chargé en base")

    if reasons:
        combined = pd.concat(reasons, axis=1).apply(
            lambda row: "; ".join(r for r in row if r), axis=1
        )
    else:
        combined = pd.Series("", index=df.index, dtype="object")
    if df.empty:
        combined = pd.Series("", index=df.index, dtype="object")

    valid = int((combined == "").sum())
    report.score = round(100 * valid / len(df), 1) if len(df) else 100.0
    return RowCheck(parsed=parsed, reasons=combined, report=report)
