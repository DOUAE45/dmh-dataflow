#!/bin/sh
# Crée deux bases séparées, chacune avec son propre utilisateur :
#   - base applicative DMH (données, exécutions, rapports qualité)
#   - base de métadonnées Airflow
# Exécuté automatiquement par l'image postgres au PREMIER démarrage du volume.
# Les valeurs sont passées via `psql -v` et citées par psql (:"ident" / :'littéral'),
# ce qui évite toute injection SQL depuis les variables d'environnement.
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname postgres \
  -v dmh_db="$DMH_DB_NAME" -v dmh_user="$DMH_DB_USER" -v dmh_pwd="$DMH_DB_PASSWORD" \
  -v af_db="$AIRFLOW_DB_NAME" -v af_user="$AIRFLOW_DB_USER" -v af_pwd="$AIRFLOW_DB_PASSWORD" <<'EOSQL'
CREATE ROLE :"dmh_user" LOGIN PASSWORD :'dmh_pwd';
CREATE DATABASE :"dmh_db" OWNER :"dmh_user";
REVOKE ALL ON DATABASE :"dmh_db" FROM PUBLIC;

CREATE ROLE :"af_user" LOGIN PASSWORD :'af_pwd';
CREATE DATABASE :"af_db" OWNER :"af_user";
REVOKE ALL ON DATABASE :"af_db" FROM PUBLIC;
EOSQL

echo "Bases '$DMH_DB_NAME' et '$AIRFLOW_DB_NAME' créées."
