"""Anonymize switch recordings (``aiosnmpswitch-diagnostics --record``) into test fixtures.

    python scripts/anonymize.py RAW OUT [RAW OUT ...]

All recordings of one network go into one run, so the same device gets the same fake address in
every file and the switches still recognise each other through LLDP.

MAC addresses become ``02:00:00:00:xx:xx`` (locally administered), IPv4 addresses
``192.0.2.x`` (TEST-NET-1), IPv6 addresses ``2001:db8::x`` or ``fe80::x``, switch names
``switch-N``, port descriptions ``port description N``. The script is an allowlist: an octet
string in a column it does not know stops it, so a new column is classified before anything is
written. Check the output by eye as well.
"""

from __future__ import annotations

import ipaddress
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

FORMAT = 1
MAC_LENGTH = 6
BRIDGE_ID_LENGTH = 8
MIN_TEXT = 3  # shorter originals ("1", "LG") occur in any text by chance

# Columns (OID prefixes) whose octet strings are kept: models, firmware, port names, MIB texts,
# capability bits, PoE port types.
KEEP = (
    "1.3.6.1.2.1.1.1",  # sysDescr
    "1.3.6.1.2.1.1.9.1.3",  # sysORDescr
    "1.3.6.1.2.1.2.2.1.2",  # ifDescr
    "1.3.6.1.2.1.31.1.1.1.1",  # ifName
    "1.0.8802.1.1.2.1.3.4",  # lldpLocSysDesc
    "1.0.8802.1.1.2.1.3.5",  # lldpLocSysCapSupported
    "1.0.8802.1.1.2.1.3.6",  # lldpLocSysCapEnabled
    "1.0.8802.1.1.2.1.4.1.1.10",  # lldpRemSysDesc
    "1.0.8802.1.1.2.1.4.1.1.11",  # lldpRemSysCapSupported
    "1.0.8802.1.1.2.1.4.1.1.12",  # lldpRemSysCapEnabled
    "1.3.6.1.2.1.17.2.15.1.9",  # dot1dStpPortDesignatedPort (priority and port number)
    "1.3.6.1.2.1.105.1.1.1.9",  # pethPsePortType
    "1.3.6.1.2.1.105.1.3.1.1.6",  # vendor PSE firmware text (HPE 1920S)
)
# Columns holding a MAC address, or a text port ID when it is not six octets.
MACS = (
    "1.3.6.1.2.1.2.2.1.6",  # ifPhysAddress
    "1.3.6.1.2.1.17.4.3.1.1",  # dot1dTpFdbAddress
    "1.3.6.1.2.1.4.22.1.2",  # ipNetToMediaPhysAddress
    "1.3.6.1.2.1.4.35.1.4",  # ipNetToPhysicalPhysAddress
    "1.0.8802.1.1.2.1.3.2",  # lldpLocChassisId
    "1.0.8802.1.1.2.1.3.7.1.3",  # lldpLocPortId
    "1.0.8802.1.1.2.1.4.1.1.5",  # lldpRemChassisId
    "1.0.8802.1.1.2.1.4.1.1.7",  # lldpRemPortId
)
BRIDGE_IDS = (
    "1.3.6.1.2.1.17.2.5",  # dot1dStpDesignatedRoot
    "1.3.6.1.2.1.17.2.15.1.6",  # dot1dStpPortDesignatedRoot
    "1.3.6.1.2.1.17.2.15.1.8",  # dot1dStpPortDesignatedBridge
)
NAMES = ("1.3.6.1.2.1.1.5", "1.0.8802.1.1.2.1.3.3", "1.0.8802.1.1.2.1.4.1.1.9")
DESCRIPTIONS = (
    "1.3.6.1.2.1.31.1.1.1.18",  # ifAlias
    "1.0.8802.1.1.2.1.3.7.1.4",  # lldpLocPortDesc
    "1.0.8802.1.1.2.1.4.1.1.8",  # lldpRemPortDesc
)
CONTACT, LOCATION = "1.3.6.1.2.1.1.4", "1.3.6.1.2.1.1.6"
# OID values that may encode anything (lldpRemManAddrOID, lldpLocManAddrOID): replaced.
OPAQUE_OIDS = ("1.0.8802.1.1.2.1.4.2.1.5", "1.0.8802.1.1.2.1.3.8.1.6")

# Tables whose index holds an address: (column prefix, parts before the address, kind).
# kind "mac": six parts; "ip4": four parts; "inet": type, length, address (InetAddress);
# "lldp": subtype, length, address (LLDP management address).
INDEX_ADDRESSES = (
    ("1.3.6.1.2.1.17.7.1.2.2.1", 2, "mac"),  # dot1qTpFdbTable: column, fdb id
    ("1.3.6.1.2.1.17.4.3.1", 1, "mac"),  # dot1dTpFdbTable: column
    ("1.3.6.1.2.1.4.22.1", 2, "ip4"),  # ipNetToMediaTable: column, ifIndex
    ("1.3.6.1.2.1.4.35.1", 2, "inet"),  # ipNetToPhysicalTable: column, ifIndex
    ("1.0.8802.1.1.2.1.4.2.1", 4, "lldp"),  # lldpRemManAddrTable: column, time, port, index
    ("1.0.8802.1.1.2.1.3.8.1", 1, "lldp"),  # lldpLocManAddrTable: column
)


class Anonymizer:
    """Consistent replacements across all files of one run."""

    def __init__(self) -> None:
        """Start with empty mappings."""
        self.macs: dict[bytes, bytes] = {}
        self.ips: dict[bytes, bytes] = {}
        self.texts: dict[tuple[str, str], str] = {}

    def mac(self, value: bytes) -> bytes:
        """A fake, locally administered MAC address for ``value``."""
        if value not in self.macs:
            n = len(self.macs) + 1
            self.macs[value] = bytes((2, 0, 0, 0, n >> 8, n & 0xFF))
        return self.macs[value]

    def ip(self, value: bytes) -> bytes:
        """A documentation address for an IPv4 or IPv6 address (link-local stays link-local)."""
        if value not in self.ips:
            n = len(self.ips) + 1
            if len(value) == 4:  # noqa: PLR2004
                fake = ipaddress.IPv4Address(f"192.0.2.{n}")
            elif value[:2] == b"\xfe\x80":
                fake = ipaddress.IPv6Address(f"fe80::{n:x}")  # type: ignore[assignment]
            else:
                fake = ipaddress.IPv6Address(f"2001:db8::{n:x}")  # type: ignore[assignment]
            self.ips[value] = fake.packed
        return self.ips[value]

    def text(self, kind: str, value: str, template: str) -> str:
        """The same replacement text for the same original text of one kind."""
        if not value:
            return ""
        if (kind, value) not in self.texts:
            n = sum(1 for k, _ in self.texts if k == kind) + 1
            self.texts[kind, value] = template.format(n)
        return self.texts[kind, value]

    def octets(self, oid: str, raw: bytes) -> bytes:
        """Replace or keep an octet string by its column."""
        text = raw.decode("utf-8", errors="replace")
        rules: list[tuple[tuple[str, ...], Callable[[], bytes]]] = [
            (KEEP, lambda: raw),
            (MACS, lambda: self.mac(raw) if len(raw) == MAC_LENGTH else self.port_text(raw)),
            (BRIDGE_IDS, lambda: self.bridge_id(raw)),
            (NAMES, lambda: self.text("name", text, "switch-{}").encode()),
            (DESCRIPTIONS, lambda: self.text("description", text, "port description {}").encode()),
            ((CONTACT,), lambda: self.text("contact", text, "network admin").encode()),
            ((LOCATION,), lambda: self.text("location", text, "location {}").encode()),
        ]
        for prefixes, replace in rules:
            if _in(oid, prefixes):
                return replace()
        raise SystemExit(f"unclassified octet string in {oid}: add its column to a list first")

    def port_text(self, raw: bytes) -> bytes:
        """A port ID that is not a MAC address: kept if it is only a number, else replaced."""
        text = raw.decode("utf-8", errors="replace")
        return raw if text.isdigit() else self.text("port", text, "port {}").encode()

    def bridge_id(self, raw: bytes) -> bytes:
        """Priority kept, MAC address replaced."""
        if len(raw) != BRIDGE_ID_LENGTH:
            raise SystemExit(f"bridge ID of unexpected length {len(raw)}")
        return raw[:2] + self.mac(raw[2:])

    def index(self, oid: str) -> str:
        """Replace an address inside a table index."""
        for prefix, before, kind in INDEX_ADDRESSES:
            if not oid.startswith(prefix + "."):
                continue
            parts = [int(p) for p in oid[len(prefix) + 1 :].split(".")]
            head, rest = parts[:before], parts[before:]
            return ".".join([prefix, *map(str, head + self.address_parts(kind, rest))])
        return oid

    def address_parts(self, kind: str, parts: list[int]) -> list[int]:
        """The index parts of an address, replaced."""
        if kind == "mac":
            return list(self.mac(bytes(parts)))
        if kind == "ip4":
            return list(self.ip(bytes(parts)))
        kind_part, length, address = parts[0], parts[1], parts[2:]
        if kind == "inet" and kind_part in (3, 4):  # zoned: address, then a 4-octet zone index
            size = length - 4
            return [kind_part, length, *self.ip(bytes(address[:size])), *address[size:]]
        if len(address) in (4, 16):
            return [kind_part, length, *self.ip(bytes(address))]
        raise SystemExit(f"address of unexpected length {len(address)} in an index")

    def value(self, oid: str, value: Any) -> Any:
        """A recorded value, replaced where needed."""
        if isinstance(value, dict) and "hex" in value:
            return {"hex": self.octets(oid, bytes.fromhex(value["hex"])).hex()}
        if isinstance(value, dict) and _in(oid, OPAQUE_OIDS):
            return {"oid": "0.0"}
        return value


def _in(oid: str, prefixes: tuple[str, ...]) -> bool:
    return any(oid == p or oid.startswith(p + ".") for p in prefixes)


def anonymize(anonymizer: Anonymizer, data: dict[str, Any]) -> dict[str, Any]:
    """An anonymized copy of one recording."""
    if data.get("format") != FORMAT:
        raise SystemExit(f"unknown recording format {data.get('format')!r}")
    values = {
        anonymizer.index(oid): anonymizer.value(oid, value) for oid, value in data["values"].items()
    }
    return {"format": FORMAT, "values": values}


def leftovers(anonymizer: Anonymizer, text: str) -> list[str]:
    """Original addresses and texts still in ``text`` (as hex, index parts or text)."""
    found = []
    for original in [*anonymizer.macs, *anonymizer.ips]:
        dotted = ".".join(str(b) for b in original)
        if original.hex() in text or f'.{dotted}"' in text or f".{dotted}." in text:
            found.append(original.hex())
    found += [
        value
        for (_, value), _ in anonymizer.texts.items()
        if len(value) > MIN_TEXT and value in text
    ]
    return found


def main(argv: list[str]) -> int:
    """Anonymize pairs of RAW OUT files."""
    if not argv or len(argv) % 2:
        print(__doc__)
        return 2
    anonymizer = Anonymizer()
    outputs = []
    for raw, out in zip(argv[::2], argv[1::2], strict=True):
        data = json.loads(Path(raw).read_text(encoding="utf-8"))
        outputs.append((Path(out), anonymize(anonymizer, data)))
    for path, data in outputs:
        text = json.dumps(data, indent=1, sort_keys=True) + "\n"
        if found := leftovers(anonymizer, text):
            raise SystemExit(f"{path}: original values left: {len(found)}; nothing written")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
