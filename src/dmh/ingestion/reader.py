"""Lecture des fichiers CSV.

Toutes les colonnes sont lues comme du texte : la conversion de types est faite plus tard,
colonne par colonne, pour pouvoir compter les erreurs de format au lieu d'échouer.
Les espaces en début et fin de valeur sont retirés et les cellules vides deviennent NA.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

ENCODINGS = ("utf-8-sig", "latin-1")  # utf-8-sig retire aussi le BOM ajouté par Excel
DELIMITERS = ",;\t|"


class IngestionError(ValueError):
    """Fichier illisible ou qui n'est pas un CSV exploitable."""


def detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:65536]
    for encoding in ENCODINGS:
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return ENCODINGS[-1]  # latin-1 décode n'importe quel octet


def detect_delimiter(path: Path, encoding: str) -> str:
    with path.open(encoding=encoding, newline="") as f:
        sample = f.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        return ","  # une seule colonne, ou fichier trop court pour deviner


def read_csv(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise IngestionError(f"Fichier introuvable : {path}")
    if path.stat().st_size == 0:
        raise IngestionError(f"Fichier vide : {path.name}")

    encoding = detect_encoding(path)
    sep = detect_delimiter(path, encoding)
    try:
        # En-tête lu à part : pandas renommerait silencieusement "a,a" en "a, a.1".
        header = pd.read_csv(path, sep=sep, encoding=encoding, header=None, nrows=1, dtype=str)
        df = pd.read_csv(
            path,
            sep=sep,
            encoding=encoding,
            dtype=str,
            nrows=nrows,
            skip_blank_lines=True,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise IngestionError(f"CSV illisible ({path.name}) : {exc}") from exc

    names = ["" if pd.isna(c) else str(c).strip() for c in header.iloc[0]]
    if "" in names:
        raise IngestionError(f"En-tête incomplet dans {path.name} : {names}")
    if len(set(names)) != len(names):
        raise IngestionError(f"Colonnes en double dans l'en-tête de {path.name} : {names}")
    df.columns = names

    for col in df.columns:
        df[col] = df[col].str.strip()
    return df.mask(df == "")


def preview(path: str | Path, rows: int = 20) -> pd.DataFrame:
    """Premières lignes, pour l'aperçu dans Streamlit avant de lancer le pipeline."""
    return read_csv(path, nrows=rows)
