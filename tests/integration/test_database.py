"""Nécessite PostgreSQL démarré (docker compose up -d) et un .env rempli.
Lancement : pytest -m integration
"""

import os

import pytest
from dotenv import dotenv_values
from sqlalchemy import text

from dmh.config import get_settings
from dmh.db.connection import get_engine

pytestmark = pytest.mark.integration


def test_app_user_connects_to_app_database():
    settings = get_settings()
    with get_engine().connect() as conn:
        user, db = conn.execute(text("SELECT current_user, current_database()")).one()
    assert (user, db) == (settings.db_user, settings.db_name)


def test_app_user_is_not_superuser():
    with get_engine().connect() as conn:
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    assert is_super is False


def test_airflow_database_exists_separately():
    airflow_db = (
        dotenv_values(".env").get("AIRFLOW_DB_NAME") or os.getenv("AIRFLOW_DB_NAME", "airflow")
    )
    with get_engine().connect() as conn:
        names = set(conn.execute(text("SELECT datname FROM pg_database")).scalars())
    assert airflow_db in names
    assert airflow_db != get_settings().db_name


def test_app_user_can_create_tables():
    with get_engine().begin() as conn:
        conn.execute(text("CREATE TEMP TABLE _smoke (id int)"))
        conn.execute(text("INSERT INTO _smoke VALUES (1)"))
        assert conn.execute(text("SELECT count(*) FROM _smoke")).scalar() == 1
