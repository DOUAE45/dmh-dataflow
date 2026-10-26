# Raccourcis pour le terminal (macOS / VS Code).  `make help` pour la liste.
PY := .venv/bin/python

.PHONY: help venv env up down reset-db ps logs db-check test test-int lint check

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

venv: ## Crée .venv (Python 3.12) et installe toutes les dépendances
	python3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[app,metrics,dev]"

env: ## Crée .env depuis .env.example avec des mots de passe aléatoires (si absent)
	@test -f .env && echo ".env existe déjà : rien à faire." || ( \
	  cp .env.example .env && \
	  for v in POSTGRES_SUPERUSER_PASSWORD DMH_DB_PASSWORD AIRFLOW_DB_PASSWORD; do \
	    p=$$(python3 -c "import secrets; print(secrets.token_hex(16))"); \
	    sed -i '' "s/^$$v=.*/$$v=$$p/" .env; \
	  done && echo ".env créé avec des mots de passe aléatoires." )

up: ## Démarre les services Docker et attend qu'ils soient prêts
	docker compose up -d --wait

down: ## Arrête les services (les données sont conservées)
	docker compose down

reset-db: ## ⚠ Supprime le volume PostgreSQL (toutes les données) puis redémarre
	docker compose down -v
	docker compose up -d --wait

ps: ## État des conteneurs
	docker compose ps

logs: ## Logs des services
	docker compose logs -f --tail=100

db-check: ## Vérifie la connexion Python → PostgreSQL
	$(PY) -m dmh.db.healthcheck

test: ## Tests unitaires
	$(PY) -m pytest -v

test-int: ## Tests d'intégration (nécessite `make up`)
	$(PY) -m pytest -v -m integration

lint: ## Analyse statique du code
	$(PY) -m ruff check .

check: up lint test test-int ## Tout vérifier avant une PR (comme la CI)
