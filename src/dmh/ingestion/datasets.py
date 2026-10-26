"""Chargement des définitions de jeux de données (config/datasets/<nom>.yaml)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

import yaml

from dmh.contracts import ColumnSpec, ColumnType, DatasetSchema

# Le nom sert aussi de nom de table (data_<nom>) : on le restreint volontairement.
DATASET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,50}$")


class DatasetConfigError(ValueError):
    """Fichier de configuration absent ou invalide."""


@dataclass(frozen=True)
class CleaningOptions:
    date_format: str = "%Y-%m-%d"
    lowercase: tuple[str, ...] = ()
    rename: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetConfig:
    schema: DatasetSchema
    cleaning: CleaningOptions = field(default_factory=CleaningOptions)
    description: str = ""

    @property
    def name(self) -> str:
        return self.schema.name


def datasets_dir() -> Path:
    """Dossier des fichiers YAML ; modifiable avec DMH_DATASETS_DIR (ex. dans Airflow)."""
    return Path(os.getenv("DMH_DATASETS_DIR", "config/datasets"))


def list_datasets(directory: Path | None = None) -> list[str]:
    directory = directory or datasets_dir()
    return sorted(p.stem for p in directory.glob("*.yaml"))


def load_dataset_config(name: str, directory: Path | None = None) -> DatasetConfig:
    if not DATASET_NAME_RE.fullmatch(name):
        raise DatasetConfigError(
            f"Nom de jeu de données invalide : {name!r} (minuscules, chiffres et _ uniquement)"
        )
    path = (directory or datasets_dir()) / f"{name}.yaml"
    if not path.is_file():
        raise DatasetConfigError(f"Configuration introuvable : {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("name", name) != name:
        raise DatasetConfigError(f"{path.name} : 'name' doit valoir {name!r}")

    columns = tuple(_parse_column(c, path) for c in raw.get("columns") or [])
    if not columns:
        raise DatasetConfigError(f"{path.name} : aucune colonne déclarée")
    names = [c.name for c in columns]
    if len(set(names)) != len(names):
        raise DatasetConfigError(f"{path.name} : colonne déclarée deux fois")

    cleaning = raw.get("cleaning") or {}
    options = CleaningOptions(
        date_format=cleaning.get("date_format", CleaningOptions.date_format),
        lowercase=tuple(cleaning.get("lowercase") or ()),
        rename=dict(cleaning.get("rename") or {}),
    )
    unknown = set(options.lowercase) - set(names)
    if unknown:
        raise DatasetConfigError(f"{path.name} : 'lowercase' cite des colonnes inconnues {unknown}")

    return DatasetConfig(
        schema=DatasetSchema(name=name, columns=columns),
        cleaning=options,
        description=raw.get("description", ""),
    )


def _parse_column(entry: dict, path: Path) -> ColumnSpec:
    try:
        spec = ColumnSpec(
            name=str(entry["name"]),
            dtype=entry["dtype"],
            required=bool(entry.get("required", True)),
            unique=bool(entry.get("unique", False)),
        )
    except (KeyError, TypeError) as exc:
        raise DatasetConfigError(f"{path.name} : colonne mal définie {entry!r}") from exc
    if spec.dtype not in get_args(ColumnType):
        raise DatasetConfigError(f"{path.name} : type inconnu {spec.dtype!r} pour {spec.name}")
    return spec
