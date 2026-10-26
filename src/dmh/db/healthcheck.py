"""Vérifie la connexion à la base DMH.  Usage : python -m dmh.db.healthcheck"""

import sys

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from dmh.config import get_settings
from dmh.db.connection import get_engine


def main() -> int:
    settings = get_settings()
    target = f"{settings.db_user}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT current_user, current_database(), version()")
            ).one()
    except OperationalError as exc:
        print(f"ÉCHEC connexion à {target}\n{exc.orig}", file=sys.stderr)
        print("Le conteneur tourne-t-il ?  docker compose ps", file=sys.stderr)
        return 1
    print(f"OK  utilisateur={row[0]}  base={row[1]}")
    print(f"    {row[2].split(',')[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
