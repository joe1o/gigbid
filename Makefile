# Makefile - short names for common commands (make dev | test | eval | seed | demo | lint).
# On Windows without `make`, run the commands on the right directly.
PY ?= python

.PHONY: install dev test lint seed eval eval-smoke demo web e2e

install:            ## install Python + web dependencies
	$(PY) -m pip install -e ".[dev]"
	cd apps/web && npm ci

dev:                ## run every service locally (GigSim, 3 MCP servers, API + web) on :8000
	cd apps/web && npm run build
	$(PY) scripts/run_all.py

test:               ## unit, integration and contract tests
	$(PY) -m pytest -q

lint:
	ruff check .

seed:               ## regenerate GigSim jobs + gold labels (deterministic)
	$(PY) -m gigsim.seed

eval:               ## retrieval metrics + full decision/outcome eval -> evals/results/*.json
	$(PY) -m evals.runners.rag_eval
	$(PY) -m evals.runners.decision_eval

eval-smoke:         ## 30-job smoke eval with the fake model + CI thresholds
	$(PY) -m evals.runners.decision_eval --fake --smoke

demo:               ## rehearse degraded mode against a running `make dev`
	$(PY) scripts/degraded_mode_check.py

e2e:                ## Playwright browser tests
	cd apps/web && npx playwright test
