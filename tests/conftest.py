import pytest

from dmh.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Chaque test relit la configuration (utile avec monkeypatch.setenv)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
