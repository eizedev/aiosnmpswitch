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
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

FORMAT = 1
MAC_LENGTH = 6
BRIDGE_ID_LENGTH = 8
MIN_TEXT = 3  # shorter originals ("1", "LG") occur in any text by chance
MAX_NUMERIC_PORT_ID = 4  # longer all-digit port IDs may be serial numbers
FAKE_IPV4_NETWORKS = ("192.0.2", "198.51.100", "203.0.113")  # RFC 5737
ADDRESS_LIKE = re.compile(
    # an IPv4 address on its own, not a version glued to a name ("InstantOn_1930_3.4.0.0")
    r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])",
    re.I,
)

# Columns (OID prefixes) whose octet strings are kept: models, firmware, port names, MIB texts,
# capability bits. Kept text is checked once more for anything that looks like an address
# (check_kept), and every distinct kept text is listed for a look before committing.
SYS_DESCR = "1.3.6.1.2.1.1.1"
KEEP = (
    SYS_DESCR,  # sysDescr: model and firmware; some agents add a host name, see the kept list
    "1.3.6.1.2.1.1.9.1.3",  # sysORDescr
    "1.3.6.1.2.1.47.1.1.1.1.2",  # entPhysicalDescr
    "1.3.6.1.2.1.47.1.1.1.1.13",  # entPhysicalModelName
    "1.3.6.1.4.1.11.2.83.3.1.4",  # HPE Instant On 1930: sensor names
    "1.3.6.1.2.1.2.2.1.2",  # ifDescr
    "1.3.6.1.2.1.31.1.1.1.1",  # ifName
    "1.0.8802.1.1.2.1.3.4",  # lldpLocSysDesc
    "1.0.8802.1.1.2.1.3.5",  # lldpLocSysCapSupported
    "1.0.8802.1.1.2.1.3.6",  # lldpLocSysCapEnabled
    "1.0.8802.1.1.2.1.4.1.1.11",  # lldpRemSysCapSupported
    "1.0.8802.1.1.2.1.4.1.1.12",  # lldpRemSysCapEnabled
    "1.3.6.1.2.1.17.2.15.1.9",  # dot1dStpPortDesignatedPort (priority and port number)
)
# Firmware versions, kept without the address check: four numbers with dots look like IPv4.
VERSIONS = (
    "1.3.6.1.2.1.105.1.3.1.1.6",  # vendor PSE firmware text (HPE 1920S)
    "1.3.6.1.2.1.47.1.1.1.1.10",  # entPhysicalSoftwareRev
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
# lldpRemSysDesc is what a neighbour says about itself; it is kept only where it equals a
# description of one of the recorded switches (sysDescr), else replaced.
REMOTE_DESCRIPTIONS = ("1.0.8802.1.1.2.1.4.1.1.10",)
DESCRIPTIONS = (
    "1.3.6.1.2.1.105.1.1.1.9",  # pethPsePortType: written by administrators
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
        self.kept: set[str] = set()
        self.system_descriptions: set[bytes] = set()

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
                count = sum(1 for original in self.ips if len(original) == 4) + 1  # noqa: PLR2004
                network, host = divmod(count - 1, 254)
                if network >= len(FAKE_IPV4_NETWORKS):
                    raise SystemExit("more IPv4 addresses than the documentation networks hold")
                fake = ipaddress.IPv4Address(f"{FAKE_IPV4_NETWORKS[network]}.{host + 1}")
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
            (KEEP, lambda: self.keep(oid, raw)),
            (VERSIONS, lambda: raw),
            (REMOTE_DESCRIPTIONS, lambda: self.remote_description(raw)),
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

    def keep(self, oid: str, raw: bytes) -> bytes:
        """Keep a value of a KEEP column, unless it looks like it holds an address."""
        text = raw.decode("utf-8", errors="replace")
        if ADDRESS_LIKE.search(text):
            raise SystemExit(f"a kept value in {oid} looks like an address: classify the column")
        if text.isprintable() and text.strip():
            self.kept.add(text)
        return raw

    def remote_description(self, raw: bytes) -> bytes:
        """A neighbour's description: kept if it is one of the recorded switches', else replaced."""
        if raw in self.system_descriptions:
            return raw
        text = raw.decode("utf-8", errors="replace")
        return self.text("device description", text, "device description {}").encode()

    def port_text(self, raw: bytes) -> bytes:
        """A port ID that is not a MAC address: kept if it is a short number, else replaced."""
        text = raw.decode("utf-8", errors="replace")
        if text.isdigit() and len(text) <= MAX_NUMERIC_PORT_ID:
            return raw
        return self.text("port", text, "port {}").encode()

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
    recordings = [
        (json.loads(Path(raw).read_text(encoding="utf-8")), Path(out))
        for raw, out in zip(argv[::2], argv[1::2], strict=True)
    ]
    for data, _ in recordings:  # the switches' own descriptions, as their neighbours see them
        value = data.get("values", {}).get(f"{SYS_DESCR}.0")
        if isinstance(value, dict) and "hex" in value:
            anonymizer.system_descriptions.add(bytes.fromhex(value["hex"]))
    outputs = [(out, anonymize(anonymizer, data)) for data, out in recordings]
    for path, data in outputs:
        text = json.dumps(data, indent=1, sort_keys=True) + "\n"
        if found := leftovers(anonymizer, text):
            raise SystemExit(f"{path}: original values left: {len(found)}; nothing written")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"written {path}")
    print("Kept as they are; check that none of them names a person, place or device:")
    for text in sorted(anonymizer.kept):
        print(f"  {text[:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
