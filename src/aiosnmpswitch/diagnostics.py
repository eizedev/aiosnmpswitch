"""Describe what a switch answers, without any of its values, or record it for test fixtures.

    aiosnmpswitch-diagnostics <switch address>                       # SNMPv2c, community asked
    aiosnmpswitch-diagnostics <switch address> --user <SNMPv3 user>  # keys asked
    aiosnmpswitch-diagnostics <switch address> --record switch.raw.json

The summary names the model and firmware and counts what each MIB returns; it holds no MAC or IP
addresses, names or descriptions and can be pasted into an issue. A recording holds every value
and must be anonymized with ``scripts/anonymize.py`` before it is shared.

Secrets are never taken from the command line (other users can see it): they come from the
environment (``SNMP_COMMUNITY``, ``SNMP_AUTH_KEY``, ``SNMP_PRIV_KEY``) or are asked for.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .auth import Auth, AuthProtocol, CommunityAuth, PrivProtocol, UsmAuth
from .client import SnmpSwitch
from .errors import SnmpError
from .helpers import SwitchData, lag_members, neighbors_by_port
from .transport import ObjectId, PysnmpTransport, Transport, Value

RECORDING_FORMAT = 1

# Everything the client reads, walked whole so a recording answers every getter.
RECORDED_SUBTREES = (
    "1.3.6.1.2.1.1",  # system
    "1.3.6.1.2.1.2.2.1",  # ifTable
    "1.3.6.1.2.1.31.1.1.1",  # ifXTable
    "1.3.6.1.2.1.17.1.4.1.2",  # dot1dBasePortIfIndex
    "1.3.6.1.2.1.17.2",  # dot1dStp
    "1.3.6.1.2.1.17.4.3.1",  # dot1dTpFdbTable
    "1.3.6.1.2.1.17.7.1.2.2.1",  # dot1qTpFdbTable
    "1.0.8802.1.1.2.1.3",  # lldpLocalSystemData
    "1.0.8802.1.1.2.1.4",  # lldpRemoteSystemsData
    "1.2.840.10006.300.43.1.2.1.1.13",  # dot3adAggPortAttachedAggID
    "1.3.6.1.2.1.105.1",  # pethObjects
    "1.3.6.1.2.1.4.35.1.4",  # ipNetToPhysicalPhysAddress
    "1.3.6.1.2.1.4.22.1.2",  # ipNetToMediaPhysAddress
)


def encode(value: Value) -> Any:
    """Encode a value as JSON: numbers as they are, octets and OIDs as objects."""
    if isinstance(value, ObjectId):
        return {"oid": str(value)}
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    return value


def decode(value: Any) -> Value:
    """Decode a value written by :func:`encode`."""
    if isinstance(value, dict):
        if "oid" in value:
            return ObjectId(value["oid"])
        return bytes.fromhex(value["hex"])
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"not a recorded value: {value!r}")
    return value


def load_recording(path: Path) -> dict[str, Value]:
    """Values of a recording file, for :class:`~aiosnmpswitch.transport.RecordedTransport`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != RECORDING_FORMAT:
        raise ValueError(f"{path}: unknown recording format {data.get('format')!r}")
    return {oid: decode(value) for oid, value in data["values"].items()}


async def record(transport: Transport) -> dict[str, Value]:
    """Walk every subtree the client reads."""
    values: dict[str, Value] = {}
    for subtree in RECORDED_SUBTREES:
        values.update(await transport.walk(subtree))
    return values


async def summary(switch: SnmpSwitch) -> list[str]:
    """Lines describing what the switch answers; counts and structure only, no values."""
    system = await switch.get_system()
    interfaces = await switch.get_interfaces()
    data = SwitchData(
        interfaces=interfaces,
        bridge_ports=await switch.get_bridge_ports(),
        fdb=await switch.get_fdb(),
        lldp=await switch.get_lldp(),
        lag_ports=await switch.get_lag_ports(),
        neighbors=await switch.get_neighbors(),
    )
    stp = await switch.get_stp()
    poe = await switch.get_poe()
    types: dict[int | None, int] = {}
    for interface in interfaces.values():
        types[interface.type] = types.get(interface.type, 0) + 1
    fdb = list(data.fdb)
    lldp = data.lldp
    assert lldp is not None  # noqa: S101 - set above
    with_hc = sum(1 for i in interfaces.values() if i.hc_in_octets is not None)
    port_states = len(stp.port_states) if stp else 0
    return [
        f"model: {system.descr}",
        f"sysObjectID: {system.object_id}",
        f"interfaces: {len(interfaces)} by ifType {dict(sorted(types.items(), key=str))}",
        f"interfaces with ifName: {sum(1 for i in interfaces.values() if i.name)}, "
        f"with ifHighSpeed: {sum(1 for i in interfaces.values() if i.high_speed is not None)}, "
        f"with 64-bit counters: {with_hc}",
        f"bridge ports: {len(data.bridge_ports)}",
        f"address table: {len(fdb)} entries, "
        f"{'with' if any(e.fdb_id is not None for e in fdb) else 'without'} VLAN (Q-BRIDGE-MIB)",
        f"spanning tree: {'yes' if stp else 'no'}, port states: {port_states}",
        f"LLDP: chassis ID subtype {lldp.chassis_id_subtype}, local ports {len(lldp.ports)}, "
        f"port ID subtypes {sorted({p.port_id_subtype or 0 for p in lldp.ports.values()})}, "
        f"neighbours {len(lldp.remotes)} on {len(neighbors_by_port(data))} mapped ports",
        f"trunks: {len(set(lag_members(data.lag_ports, interfaces).values()))} with members, "
        f"LAG-MIB rows {len(data.lag_ports)}",
        f"PoE: {len(poe.supplies)} supplies, {len(poe.ports)} ports",
        f"neighbour cache: {len(list(data.neighbors))} entries",
    ]


def _auth(args: argparse.Namespace, environ: Mapping[str, str]) -> Auth:
    """Credentials from the arguments, the environment or a prompt."""
    if args.user is None:
        community = environ.get("SNMP_COMMUNITY") or getpass.getpass("Community: ")
        return CommunityAuth(community, version=args.version)
    auth_key = environ.get("SNMP_AUTH_KEY")
    priv_key = environ.get("SNMP_PRIV_KEY")
    if args.auth_protocol != AuthProtocol.NONE and auth_key is None:
        auth_key = getpass.getpass("Authentication key: ")
    if args.priv_protocol != PrivProtocol.NONE and priv_key is None:
        priv_key = getpass.getpass("Privacy key: ")
    return UsmAuth(
        args.user,
        auth_key or None,
        priv_key or None,
        auth_protocol=AuthProtocol(args.auth_protocol),
        priv_protocol=PrivProtocol(args.priv_protocol),
    )


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Command line options."""
    parser = argparse.ArgumentParser(
        prog="aiosnmpswitch-diagnostics", description=__doc__.split("\n")[0] if __doc__ else None
    )
    parser.add_argument("host", help="address of the switch")
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--version", choices=("1", "2c"), default="2c", help="without --user")
    parser.add_argument("--user", help="SNMPv3 user (keys from SNMP_AUTH_KEY/SNMP_PRIV_KEY)")
    parser.add_argument(
        "--auth-protocol", choices=[p.value for p in AuthProtocol], default=AuthProtocol.SHA
    )
    parser.add_argument(
        "--priv-protocol", choices=[p.value for p in PrivProtocol], default=PrivProtocol.AES128
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--record", type=Path, metavar="FILE", help="write every value to FILE (*.raw.json)"
    )
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """Read the switch and print the summary or write the recording."""
    transport = await PysnmpTransport.create(
        args.host, _auth(args, environ), port=args.port, timeout=args.timeout
    )
    try:
        if args.record:
            values = await record(transport)
            payload = {
                "format": RECORDING_FORMAT,
                "values": {oid: encode(value) for oid, value in values.items()},
            }
            args.record.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"{len(values)} values written to {args.record}; anonymize before sharing")
        else:
            print("\n".join(await summary(SnmpSwitch(transport))))
    except SnmpError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        await transport.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``aiosnmpswitch-diagnostics``."""
    return asyncio.run(run(parse_args(argv), os.environ))
