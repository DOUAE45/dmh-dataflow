# DMH DataFlow — Intelligent DataOps Platform

Projet de fin d'année (PFA) — **Douae, Meryem, Hala**.

Plateforme DataOps qui automatise le cycle de traitement de fichiers CSV :
import → contrôle qualité → nettoyage → stockage PostgreSQL → orchestration Airflow → supervision.

> **État actuel : étape 3 / 6 terminée.** PostgreSQL, la configuration, les contrats et le
> pipeline (ingestion, contrôle qualité, nettoyage, stockage) sont en place et testés.
> Airflow, Streamlit et le monitoring arrivent aux étapes 4 et 5
> (voir [Feuille de route](#feuille-de-route)).

## Architecture

```
Streamlit (UI) ──┐                         ┌── Airflow (DAG, retries)
                 ▼                         ▼
          package Python `dmh` (ingestion → qualité → nettoyage → stockage → métriques)
                 │                                   │
                 ▼                                   ▼
   PostgreSQL 16 : base `dmh` + base `airflow`   Pushgateway → Prometheus → Grafana
```

Toute la logique métier est dans `src/dmh/` : Streamlit, Airflow et les tests appellent les mêmes
fonctions. Les fichiers CSV originaux (`data/raw/`) ne sont jamais modifiés ni supprimés.

## Versions retenues

| Composant | Version | Justification |
|---|---|---|
| Python | 3.12 | Supporté par toutes les briques ci-dessous |
| Apache Airflow | 3.3.2 (étape 4) | Version stable ; Airflow 2 est en fin de vie |
| pandas | 3.0.5 | Aligné sur les contraintes Airflow 3.3.2 |
| SQLAlchemy / psycopg | 2.0.52 / 3.3.5 | Idem |
| pydantic / pydantic-settings | 2.13.5 / 2.15.0 | Idem |
| Streamlit / Plotly | 1.66.1 / 7.1.0 | Interface (étape 5) |
| prometheus-client | 0.26.0 | Métriques (étape 4) |
| pytest / ruff | 9.1.1 / 0.17.2 | Tests et lint |
| PostgreSQL (Docker) | `postgres:16.15-alpine` | |
| Prometheus / Pushgateway / Grafana | v3.15.1 / v1.11.5 / 13.0.11 | Prévu à l'étape 4 |

Les versions Python sont figées dans [pyproject.toml](pyproject.toml) et correspondent au fichier
de contraintes officiel d'Airflow 3.3.2 pour Python 3.12, afin que `dmh` s'installe sans conflit
dans l'image Airflow.

## Prérequis (macOS)

- Docker Desktop démarré, avec au moins 6 Go de RAM (Settings → Resources)
- Python 3.12 : `brew install python@3.12`
- `make` (fourni avec les Command Line Tools : `xcode-select --install`)

## Démarrage rapide

Dans le terminal VS Code, à la racine du projet :

```bash
make venv        # crée .venv et installe les dépendances
make env         # crée .env avec des mots de passe aléatoires (une seule fois)
make up          # démarre PostgreSQL et attend qu'il soit prêt
make db-check    # doit afficher : OK  utilisateur=dmh_app  base=dmh
make test        # tests unitaires
make test-int    # tests d'intégration (PostgreSQL requis)
make check       # tout d'un coup : up + lint + test + test-int
```

Activer l'environnement Python dans le terminal : `source .venv/bin/activate`.
Dans VS Code : `Cmd+Shift+P` → *Python: Select Interpreter* → `.venv`.

`make help` liste toutes les commandes.

### Lancer le pipeline

```bash
.venv/bin/python -m dmh.pipeline.runner data/sample/demo_sales.csv demo_sales
# SUCCESS  lignes lues=20  valides=12  rejetées=8  score qualité=60.0
```

Les lignes valides vont dans la table `data_demo_sales`, les lignes rejetées dans
`data/quarantine/` avec leur motif, et chaque exécution dans l'historique (`pipeline_runs`).

### Ports

| Service | Adresse | Remarque |
|---|---|---|
| PostgreSQL | `127.0.0.1:5433` | 5433 car un PostgreSQL local occupe souvent 5432 |
| Streamlit | `127.0.0.1:8501` | étape 5 |
| Airflow | `127.0.0.1:8081` | étape 4 (8080 est souvent occupé) |
| Grafana | `127.0.0.1:3000` | étape 4 |

Tous les ports sont liés à `127.0.0.1` : rien n'est exposé sur le réseau local.

### Problèmes fréquents

| Message | Cause / solution |
|---|---|
| `Cannot connect to the Docker daemon` | Ouvrir Docker Desktop et attendre qu'il soit prêt |
| `DMH_DB_PASSWORD manquant dans .env` | Lancer `make env` |
| `port is already allocated` sur 5433 | Changer `POSTGRES_HOST_PORT` **et** `DMH_DB_PORT` dans `.env` |
| `password authentication failed` après modification du `.env` | Les mots de passe sont fixés à la **première** création du volume : `make reset-db` (⚠ efface les données) |
| `No module named 'dmh'` alors que `make test` passe | Projet dans un dossier synchronisé par iCloud (Bureau, Documents) : iCloud cache un fichier de `.venv`. Placer le projet hors de ces dossiers, ou `.venv` dans `~/.venvs/dmh` avec un lien symbolique |

## Sécurité

- Aucun secret dans le code : tout passe par `.env` (ignoré par Git) ; modèle dans [.env.example](.env.example).
- Deux bases séparées avec deux utilisateurs distincts ; l'utilisateur applicatif n'est pas
  super-utilisateur et ne peut pas se connecter à la base Airflow.
- La CI (désactivée pour l'instant) génère des mots de passe éphémères et ne déploie rien.

## Organisation de l'équipe

| Membre | Rôle | Fichiers dont elle est responsable |
|---|---|---|
| **Douae** | Data Engineer | `src/dmh/ingestion/`, `quality/`, `pipeline/`, `db/`, `config/datasets/`, `data/sample/`, tests associés |
| **Meryem** | DevOps Engineer | `docker-compose.yml`, `docker/`, `airflow/`, `.github/`, `Makefile`, `src/dmh/config.py`, `pyproject.toml` |
| **Hala** | Dashboard & Monitoring | `app/`, `src/dmh/metrics/`, `monitoring/`, tests associés |
| Toutes | — | `src/dmh/contracts.py`, `README.md`, `docs/` : modification par PR relue par les trois |

### Contrats entre modules

Définis dans [src/dmh/contracts.py](src/dmh/contracts.py) : `RunResult`, `QualityReport`,
`DatasetSchema`, `RunStatus`. Fonctions publiques prévues :

```python
dmh.pipeline.runner.run_pipeline(source_path, dataset, triggered_by) -> RunResult  # Douae
dmh.quality.checks.assess_quality(df, schema) -> QualityReport                     # Douae
dmh.metrics.publisher.publish_run_metrics(result) -> None                          # Hala
```

En attendant une implémentation, chacune peut construire un `RunResult` factice pour avancer.

### Workflow Git

1. `main` ne reçoit que des Pull Requests.
2. Une branche par fonctionnalité : `feat/douae-quality-checks`, `feat/hala-dashboard`…
3. Avant de pousser : `make check`.
4. Chaque PR est relue par une autre membre ; `make check` doit passer (la CI GitHub est
   désactivée, la vérification se fait en local).

## Feuille de route

| Étape | Contenu | État |
|---|---|---|
| 1 | Analyse, architecture, plan | ✅ |
| 2 | Arborescence, dépendances, PostgreSQL, contrats, CI | ✅ testé localement |
| 3 | Pipeline : ingestion, qualité, nettoyage, stockage, tests, jeu de démo | ✅ (PR #1) |
| 4 | Airflow, métriques, Prometheus/Grafana | ⏳ |
| 5 | Dashboard Streamlit (6 pages), tests d'intégration | ⏳ |
| 6 | Finalisation, schémas, scénarios de démonstration, limites | ⏳ |

## Données de démonstration

Les jeux de données fournis dans `data/sample/` sont **fictifs** et nommés `demo_*.csv`.
Les exécutions qui les utilisent sont marquées `is_demo = true` et affichées avec un badge « DÉMO ».
