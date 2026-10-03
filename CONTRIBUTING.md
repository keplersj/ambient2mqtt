# Contributing

Thanks for your interest! This is a small, best-effort personal project.

## Dev setup

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run ty check          # advisory for now
uv run pytest
```

## Pull requests

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `chore:` …) — releases and the changelog are automated
  by [release-please](https://github.com/googleapis/release-please) from these.
- Keep CI green (ruff, pytest). `ty` is advisory until the codebase is fully typed.
- Add/adjust tests for behavior changes. Tests must not require live credentials or
  network access.

## Please don't

- Commit credentials, tokens, JWTs, or real account/device identifiers.
- Add vendor-copyrighted material (decompiled code, proprietary assets) or anything
  that circumvents a technical protection measure. This project is a clean interop
  client and stays that way.
