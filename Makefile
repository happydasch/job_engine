.PHONY: install create-scraper scaffold-scraper score seed fetch-content dashboard dashboard-debug dev build clean test test-scrapers test-all docker-build docker-up docker-down docker-logs docker-dev lint format typecheck doctor pipeline-check scraper-install scraper-uninstall scraper-catalog scraper-metadata migrate bootstrap-taxonomy llm-test refresh-rates rates-status liveness-check repost-check db-check check-update

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYRIGHT_VERSION := 1.1.411
PYRIGHT := PYRIGHT_PYTHON_FORCE_VERSION=$(PYRIGHT_VERSION) PYRIGHT_PYTHON_IGNORE_WARNINGS=1 $(PY) -m pyright
JOB_ENGINE_ROOT := $(shell pwd)
export JOB_ENGINE_ROOT

# --- Python ------------------------------------------------------------------

install: $(VENV)/bin/activate
	$(PIP) install -e packages/job-engine-core
	$(PIP) install -e packages/job-engine-dashboard
	$(PIP) install pyright==$(PYRIGHT_VERSION)
	cd packages/job-engine-scrapers && npm install
	cd packages/job-engine-dashboard && npm install
	$(MAKE) build

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

create-scraper: ## Create a new scraper scaffold: make create-scraper ID=my_board TYPE=api NAME="My Board"
	cd packages/job-engine-scrapers && node create-scraper.mjs $(ID) --type $(TYPE) --name "$(NAME)"

scaffold-scraper: ## Scaffold a new scraper: make scaffold-scraper ARGS="my_board https://example.com/jobs"
	$(PY) scripts/scaffold_scraper.py $(ARGS)

score:
	$(PY) -m job_engine.skill_scorer data/scraper-output/_all.json --top 10

seed:
	$(PY) scripts/seed.py

fetch-content:
	$(PY) scripts/fetch_content.py $(ARGS)

dashboard: build
	$(VENV)/bin/uvicorn dashboard.main:app --reload --port $(or $(PORT),8000)
dashboard-debug: build
	$(VENV)/bin/uvicorn dashboard.main:app --port $(or $(PORT),8000)

# --- Testing -----------------------------------------------------------------

test:
	$(PY) -m pytest packages/job-engine-core/tests/ -v --tb=short

test-scrapers:
	cd packages/job-engine-scrapers && npm test

test-all: test test-scrapers

llm-test:
	$(PY) -c "from job_engine.llm import get_llm; llm = get_llm(); print('LLM configured:', 'yes' if llm else 'no (set an LLM API key in Settings)')"

bootstrap-taxonomy:
	@echo "Bootstrapping taxonomy registry from built-in aliases and existing data..."
	$(PY) scripts/bootstrap_taxonomy.py

migrate:
	@echo "Running schema migration (companies table, company_id FK, tech_stack -> skills)..."
	$(PY) -c "from job_engine.database import migrate_existing_db; migrate_existing_db(); print('Migration complete')"

# --- Scraper Catalog ---------------------------------------------------------

scraper-catalog:
	@echo "Open http://localhost:8000/scrapers?tab=catalog in your browser"

scraper-install:
	cd packages/job-engine-scrapers && node install-scraper.js $(ID)

scraper-uninstall:
	cd packages/job-engine-scrapers && node install-scraper.js --uninstall $(ID)

# --- Scraper Metadata --------------------------------------------------------

scraper-metadata:
	node packages/job-engine-scrapers/dump-metadata.js

# --- Docker -----------------------------------------------------------------

DOCKER_COMPOSE := docker compose

docker-build: ## Build the dashboard image
	$(DOCKER_COMPOSE) -f docker-compose.yml build

docker-up: ## Start the dashboard (production mode)
	$(DOCKER_COMPOSE) -f docker-compose.yml up -d dashboard
	@echo "Dashboard running at http://localhost:${PORT:-8000}"

docker-down: ## Stop all containers
	$(DOCKER_COMPOSE) -f docker-compose.yml down

docker-logs: ## Tail dashboard logs
	$(DOCKER_COMPOSE) -f docker-compose.yml logs -f dashboard

docker-dev: ## Start dashboard in development mode (hot-reload), rebuilding to pick up latest code
	@echo "Starting in dev mode with hot-reload..."
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up --build dashboard

# --- App -----------------------------------------------------------------

VUE_DIR := packages/job-engine-dashboard

build: ## Build the Vue 3 SPA for production
	cd $(VUE_DIR) && npm run build

dev: ## Start Vite dev server
	cd $(VUE_DIR) && npm run dev

# --- Code Quality ------------------------------------------------------------

lint:
	@$(PY) -m ruff --version 2>/dev/null || $(PIP) install ruff -q
	$(PY) -m ruff check packages/job-engine-core/ packages/job-engine-dashboard/

format:
	@$(PY) -m ruff --version 2>/dev/null || $(PIP) install ruff -q
	$(PY) -m ruff format packages/job-engine-core/ packages/job-engine-dashboard/

typecheck:
	@$(PYRIGHT) --version >/dev/null 2>&1 || { echo "pyright not installed. Run: $(PIP) install pyright==$(PYRIGHT_VERSION)"; exit 1; }
	$(PYRIGHT) packages/job-engine-core/src/ packages/job-engine-dashboard/src/

doctor: ## Run health checks (Python version, DB, pipeline integrity, liveness)
	@$(PY) scripts/doctor.py

# --- Pipeline Integrity ------------------------------------------------------

pipeline-check: ## Run pipeline integrity scripts (liveness, reposts, db integrity)
	@$(PY) scripts/liveness_check.py
	@$(PY) scripts/detect_reposts.py
	@$(PY) scripts/db_integrity.py

liveness-check: ## Run scraper liveness check (HEAD requests to target URLs)
	@$(PY) scripts/liveness_check.py

repost-check: ## Run duplicate job detection
	@$(PY) scripts/detect_reposts.py

db-check: ## Run database integrity check
	@$(PY) scripts/db_integrity.py

check-update: ## Check for updates against GitHub releases
	@$(PY) scripts/check_update.py

# --- Currency Converter ---------------------------------------------------

refresh-rates:
	$(PY) -c "from job_engine.currency_converter import refresh_rates; print('Rates refreshed:', refresh_rates())"

rates-status:
	$(PY) -c "from job_engine.currency_converter import get_rates; r = get_rates(); print('Source:', r.source if r else 'N/A'); print('Rates available:', len(r.rates) if r else 0); print('Fetched at:', __import__('datetime').datetime.fromtimestamp(r.fetched_at).strftime('%Y-%m-%d %H:%M:%S') if r else 'N/A')"

# --- Housekeeping ------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache
	rm -rf data/scraper-output/*.json
	rm -rf $(VUE_DIR)/dist
