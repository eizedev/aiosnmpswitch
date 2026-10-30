# AGENTS.md

Instructions for AI coding agents working on this repository. People should read
[CONTRIBUTING.md](CONTRIBUTING.md) first; this file adds what an agent tends to get wrong.

## What this is

An async, read-only Python client for managed network switches over SNMP (pysnmp 7), using
standard MIBs only. It is a library for others (Home Assistant integrations, scripts), so its
public API, error types and docs are a contract.

## Commands

```sh
uv sync                       # environment from uv.lock
uv run pytest                 # tests, including property-based tests (Hypothesis)
uv run pytest --cov           # coverage must stay at 100 %
uv run ruff check . && uv run ruff format --check .
uv run mypy                   # strict
```

## Rules that matter here

- **Read-only.** The transport has `get` and `walk` only. Never add SET requests or a method that
  changes a switch.
- **Standard MIBs**, as constants in `src/aiosnmpswitch/oids.py` named after the MIB object.
  Walk only the tables a getter needs: vendor trees can hold hundreds of thousands of entries. A
  vendor table only where the standard one is missing, measured on the model, read only for its
  `sysObjectID` and only its columns (the HPE 1930 temperatures; constants at the end of
  `oids.py`).
- **Models mirror the MIBs** (docs/design.md): frozen dataclasses, field names are MIB objects in
  snake_case without the table prefix, MIB units. Interpretation goes into `helpers.py`.
- **Parsers never raise.** Use the converters in `_parse.py`; `tests/test_robustness.py` fuzzes
  every getter and helper.
- **Every new table needs a fixture** recorded on a real switch with
  `aiosnmpswitch-diagnostics <switch> --record <name>.raw.json` and anonymized with
  `scripts/anonymize.py` (all switches of one network in one run). Never commit raw recordings
  (`*.raw.json` and `raw/` are ignored). The script is an allowlist: a new octet-string column
  stops it until the column is added to one of its lists. Check the output by eye as well.
- **Vendor quirks** are handled only where measured on a device, and documented in
  `docs/compatibility.md` and the docstring.
- **Errors never carry secrets**: no community, key or packet in an exception or log message.
- **Docs describe the current state**: update `docs/` (the website), `README.md` and
  `CHANGELOG.md` (Keep a Changelog, under `[Unreleased]`) in the same change.
- **Website**: `docs/` and `zensical.toml`, built by `.github/workflows/docs.yml` with the shared
  design from eizedev/brand (`docs-site/`); `docs/assets/site.css` is copied in at build time and
  not committed.
- Commit messages follow Conventional Commits.
- **`.claude/settings.json`** keeps claude.ai session links out of commits and pull requests
  (`attribution.sessionUrl: false`) and denies reads of secret files. Cloud sessions read only
  this settings file, so keep these keys.

## Don'ts

- Don't contact real switches from tests; use `RecordedTransport` with the fixtures.
- Don't widen dependency ranges or add dependencies without a reason in the pull request.
- Don't edit generated files: `src/aiosnmpswitch/_version.py`, `uv.lock` by hand.
