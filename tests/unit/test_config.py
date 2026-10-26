from pathlib import Path

import pytest
from pydantic import ValidationError

from dmh.config import Settings


def _settings(monkeypatch, **env) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # isole le test du .env local


def test_password_is_required(monkeypatch):
    monkeypatch.delenv("DMH_DB_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_uses_psycopg_and_hides_password(monkeypatch):
    s = _settings(monkeypatch, DMH_DB_PASSWORD="s3cr3t!@#", DMH_DB_PORT="6000")

    url = s.database_url
    assert url.drivername == "postgresql+psycopg"
    assert url.port == 6000
    assert url.password == "s3cr3t!@#"  # caractères spéciaux conservés sans échappement manuel
    assert "s3cr3t" not in str(url)
    assert "s3cr3t" not in repr(s)


def test_data_directories_derive_from_data_dir(monkeypatch):
    s = _settings(monkeypatch, DMH_DB_PASSWORD="x", DMH_DATA_DIR="/tmp/dmh-data")

    assert s.raw_dir == Path("/tmp/dmh-data/raw")
    assert s.incoming_dir == Path("/tmp/dmh-data/incoming")
    assert s.quarantine_dir == Path("/tmp/dmh-data/quarantine")
