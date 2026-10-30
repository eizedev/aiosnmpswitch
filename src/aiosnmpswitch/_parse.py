"""Converters from raw SNMP values; they never raise, a value of the wrong type becomes ``None``."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from enum import IntEnum

from .transport import ObjectId, Value

LLDP_CAPABILITIES = (
    "other",
    "repeater",
    "bridge",
    "wlanAccessPoint",
    "router",
    "telephone",
    "docsisCableDevice",
    "stationOnly",
)

# LLDP chassis and port ID subtypes that carry a MAC address or a network address.
_CHASSIS_MAC, _CHASSIS_NETWORK = 4, 5
_PORT_MAC, _PORT_NETWORK = 3, 4
_MAC_LENGTH = 6
_IPV4_FAMILY, _IPV6_FAMILY = 1, 2


def to_int(value: Value | None) -> int | None:
    """Return an integer value, or ``None``."""
    return value if isinstance(value, int) else None


def to_str(value: Value | None) -> str | None:
    """Return a DisplayString as text, or ``None``; drop trailing NUL bytes and spaces."""
    if isinstance(value, ObjectId) or not isinstance(value, bytes):
        return None
    return value.decode("utf-8", errors="replace").rstrip("\x00 ") or None


def to_oid(value: Value | None) -> str | None:
    """Return an OID value, or ``None``."""
    return str(value) if isinstance(value, ObjectId) else None


def to_mac(value: Value | None) -> str | None:
    """Six octets as ``aa:bb:cc:dd:ee:ff``; anything else is ``None``."""
    if isinstance(value, bytes) and not isinstance(value, ObjectId) and len(value) == _MAC_LENGTH:
        return value.hex(":")
    return None


def to_hex(value: Value | None) -> str | None:
    """Octets as lowercase hex without separators, or ``None``."""
    if isinstance(value, bytes) and not isinstance(value, ObjectId):
        return value.hex()
    return None


def to_enum[E: IntEnum](enum: type[E], value: Value | None) -> E | None:
    """Return a member of ``enum``, or ``None`` for unknown numbers."""
    if not isinstance(value, int):
        return None
    try:
        return enum(value)
    except ValueError:
        return None


def to_truth(value: Value | None) -> bool | None:
    """SNMP TruthValue: 1 is true, 2 is false."""
    return {1: True, 2: False}.get(value) if isinstance(value, int) else None


def bridge_id(value: Value | None) -> str | None:
    """Format a BRIDGE-MIB BridgeId (priority, MAC address) as ``8000.aabbccddeeff``."""
    raw = to_hex(value)
    if raw is None or len(raw) != 16:  # noqa: PLR2004 - eight octets
        return raw
    return f"{raw[:4]}.{raw[4:]}"


def lldp_id(subtype: int | None, value: Value | None, *, chassis: bool) -> str | None:
    """Format an LLDP chassis or port ID by its subtype."""
    if not isinstance(value, bytes) or isinstance(value, ObjectId):
        return None
    mac_subtype, network_subtype = (
        (_CHASSIS_MAC, _CHASSIS_NETWORK) if chassis else (_PORT_MAC, _PORT_NETWORK)
    )
    if subtype == mac_subtype:
        return to_mac(value) or value.hex()
    if subtype == network_subtype:
        return network_address(value) or value.hex()
    text = value.decode("utf-8", errors="replace")
    if text.isprintable():
        return text.rstrip("\x00 ") or None
    return value.hex()


def network_address(value: bytes) -> str | None:
    """Read an LLDP network address: one octet IANA address family, then the address."""
    family, address = (value[0], value[1:]) if value else (0, b"")
    return ip_from_octets(address) if family in (_IPV4_FAMILY, _IPV6_FAMILY) else None


def ip_from_octets(octets: bytes | Iterable[int]) -> str | None:
    """Four or sixteen octets as an IP address; other lengths are ``None``."""
    try:
        return str(ipaddress.ip_address(bytes(octets)))
    except ValueError:  # a part above 255, or a length other than 4 and 16
        return None


def capabilities(value: Value | None) -> frozenset[str]:
    """LLDP system capabilities (a BITS value) as names.

    BITS put capability 0 in the most significant bit of the first octet. Some switches (HPE
    1920S, PD.02.22) send the two octets swapped, so a two-octet value with an empty first octet
    is read the other way round. The capabilities after ``stationOnly`` (IEEE 802.1AB-2009) are
    not reported.
    """
    if not isinstance(value, bytes) or isinstance(value, ObjectId) or not value:
        return frozenset()
    octets = value[:2]
    if len(octets) == 2 and octets[0] == 0 and octets[1]:  # noqa: PLR2004
        octets = bytes((octets[1], 0))
    first = octets[0]
    return frozenset(name for bit, name in enumerate(LLDP_CAPABILITIES) if first & (0x80 >> bit))
