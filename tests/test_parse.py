"""Converters: wrong types become None, special formats are read as the MIBs define them."""

from __future__ import annotations

from aiosnmpswitch import ObjectId, OperStatus
from aiosnmpswitch._parse import (
    bridge_id,
    capabilities,
    ip_from_octets,
    lldp_id,
    network_address,
    to_enum,
    to_hex,
    to_int,
    to_mac,
    to_oid,
    to_str,
    to_truth,
)


def test_wrong_types_are_none() -> None:
    assert to_int(b"1") is None
    assert to_str(5) is None
    assert to_str(ObjectId("1.3")) is None
    assert to_oid(b"1.3") is None
    assert to_mac(ObjectId("1.2.3.4.5.6")) is None
    assert to_hex(7) is None
    assert to_enum(OperStatus, b"\x01") is None
    assert to_truth(b"\x01") is None
    assert lldp_id(4, 5, chassis=True) is None


def test_values() -> None:
    assert to_str(b"name\x00 ") == "name"
    assert to_str(b"") is None
    assert to_oid(ObjectId("1.3.6")) == "1.3.6"
    assert to_mac(b"\x02\x00\x00\x00\x00\x01") == "02:00:00:00:00:01"
    assert to_mac(b"\x02") is None
    assert to_hex(b"\xab") == "ab"
    assert to_enum(OperStatus, 1) is OperStatus.UP
    assert to_enum(OperStatus, 99) is None
    assert (to_truth(1), to_truth(2), to_truth(3)) == (True, False, None)


def test_bridge_id() -> None:
    assert bridge_id(b"\x80\x00\x02\x00\x00\x00\x00\x01") == "8000.020000000001"
    assert bridge_id(b"\x80\x00") == "8000"  # unexpected length: plain hex
    assert bridge_id(None) is None


def test_lldp_ids() -> None:
    mac = b"\x02\x00\x00\x00\x00\x01"
    assert lldp_id(4, mac, chassis=True) == "02:00:00:00:00:01"
    assert lldp_id(3, mac, chassis=False) == "02:00:00:00:00:01"
    assert lldp_id(4, b"\x02\x00", chassis=True) == "0200"  # a MAC subtype with the wrong length
    assert lldp_id(5, b"\x01\xc0\x00\x02\x01", chassis=True) == "192.0.2.1"
    assert lldp_id(4, b"\x01\xc0\x00\x02\x01", chassis=False) == "192.0.2.1"
    assert lldp_id(5, b"\x09\x01", chassis=True) == "0901"  # unknown address family
    assert lldp_id(5, b"gi1", chassis=False) == "gi1"
    assert lldp_id(7, b"\x00", chassis=False) == "00"  # not printable: hex
    assert lldp_id(7, b"  ", chassis=False) is None


def test_network_addresses() -> None:
    assert network_address(b"") is None
    assert network_address(b"\x02" + bytes(15) + b"\x01") == "::1"
    assert ip_from_octets([192, 0, 2, 1]) == "192.0.2.1"
    assert ip_from_octets(b"\x01\x02") is None


def test_capabilities() -> None:
    assert capabilities(b"\x28") == {"bridge", "router"}
    assert capabilities(b"\x20\x00") == {"bridge"}
    assert capabilities(b"\x00\x20") == {"bridge"}  # HPE 1920S: octets swapped
    assert capabilities(b"") == frozenset()
    assert capabilities(ObjectId("1")) == frozenset()
    assert capabilities(3) == frozenset()
