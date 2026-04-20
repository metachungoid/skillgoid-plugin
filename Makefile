.PHONY: test lint install-local clean

test:
	pytest

lint:
	ruff check .

install-local:
	claude plugin marketplace add .
	claude plugin install skillgoid

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ dist build *.egg-info
