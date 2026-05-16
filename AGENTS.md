# Repository Guidelines

## Project Structure & Module Organization

This repository contains a FastAPI + SQLite inscription retrieval system. Core application code lives in `app/`: `main.py` defines routes, `models.py` and `database.py` define persistence, `crud.py` contains database operations, and `app/services/` contains text and word-cloud helpers. Jinja2 pages are in `templates/`, while fonts and other served assets are under `app/static/`. Utility and data-processing scripts live in `scripts/`, including the Word parser. Product and architecture notes are in `docs/`. Docker files are in `docker/` and `docker-compose.yml`.

## Build, Test, and Development Commands

- `pip install -r requirements.txt`: install Python dependencies.
- `python scripts/word_parser.py`: import Word source documents from `data/raw_word/` into the SQLite database.
- `uvicorn app.main:app --reload`: run the local development server at `http://127.0.0.1:8000`.
- `python start.py`: start the server on port `8000` after checking for an existing Windows process on that port.
- `docker-compose up --build`: build and run the app in Docker.
- `python scripts/test_word_import_streaming.py`: run the current script-level import/streaming check.

## Coding Style & Naming Conventions

Use Python 3 conventions with 4-space indentation and descriptive `snake_case` names for functions, variables, and modules. Keep FastAPI route handlers small; place reusable database logic in `app/crud.py` and text-processing logic in `app/services/`. Prefer explicit imports and typed parameters where they clarify API behavior. Template files should use clear IDs/classes that match their feature area, for example search controls in `templates/index.html`.

## Testing Guidelines

There is no full test suite yet. When changing parsing, import, search, or export behavior, add or update focused scripts under `scripts/` and document the command used. Name check scripts with `test_*.py` when they are intended to be runnable verification steps. Before opening a PR, at minimum run the app locally and exercise the changed endpoint or UI workflow.

## Commit & Pull Request Guidelines

Recent history uses concise Conventional Commit prefixes such as `fix:` and `refactor:`. Follow that pattern, for example `fix: correct search pagination` or `refactor: simplify wordcloud service`. Pull requests should include a short description, the reason for the change, manual test steps or script output, and screenshots for UI changes. Link related issues or docs when applicable, especially for changes tied to files in `docs/`.

## Security & Configuration Tips

Do not commit local databases, raw Word sources, generated exports, or secrets. Keep environment-specific data under ignored `data/` paths. Validate uploaded files and preserve existing schema backfill behavior in `app/main.py` when changing database models.
