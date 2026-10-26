from functools import lru_cache

from sqlalchemy import Engine, create_engine

from dmh.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping : reconnexion propre si le conteneur PostgreSQL a redémarré
    return create_engine(get_settings().database_url, pool_pre_ping=True)
