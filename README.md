# python-template

A modern Python project template using [uv](https://docs.astral.sh/uv/) for
dependency management, [hatchling](https://hatch.pypa.io/) as the build
backend, [Ruff](https://docs.astral.sh/ruff/) for linting/formatting,
[mypy](https://mypy.readthedocs.io/) for type checking, [pytest](https://docs.pytest.org/)
for testing, [pre-commit](https://pre-commit.com/) for git hooks, and
[pip-audit](https://pypi.org/project/pip-audit/) for dependency vulnerability scanning.

## Setup

```bash
uv sync
uv run pre-commit install
```

## Usage

```bash
uv run python-template
```

## Development

```bash
# Run tests with coverage
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy

# Scan dependencies for known vulnerabilities
uv run pip-audit

# Run all pre-commit hooks against every file
uv run pre-commit run --all-files
```
