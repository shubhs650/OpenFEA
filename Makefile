SHELL := /bin/bash
.DELETE_ON_ERROR:
.DEFAULT_GOAL := help
export UV_CACHE_DIR ?= $(CURDIR)/.local/cache/uv
export npm_config_cache ?= $(CURDIR)/.local/cache/npm
export PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.local/browsers
export PYTHONPATH := $(CURDIR)/services/api:$(CURDIR)/services/worker
export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/.local/native/bin:$(PATH)
PY := .venv/bin/python

.PHONY: help setup setup-native native-report doctor dev lint typecheck test-unit test-integration check build contracts contracts-check docs-check test-native test-e2e benchmark benchmark-all test-security test-reports smoke feasibility resource-browser
help:
	@echo 'setup doctor dev check build smoke test-e2e docs-check contracts'
	@echo 'test-native verifies real tools/mapping/loads/stress/bonds; benchmark CASE=B01–B05, B07 or B09 DEVELOPMENT=1.'
	@echo 'feasibility runs native cleanup diagnostics; MESHES=1 measures bounded workloads. resource-browser OUTPUT=<directory>.'
	@echo 'Release benchmark acceptance, benchmark-all, full security and reports remain BLOCKED.'
setup:
	bash scripts/codex/setup.sh
setup-native:
	$(PY) scripts/native/install.py
native-report:
	$(PY) scripts/native/report.py
doctor:
	bash scripts/codex/check.sh
dev:
	bash scripts/codex/start.sh
lint:
	.venv/bin/ruff check services migrations scripts tests
	.venv/bin/ruff format --check services migrations scripts tests
	npm run lint
typecheck:
	.venv/bin/mypy
	npm run typecheck
test-unit:
	$(PY) -m pytest
	npm run test:unit
test-integration:
	$(PY) -m pytest tests/integration
check: lint typecheck test-unit contracts-check docs-check
build:
	npm run build
contracts:
	$(PY) scripts/ci/contracts.py
contracts-check:
	$(PY) scripts/ci/contracts.py --check
docs-check:
	$(PY) scripts/ci/docs_check.py
smoke:
	bash scripts/codex/start.sh --smoke
test-e2e:
	npm run test:e2e
test-native:
	$(PY) -m pytest tests/native
benchmark:
	$(PY) scripts/native/benchmark.py $(CASE) $(if $(filter 1,$(DEVELOPMENT)),--development,)
feasibility:
	$(PY) scripts/native/feasibility.py $(if $(filter 1,$(MESHES)),--meshes,)
resource-browser:
	node scripts/native/resource-browser.mjs $(OUTPUT) $(if $(filter 1,$(HEADED)),--headed,)
benchmark-all:
	@bash scripts/ci/blocked.sh 'release benchmarks' 'reviewed manifests and native pipeline'
test-security:
	@bash scripts/ci/blocked.sh 'full security suite' 'archive, hosted auth, caps and lease-race implementations; T007 local ownership/session guards run in test-unit'
test-reports:
	@bash scripts/ci/blocked.sh 'reports' 'T025-T026'
