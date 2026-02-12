PYTHON ?= python3

.PHONY: init lint test

init:
	PYTHONPATH=src $(PYTHON) -m daokit init

lint:
	$(PYTHON) -m compileall src tests

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
