.PHONY: install test lint format type-check security clean help

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements-dev.txt

test:  ## Run tests with coverage
	pytest

test-fast:  ## Run tests without coverage
	pytest --no-cov

lint:  ## Run all linting checks
	flake8 .
	black --check .
	isort --check-only .

format:  ## Format code with black and isort
	black .
	isort .

type-check:  ## Run type checking with mypy
	mypy main.py --ignore-missing-imports

security:  ## Run security checks
	bandit -r . -f json -o bandit-report.json
	safety check

clean:  ## Clean up generated files
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf bandit-report.json
	rm -rf safety-report.json
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

ci:  ## Run all CI checks locally
	make lint
	make type-check
	make test
	make security