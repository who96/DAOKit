PYTHON ?= python3
RELEASE_CHECK_LOG ?= .artifacts/release-check/verification.log
RELEASE_CHECK_SUMMARY ?= .artifacts/release-check/summary.json
CRITERIA_MAP ?= docs/reports/criteria-map.json
CRITERIA_LINKAGE_SUMMARY ?= .artifacts/release-check/criteria-linkage-check.json
RELIABILITY_GATE_LOG ?= .artifacts/reliability-gate/verification.log
RELIABILITY_GATE_SUMMARY ?= .artifacts/reliability-gate/summary.json

.PHONY: init lint test release-check gate-release-check gate-criteria-linkage gate-reliability-readiness gate-template-checks ci-hardening-gate

init:
	PYTHONPATH=src $(PYTHON) -m daokit init

lint:
	$(PYTHON) -m compileall src tests

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

release-check:
	PYTHONPATH=src $(PYTHON) -m cli.release_check \
		--verification-log "$(RELEASE_CHECK_LOG)" \
		--summary-json "$(RELEASE_CHECK_SUMMARY)" \
		--working-directory "$(CURDIR)"

gate-release-check: release-check

gate-criteria-linkage:
	PYTHONPATH=src $(PYTHON) scripts/check_criteria_linkage.py \
		--criteria-map "$(CRITERIA_MAP)" \
		--summary-json "$(CRITERIA_LINKAGE_SUMMARY)"

gate-reliability-readiness:
	PYTHONPATH=src $(PYTHON) -m verification.reliability_gate \
		--verification-log "$(RELIABILITY_GATE_LOG)" \
		--summary-json "$(RELIABILITY_GATE_SUMMARY)" \
		--working-directory "$(CURDIR)"

gate-template-checks:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests/templates -p 'test_*.py' -v

ci-hardening-gate: gate-release-check gate-reliability-readiness gate-criteria-linkage gate-template-checks
