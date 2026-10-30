"""PysnmpTransport with pysnmp's request functions replaced; value conversion with real types."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pysnmp.hlapi.v3arch import asyncio as hlapi
from pysnmp.proto import errind, rfc1902, rfc1905

from aiosnmpswitch import (
    AuthProtocol,
    CommunityAuth,
    ObjectId,
    PrivProtocol,
    PysnmpTransport,
    RecordedTransport,
    SnmpAuthError,
    SnmpError,
    SnmpSwitch,
    SnmpTimeoutError,
    UsmAuth,
)
from aiosnmpswitch.transport import _auth_data, convert, oid_key


class FakeTarget:
    """Stands in for UdpTransportTarget; remembers how it was created."""

    created: list[tuple[str, Any]] = []  # noqa: RUF012 - shared by the test on purpose

    @classmethod
    async def create(cls, address: tuple[str, int], **options: Any) -> FakeTarget:
        cls.created.append((cls.__name__, address))
        if address[0] == "unresolvable":
            raise OSError("no such host")
        return cls()


class FakeTarget6(FakeTarget):
    pass


class Status:
    def __init__(self, text: str) -> None:
        self.text = text

    def __bool__(self) -> bool:
        return True

    def prettyPrint(self) -> str:
        return self.text


def bind(oid: str, value: Any) -> tuple[Any, Any]:
    return rfc1902.ObjectName(oid), value


@pytest.fixture
def fake_hlapi(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace pysnmp's targets and request functions; the test sets their answers."""
    answers: dict[str, Any] = {"get": (None, 0, 0, ()), "walk": []}
    FakeTarget.created = []
    monkeypatch.setattr(hlapi, "UdpTransportTarget", FakeTarget)
    monkeypatch.setattr(hlapi, "Udp6TransportTarget", FakeTarget6)

    async def get_cmd(*args: Any, **options: Any) -> Any:
        answers["get_options"] = options
        answers["get_count"] = len(args) - 4
        return answers["get"]

    async def walk(*args: Any, **options: Any) -> AsyncIterator[Any]:
        answers["walk_options"] = options
        for reply in answers["walk"]:
            yield reply

    def bulk_walk_cmd(*args: Any, **options: Any) -> AsyncIterator[Any]:
        answers["walked_with"] = "bulk"
        return walk(*args, **options)

    def walk_cmd(*args: Any, **options: Any) -> AsyncIterator[Any]:
        answers["walked_with"] = "next"
        return walk(*args, **options)

    monkeypatch.setattr(hlapi, "get_cmd", get_cmd)
    answers["monkeypatch"] = monkeypatch
    monkeypatch.setattr(hlapi, "bulk_walk_cmd", bulk_walk_cmd)
    monkeypatch.setattr(hlapi, "walk_cmd", walk_cmd)
    return answers


async def test_get_converts_and_skips_missing(fake_hlapi: dict[str, Any]) -> None:
    fake_hlapi["get"] = (
        None,
        0,
        0,
        (
            bind("1.3.6.1.2.1.1.5.0", rfc1902.OctetString(b"sw")),
            bind("1.3.6.1.2.1.1.9.0", rfc1905.NoSuchObject()),
        ),
    )
    transport = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c"))
    assert await transport.get(["1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.9.0"]) == {
        "1.3.6.1.2.1.1.5.0": b"sw"
    }
    assert fake_hlapi["get_options"] == {"lookupMib": False}
    assert fake_hlapi["get_count"] == 2
    await transport.close()


async def test_walk_bulk_and_v1(fake_hlapi: dict[str, Any]) -> None:
    fake_hlapi["walk"] = [
        (None, 0, 0, (bind("1.3.6.1.2.1.2.2.1.8.1", rfc1902.Integer(1)),)),
        (None, 0, 0, (bind("1.3.6.1.2.1.2.2.1.8.2", rfc1902.Integer(2)),)),
    ]
    transport = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c"))
    assert await transport.walk("1.3.6.1.2.1.2.2.1.8") == [
        ("1.3.6.1.2.1.2.2.1.8.1", 1),
        ("1.3.6.1.2.1.2.2.1.8.2", 2),
    ]
    assert fake_hlapi["walked_with"] == "bulk"
    assert fake_hlapi["walk_options"] == {"lexicographicMode": False, "lookupMib": False}

    fake_hlapi["walk"].append((None, Status("noSuchName"), 1, ()))
    fake_hlapi["walk"].append((None, 0, 0, (bind("1.3.6.1.2.1.2.2.1.8.3", rfc1902.Integer(1)),)))
    v1 = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c", version="1"))
    assert len(await v1.walk("1.3.6.1.2.1.2.2.1.8")) == 2  # stops at noSuchName
    assert fake_hlapi["walked_with"] == "next"


@pytest.mark.parametrize(
    ("error", "status", "expected", "message"),
    [
        (errind.RequestTimedOut(), 0, SnmpTimeoutError, "no answer"),
        (errind.UnknownUserName(), 0, SnmpAuthError, "UnknownUserName"),
        (errind.WrongDigest(), 0, SnmpAuthError, "WrongDigest"),
        (errind.EmptyResponse(), 0, SnmpError, "EmptyResponse"),
        (None, Status("genErr"), SnmpError, "genErr at 1"),
    ],
)
async def test_errors(
    fake_hlapi: dict[str, Any], error: Any, status: Any, expected: type[Exception], message: str
) -> None:
    transport = await PysnmpTransport.create("192.0.2.1", UsmAuth("u", "k1", "k2"))
    fake_hlapi["get"] = (error, status, 1, ())
    with pytest.raises(expected, match=message):
        await transport.get(["1.3.6.1.2.1.1.5.0"])
    fake_hlapi["walk"] = [(error, status, 1, ())]
    with pytest.raises(expected, match=message):
        await transport.walk("1.3.6.1.2.1.1")


async def test_ipv6_target_shared_engine_and_resolve_error(fake_hlapi: dict[str, Any]) -> None:
    closed: list[bool] = []

    class Engine:
        def close_dispatcher(self) -> None:
            closed.append(True)

    engine = Engine()
    transport = await PysnmpTransport.create("2001:db8::1", CommunityAuth("c"), engine=engine)
    await transport.close()
    assert closed == []  # a shared engine stays open
    assert FakeTarget.created[-1] == ("FakeTarget6", ("2001:db8::1", 161))
    with pytest.raises(SnmpError, match="cannot resolve the switch address: OSError"):
        await PysnmpTransport.create("unresolvable", CommunityAuth("c"), engine=engine)
    assert closed == []
    with pytest.raises(SnmpError, match="cannot resolve"):
        await PysnmpTransport.create("unresolvable", CommunityAuth("c"))


async def test_connect(fake_hlapi: dict[str, Any]) -> None:
    switch = await SnmpSwitch.connect("192.0.2.1", CommunityAuth("c"), timeout=1.0)
    assert isinstance(switch.transport, PysnmpTransport)
    await switch.close()


def test_auth_data() -> None:
    assert _auth_data(CommunityAuth("c")).message_processing_model == 1
    assert _auth_data(CommunityAuth("c", version="1")).message_processing_model == 0
    assert _auth_data(UsmAuth("u")).authentication_protocol == hlapi.USM_AUTH_NONE
    sha = _auth_data(UsmAuth("u", "authkey12", auth_protocol=AuthProtocol.SHA256))
    assert sha.authentication_protocol == hlapi.USM_AUTH_HMAC192_SHA256
    assert sha.privacy_protocol == hlapi.USM_PRIV_NONE
    full = _auth_data(UsmAuth("u", "authkey12", "privkey12", AuthProtocol.SHA, PrivProtocol.DES))
    assert (full.authentication_protocol, full.privacy_protocol) == (
        hlapi.USM_AUTH_HMAC96_SHA,
        hlapi.USM_PRIV_CBC56_DES,
    )


def test_convert() -> None:
    assert convert(rfc1902.Integer32(-1)) == -1
    assert convert(rfc1902.Counter64(2**40)) == 2**40
    assert convert(rfc1902.TimeTicks(100)) == 100
    assert convert(rfc1902.Gauge32(5)) == 5
    assert convert(rfc1902.IpAddress("192.0.2.1")) == b"\xc0\x00\x02\x01"
    assert convert(rfc1902.OctetString(b"\x00\x01")) == b"\x00\x01"
    assert convert(rfc1902.Bits(b"\x20")) == b"\x20"
    oid = convert(rfc1902.ObjectIdentifier("1.3.6.1"))
    assert isinstance(oid, ObjectId)
    assert oid == "1.3.6.1"
    assert convert(rfc1905.NoSuchInstance()) is None
    assert convert(rfc1905.EndOfMibView()) is None
    assert convert(rfc1902.Null()) is None


async def test_recorded_transport_sorts_numerically() -> None:
    transport = RecordedTransport({"1.3.10": 1, "1.3.9": 2, "1.30": 3})
    assert await transport.walk("1.3") == [("1.3.9", 2), ("1.3.10", 1)]
    assert await transport.get(["1.30", "1.4"]) == {"1.30": 3}
    await transport.close()
    assert oid_key("1.3.10") > oid_key("1.3.9")


async def test_real_engine_is_created_and_closed(fake_hlapi: dict[str, Any]) -> None:
    transport = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c"))
    assert isinstance(transport._engine, hlapi.SnmpEngine)
    assert "mibViewController" in transport._engine.cache  # MIBs read outside the loop
    await transport.close()


async def test_v1_get_reads_each_oid_when_one_is_missing(fake_hlapi: dict[str, Any]) -> None:
    answers = {
        "1.3.6.1.2.1.1.5.0": (None, 0, 0, (bind("1.3.6.1.2.1.1.5.0", rfc1902.OctetString(b"sw")),)),
        "1.3.6.1.2.1.1.9.0": (None, Status("noSuchName"), 1, ()),
    }
    asked: list[int] = []

    async def get(self: PysnmpTransport, oids: Any) -> Any:
        asked.append(len(oids))
        if len(oids) > 1:
            return (None, Status("noSuchName"), 2, ())
        return answers[oids[0]]

    fake_hlapi["monkeypatch"].setattr(PysnmpTransport, "_get", get)
    transport = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c", version="1"))
    values = await transport.get(["1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.9.0"])
    assert values == {"1.3.6.1.2.1.1.5.0": b"sw"}
    assert asked == [2, 1, 1]


async def test_walk_stops_after_too_many_rows(
    fake_hlapi: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from aiosnmpswitch import transport as module  # noqa: PLC0415

    monkeypatch.setattr(module, "MAX_WALK_ROWS", 2)
    fake_hlapi["walk"] = [
        (None, 0, 0, tuple(bind(f"1.3.6.1.2.1.2.2.1.8.{i}", rfc1902.Integer(1)) for i in range(3)))
    ]
    transport = await PysnmpTransport.create("192.0.2.1", CommunityAuth("c"))
    with pytest.raises(SnmpError, match="more than 2 rows"):
        await transport.walk("1.3.6.1.2.1.2.2.1.8")
