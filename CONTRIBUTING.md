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

For step 3 to run automatically, release-please must push the tag with a token other than the
default `GITHUB_TOKEN` (GitHub does not run workflows off events created by that token). This
repo uses a **GitHub App** token (no expiring secret to rotate). One-time setup:

1. Create a GitHub App (*Settings → Developer settings → GitHub Apps → New*) with repository
   permissions **Contents: Read and write** and **Pull requests: Read and write**. Generate a
   private key.
2. Install the App on the `keplersj/ambient2mqtt` repository.
3. Add the App's ID as the repository **variable** `RELEASE_APP_ID`, and the private key as the
   repository **secret** `RELEASE_APP_PRIVATE_KEY` (*Settings → Secrets and variables → Actions*).

`release-please.yaml` then mints a short-lived installation token per run via
`actions/create-github-app-token`. Until the App is configured, it falls back to `GITHUB_TOKEN`:
the release PR still works, but you cut the release by pushing the tag yourself —
`git tag vX.Y.Z && git push origin vX.Y.Z`.

## Please don't

- Commit credentials, tokens, JWTs, or real account/device identifiers.
- Add vendor-copyrighted material (decompiled code, proprietary assets) or anything
  that circumvents a technical protection measure. This project is a clean interop
  client and stays that way.
