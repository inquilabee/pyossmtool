sync:
	uv sync --all-groups

test:
	uv run pytest -q

integration:
	uv run pytest -m integration -q

format:
	uv run ruff format .

ruff:
	uv run ruff check . --fix

check-commit:
	uv run shipgate install
	uv run shipgate check
	uv run ruff format --check .
	uv run ruff check .
	uv run pytest -q

install-hooks:
	uv run pre-commit install

build:
	uv build

publish-check: build
	uv run python -c "import glob, zipfile; paths=glob.glob('dist/*.whl'); assert paths, 'no wheel'; z=zipfile.ZipFile(paths[-1]); z.testzip(); print(paths[-1], 'ok')"

.PHONY: build check-commit format install-hooks integration publish-check ruff sync test
