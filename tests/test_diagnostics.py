"""The diagnostics command: summary without values, recordings, credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aiosnmpswitch import (
    CommunityAuth,
    ObjectId,
    PrivProtocol,
    PysnmpTransport,
    RecordedTransport,
    SnmpTimeoutError,
    UsmAuth,
)
from aiosnmpswitch import diagnostics as diag

from .conftest import RECORDINGS, recorded


async def test_summary_holds_no_values() -> None:
    lines = await diag.summary(recorded("switch-1"))
    text = "\n".join(lines)
    assert lines[0].startswith("model: HPE OfficeConnect Switch 1920S")
    assert "address table: 39 entries, with VLAN" in text
    assert "trunks: 2 with members" in text
    assert "PoE: 1 supplies, 4 ports" in text
    assert "neighbours 2 on 2 mapped ports" in text
    assert "02:00" not in text
    assert "switch-" not in text
    assert "192.0.2" not in text


def test_encode_decode_round_trip() -> None:
    for value in (5, b"\x00\xff", ObjectId("1.3.6")):
        assert diag.decode(diag.encode(value)) == value
    assert isinstance(diag.decode({"oid": "1.3"}), ObjectId)
    with pytest.raises(ValueError, match="not a recorded value"):
        diag.decode(True)
    with pytest.raises(ValueError, match="not a recorded value"):
        diag.decode("text")


def test_load_recording_checks_format(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"format": 99, "values": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown recording format 99"):
        diag.load_recording(path)


async def test_record_answers_every_getter() -> None:
    source = recorded("switch-3")
    values = await diag.record(source.transport)
    assert values == diag.load_recording(RECORDINGS["switch-3"])


def args(*argv: str) -> Any:
    return diag.parse_args(["192.0.2.1", *argv])


def test_auth_from_environment_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return "typed"

    monkeypatch.setattr("getpass.getpass", ask)
    assert diag._auth(args(), {"SNMP_COMMUNITY": "env"}) == CommunityAuth("env")
    assert diag._auth(args("--version", "1"), {}) == CommunityAuth("typed", "1")
    usm = diag._auth(args("--user", "u", "--priv-protocol", "des"), {"SNMP_AUTH_KEY": "a"})
    assert usm == UsmAuth("u", "a", "typed", priv_protocol=PrivProtocol.DES)
    plain = diag._auth(
        args("--user", "u", "--auth-protocol", "none", "--priv-protocol", "none"), {}
    )
    assert plain == UsmAuth("u", None, None, auth_protocol="none", priv_protocol="none")  # type: ignore[arg-type]
    prompted = diag._auth(args("--user", "u", "--priv-protocol", "none"), {})
    assert prompted == UsmAuth("u", "typed", None, priv_protocol=PrivProtocol.NONE)
    assert asked == ["Community: ", "Privacy key: ", "Authentication key: "]


@pytest.fixture
def recorded_create(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """PysnmpTransport.create answers from switch-1's recording."""
    created: list[Any] = []

    async def create(host: str, auth: Any, **options: Any) -> RecordedTransport:
        created.append((host, auth, options))
        transport = recorded("switch-1").transport
        assert isinstance(transport, RecordedTransport)
        return transport

    monkeypatch.setattr(PysnmpTransport, "create", create)
    return created


async def test_run_summary_and_record(
    recorded_create: list[Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = {"SNMP_COMMUNITY": "c"}
    assert await diag.run(args("--timeout", "2"), environ) == 0
    assert "model: HPE" in capsys.readouterr().out
    assert recorded_create[0][2] == {"port": 161, "timeout": 2.0}
    target = tmp_path / "switch.raw.json"
    assert await diag.run(args("--record", str(target)), environ) == 0
    assert "anonymize before sharing" in capsys.readouterr().out
    assert diag.load_recording(target) == diag.load_recording(RECORDINGS["switch-1"])


async def test_run_reports_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Silent(RecordedTransport):
        async def walk(self, oid: str) -> list[Any]:
            raise SnmpTimeoutError("no answer from the switch")

    async def create(host: str, auth: Any, **options: Any) -> Silent:
        return Silent({})

    monkeypatch.setattr(PysnmpTransport, "create", create)
    assert await diag.run(args(), {"SNMP_COMMUNITY": "c"}) == 1
    assert "error: no answer from the switch" in capsys.readouterr().err


def test_main(recorded_create: list[Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNMP_COMMUNITY", "c")
    assert diag.main(["192.0.2.1"]) == 0
