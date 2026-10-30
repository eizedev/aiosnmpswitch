## Summary

<!-- What does this change, and why? -->

## Test plan

<!-- How did you verify it? Name the switch model and firmware if you tested on a device. -->

- [ ] `uv run pytest --cov`, `uv run mypy`, `uv run ruff check .` pass
- [ ] Only reads (GET, GETNEXT, GETBULK); new OIDs are standard MIB objects in `oids.py`
- [ ] New fixtures are anonymized with `scripts/anonymize.py` and checked by eye
- [ ] No personal data (addresses, host names, network layout) in code, docs or fixtures
- [ ] Breaking changes are marked as such in `CHANGELOG.md`
- [ ] `CHANGELOG.md` and, if relevant, `docs/` updated
