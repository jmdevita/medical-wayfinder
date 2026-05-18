# Atlas dev tooling.
#
# Reuses the repo-root `env/` virtualenv (created elsewhere for tools/ and
# training/). The backend imports from tools/, so sharing one venv is the
# right call — see CLAUDE.md.
#
# If you have not yet created env/, run `make bootstrap-env` once.

REPO_ROOT := $(realpath ..)
VENV      := $(REPO_ROOT)/env
PY        := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip
UVICORN   := $(VENV)/bin/uvicorn

# Load atlas/.env if present (gitignored). All variables are exported to
# every recipe so uvicorn / npm pick them up. -include is non-fatal when
# the file is absent. The same file is auto-loaded by docker-compose.
-include .env
export

.PHONY: install install-frontend install-backend dev dev-frontend dev-backend build typecheck bootstrap-env env-check

install: install-frontend install-backend

install-frontend:
	cd frontend && npm install

install-backend:
	@if [ ! -x "$(PY)" ]; then \
		echo "No virtualenv at $(VENV). Run 'make bootstrap-env' first."; \
		exit 1; \
	fi
	$(PIP) install --upgrade pip
	$(PIP) install -e backend[dev]

# One-time: create the repo-root env/ virtualenv if it doesn't exist.
bootstrap-env:
	@if [ -d "$(VENV)" ]; then \
		echo "Virtualenv already exists at $(VENV)"; \
	else \
		python3 -m venv "$(VENV)" && \
		"$(VENV)/bin/pip" install --upgrade pip; \
	fi

# Run frontend (5173) and backend (8000) concurrently.
# Foregrounds the backend; frontend logs land in atlas/.frontend.log.
dev:
	@echo "Frontend → http://localhost:5173"
	@echo "Backend  → http://localhost:8000  (docs: /docs)"
	cd frontend && npm run dev > ../.frontend.log 2>&1 &
	cd backend  && $(UVICORN) app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && $(UVICORN) app.main:app --reload --port 8000

build:
	cd frontend && npm run build

typecheck:
	cd frontend && npm run typecheck

# Confirm atlas/.env is being loaded. Only prints whether each var is set,
# never the value, so this is safe to run in shared terminals.
env-check:
	@echo "atlas/.env loaded? checking key presence (values not printed)"
	@for v in GOOGLE_MAPS_API_KEY ATLAS_AUTH_ENABLED ATLAS_RATE_LIMIT_ENABLED ATLAS_REDIS_URL OPENAI_BASE_URL; do \
		if [ -n "$${!v}" ]; then echo "  $$v = (set)"; else echo "  $$v = (unset)"; fi; \
	done
