PYTHON ?= python3
RELEASE_CHECK_LOG ?= .artifacts/release-check/verification.log
RELEASE_CHECK_SUMMARY ?= .artifacts/release-check/summary.json

.PHONY: init lint test release-check

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
