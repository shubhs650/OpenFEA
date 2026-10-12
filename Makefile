SHELL := /bin/bash
.DELETE_ON_ERROR:
.DEFAULT_GOAL := help
export UV_CACHE_DIR ?= $(CURDIR)/.local/cache/uv
export npm_config_cache ?= $(CURDIR)/.local/cache/npm
export PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.local/browsers
export PYTHONPATH := $(CURDIR)/services/api
export PATH := $(CURDIR)/.venv/bin:$(PATH)
PY := .venv/bin/python

.PHONY: help setup doctor dev lint typecheck test-unit test-integration check build contracts contracts-check docs-check test-native test-e2e benchmark benchmark-all test-security test-reports smoke
help:
	@echo 'setup doctor dev check build smoke test-e2e docs-check contracts'
	@echo 'Native, benchmark, full security and report targets fail as BLOCKED until implemented.'
setup:
	bash scripts/codex/setup.sh
doctor:
	bash scripts/codex/check.sh
dev:
	bash scripts/codex/start.sh
lint:
	.venv/bin/ruff check services scripts tests
	.venv/bin/ruff format --check services scripts tests
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
	@bash scripts/ci/blocked.sh 'native integration' 'T002-T005'
benchmark:
	@bash scripts/ci/blocked.sh 'benchmark $(CASE)' 'reviewed manifests and native pipeline'
benchmark-all:
	@bash scripts/ci/blocked.sh 'release benchmarks' 'reviewed manifests and native pipeline'
test-security:
	@bash scripts/ci/blocked.sh 'full security suite' 'ownership, archive and job implementations; local startup guards run in test-unit'
test-reports:
	@bash scripts/ci/blocked.sh 'reports' 'T025-T026'
