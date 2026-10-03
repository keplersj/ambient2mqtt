# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's
[private vulnerability reporting](https://github.com/keplersj/ambient2mqtt/security/advisories/new)
rather than opening a public issue. I'll acknowledge within a few days.

## Scope / handling

`ambient2mqtt` handles your Ambient and MQTT credentials. It reads them from
environment variables only, never logs them, and never commits them. Please do
**not** include real credentials, tokens, JWTs, or account/device identifiers in
issues, logs, or pull requests — redact them first.
