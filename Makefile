PYTHON ?= python

PYTEST_ARGS ?=
TEST_PROFILE_TEMPLATE ?= local-dev
TEST_PROFILE_NAME ?= ci-test

PYTHONPATH := src

test:
	$(PYTHON) -m pytest -q $(PYTEST_ARGS)

test-clean:
	AIPLANE_TEST_PROFILE_TEMPLATE="$(TEST_PROFILE_TEMPLATE)" \
	AIPLANE_TEST_PROFILE_NAME="$(TEST_PROFILE_NAME)" \
	PYTHONPATH="$(PYTHONPATH)" \
	./scripts/test-clean.sh $(PYTEST_ARGS)

format:
	python -m ruff format src tests

lint:
	python -m ruff check src tests

check: format lint test-clean

install-hooks:
	mkdir -p .githooks
	if [ ! -f .githooks/pre-push ]; then \
		echo "aiplane hook missing: .githooks/pre-push"; \
		exit 1; \
	fi
	ln -sf ../../.githooks/pre-push .git/hooks/pre-push
	printf 'Installed pre-push hook to .git/hooks/pre-push (from .githooks/pre-push).\n'
	printf 'Override: export AIPLANE_PREPUSH_MODE=backup|fast|off (default=full).\n'

.PHONY: test test-clean format lint check install-hooks
