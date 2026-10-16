SHELL := /bin/bash
.DELETE_ON_ERROR:
.DEFAULT_GOAL := help
export UV_CACHE_DIR ?= $(CURDIR)/.local/cache/uv
export npm_config_cache ?= $(CURDIR)/.local/cache/npm
export PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.local/browsers
export PYTHONPATH := $(CURDIR)/services/api:$(CURDIR)/services/worker
export PATH := $(CURDIR)/.venv/bin:$(CURDIR)/.local/native/bin:$(PATH)
PY := .venv/bin/python

.PHONY: help setup setup-native native-report doctor dev lint typecheck test-unit test-integration check build contracts contracts-check docs-check test-native test-e2e benchmark benchmark-m3 benchmark-m4 m4-review local-profile benchmark-all test-security test-reports smoke feasibility resource-browser
help:
	@echo 'setup doctor dev check build smoke test-e2e docs-check contracts'
	@echo 'test-native verifies real tools/mapping/loads/stress/bonds/references; benchmark CASE=B01–B14 DEVELOPMENT=1 OUTPUT=<fresh-directory>.'
	@echo 'feasibility runs native cleanup diagnostics; MESHES=1 measures bounded workloads. resource-browser OUTPUT=<directory>.'
	@echo 'test-reports checks real A4 PDF content/layout; release benchmarks/full security remain BLOCKED.'
	@echo 'm4-review prints exact pending approvals; benchmark-m4 DEVELOPMENT=1 OUTPUT=<fresh-directory> replays all 14 cases without granting acceptance.'
	@echo 'local-profile OUTPUT=<new-json-file> SCRATCH=<existing-directory> records hardware/headroom; see docs/LOCAL_ACCEPTANCE.md for Windows/human checks.'
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
	$(PY) scripts/native/benchmark.py $(CASE) $(if $(filter 1,$(DEVELOPMENT)),--development,) $(if $(OUTPUT),--output '$(OUTPUT)',)
benchmark-m3:
	$(PY) scripts/validation/m3_gate.py $(if $(filter 1,$(DEVELOPMENT)),--development,) $(if $(OUTPUT),--output '$(OUTPUT)',)
benchmark-m4:
	$(PY) -m scripts.validation.m4_gate $(if $(filter 1,$(DEVELOPMENT)),--development,) $(if $(OUTPUT),--output '$(OUTPUT)',)
m4-review:
	$(PY) -m scripts.validation.m4_gate --review-packet
local-profile:
	$(PY) -m scripts.validation.local_profile --output '$(OUTPUT)' $(if $(SCRATCH),--scratch '$(SCRATCH)',)
feasibility:
	$(PY) scripts/native/feasibility.py $(if $(filter 1,$(MESHES)),--meshes,)
resource-browser:
	node scripts/native/resource-browser.mjs $(OUTPUT) $(if $(filter 1,$(HEADED)),--headed,)
benchmark-all:
	@bash scripts/ci/blocked.sh 'release benchmarks' 'reviewed manifests and native pipeline'
test-security:
	@bash scripts/ci/blocked.sh 'full security suite' 'archive, hosted auth, caps and lease-race implementations; T007 local ownership/session guards run in test-unit'
test-reports:
	$(PY) -m pytest tests/reports
