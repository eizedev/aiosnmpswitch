# Contributing

Thanks for helping. The most useful contribution is often a report from a switch model or
firmware that is not tested yet.

## Reporting a model or firmware

Open an issue with the **Model or firmware report** form and tell us the model and the firmware.
Never paste raw SNMP output: it contains your MAC addresses, IP addresses and device names.
Instead, run the diagnostics command and paste its output; it describes what the switch answers
without any of the values:

```sh
pip install aiosnmpswitch
aiosnmpswitch-diagnostics <switch address>                  # SNMPv2c
aiosnmpswitch-diagnostics <switch address> --user <v3 user>  # SNMPv3
```

## Where help is wanted

Issues labelled [`help wanted`](https://github.com/eizedev/aiosnmpswitch/labels/help%20wanted)
need someone with hardware the maintainer does not have, for example another vendor's switch. Issues
labelled [`roadmap`](https://github.com/eizedev/aiosnmpswitch/labels/roadmap) describe what is
planned next. Other labels:

| Label | Meaning |
| --- | --- |
| `bug` | something does not work as documented |
| `enhancement` | something the library should read or do |
| `compatibility` | a report about a model, firmware or setup |
| `needs device test` | implemented, but not checked on a real device yet |
| `breaking change` | changes the public API |
| `security` | a security-relevant change (report vulnerabilities privately, see SECURITY.md) |
| `documentation` | docs only |
| `dependencies` | dependency updates, usually from Dependabot |

## Development setup

You need [uv](https://docs.astral.sh/uv/) 0.13 and Python 3.12 or newer. `pyproject.toml` pins
uv to 0.13.x (`[tool.uv] required-version`), because CI reads the version from there and
`uv.lock` must not change between uv versions; another uv refuses to run in this repository.
Install 0.13 (`uv self update 0.13.5`, or `pipx install uv==0.13.5`); a change of the pin comes
as a pull request of its own, together with the lock file.

```sh
git clone https://github.com/eizedev/aiosnmpswitch.git
cd aiosnmpswitch
uv sync
uv run pytest
```

Before opening a pull request, all of these must pass (CI runs the same):

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

## Rules for changes

- **Read-only stays read-only.** The transport has `get` and `walk` only. Pull requests that add
  a SET request are not accepted.
- **Every new table needs a fixture** from a real switch: record it with
  `aiosnmpswitch-diagnostics <switch> --record <name>.raw.json` and anonymize all switches of one
  network in one run with
  `python scripts/anonymize.py <a.raw.json> tests/fixtures/<model>-<firmware>/<a>.json ...`.
  The script refuses to write anything when an octet-string column is not classified yet (add it
  to one of its lists) or an original value is left; check the output by eye as well.
- `tests/test_privacy.py` fails on MAC and IP addresses that may be real, in the files and in
  every line your unpushed commits add. Run the tests before you push: removing an address in a
  later commit leaves it in the history, so fix the commit that added it instead.
- **Models mirror the MIBs.** Name fields after the MIB objects (snake_case, without the table
  prefix), keep the MIB's units, and put anything derived into `helpers.py`. Vendor quirks are
  handled only where measured on a device, and documented in `docs/compatibility.md`.
- Update [docs/compatibility.md](docs/compatibility.md), the other pages in `docs/` where they
  describe what you changed, and [CHANGELOG.md](CHANGELOG.md). `docs/` is the website at
  https://aiosnmpswitch.eize.dev/.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, ...).

## Releases

Maintainers first merge a pull request that turns `[Unreleased]` in `CHANGELOG.md` into
`[X.Y.Z] - date` (with its compare link at the bottom), then tag `vX.Y.Z` on `main`. The release
workflow runs the full CI, builds, checks with `scripts/release_notes.py` that the built version is
the tag's and that the CHANGELOG has its section, publishes to PyPI via trusted publishing and
creates the GitHub release with that section as its notes. No tokens are stored in the repository.
The build requirements are pinned with hashes in `build-constraints.txt`; refresh them with

```sh
printf 'hatchling>=1.27\nhatch-vcs>=0.4\n' | uv pip compile - --generate-hashes --python-version 3.12 --no-header -o build-constraints.txt
```

and put the two comment lines at the top back. Do this before each release; Dependabot does not
update this file.
