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

## Releasing

Releases are automated with [release-please](https://github.com/googleapis/release-please):

1. Conventional-commit PRs land on `main`.
2. release-please maintains a "release PR" that bumps the version + CHANGELOG (and the
   chart's `version`/`appVersion`). Merging it tags `vX.Y.Z` and cuts a GitHub Release.
3. `release.yaml` (triggered by the `v*` tag) builds and pushes the multi-arch image to
   `ghcr.io/keplersj/ambient2mqtt` and the Helm chart to `oci://ghcr.io/keplersj/charts`.

For step 3 to run automatically, release-please must push the tag with a token other than
the default `GITHUB_TOKEN` (GitHub does not run workflows off events created by that token).
Create a repository secret **`RELEASE_PLEASE_TOKEN`**:

- a fine-grained PAT scoped to this repo with **Contents: Read and write** and
  **Pull requests: Read and write** (a classic PAT with `repo` also works), or a GitHub App
  installation token;
- add it under *Settings → Secrets and variables → Actions*.

Without that secret, release-please still manages the release PR, but you cut the release by
pushing the tag yourself: `git tag vX.Y.Z && git push origin vX.Y.Z`.

## Please don't

- Commit credentials, tokens, JWTs, or real account/device identifiers.
- Add vendor-copyrighted material (decompiled code, proprietary assets) or anything
  that circumvents a technical protection measure. This project is a clean interop
  client and stays that way.
