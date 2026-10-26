"""Configuration centralisée, lue depuis les variables d'environnement ou le fichier .env.

Responsable : Meryem (DevOps). Aucun secret n'a de valeur par défaut dans le code.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # le .env contient aussi des variables destinées à Docker
    )

    env: str = Field(default="dev", alias="DMH_ENV")

    db_host: str = Field(default="localhost", alias="DMH_DB_HOST")
    db_port: int = Field(default=5433, alias="DMH_DB_PORT")
    db_name: str = Field(default="dmh", alias="DMH_DB_NAME")
    db_user: str = Field(default="dmh_app", alias="DMH_DB_USER")
    db_password: SecretStr = Field(alias="DMH_DB_PASSWORD")

    data_dir: Path = Field(default=Path("./data"), alias="DMH_DATA_DIR")
    pushgateway_url: str = Field(default="", alias="DMH_PUSHGATEWAY_URL")

    @property
    def database_url(self) -> URL:
        """URL SQLAlchemy ; l'objet URL masque le mot de passe quand il est affiché."""
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def raw_dir(self) -> Path:
        """Fichiers originaux importés : jamais modifiés ni supprimés par le pipeline."""
        return self.data_dir / "raw"

    @property
    def incoming_dir(self) -> Path:
        """Dossier surveillé par le DAG Airflow."""
        return self.data_dir / "incoming"

    @property
    def quarantine_dir(self) -> Path:
        """Copies des lignes rejetées, pour consultation."""
        return self.data_dir / "quarantine"


@lru_cache
def get_settings() -> Settings:
    return Settings()
