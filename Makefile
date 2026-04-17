.PHONY: test lint install-local clean

test:
	pytest

lint:
	ruff check .

install-local:
	claude plugin install .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ dist build *.egg-info
