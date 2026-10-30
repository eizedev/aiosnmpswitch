"""Interpretation across tables and switches: trunks, LLDP ports, uplinks, device locations.

Everything here is derived from the models; nothing reads from a switch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .models import FdbEntry, FdbStatus, Interface, Lldp, LldpRemote, NeighborEntry

# IANAifType values of interfaces that are Ethernet ports.
ETHERNET_TYPES = frozenset({6, 62, 69, 117})
LAG_TYPE = 161
_LLDP_PORT_NAME_SUBTYPES = (1, 5, 7)  # interfaceAlias, interfaceName, local


@dataclass(frozen=True, slots=True)
class SwitchData:
    """The reads of one switch that the helpers combine."""

    interfaces: Mapping[int, Interface]
    bridge_ports: Mapping[int, int] = field(default_factory=dict)
    fdb: Iterable[FdbEntry] = ()
    lldp: Lldp | None = None
    lag_ports: Mapping[int, int] = field(default_factory=dict)
    neighbors: Iterable[NeighborEntry] = ()


@dataclass(frozen=True, slots=True)
class MacLocation:
    """Where a device was learned: the switch port it is connected to, directly or not."""

    address: str
    """MAC address as ``aa:bb:cc:dd:ee:ff``."""
    switch: str
    """Key of the switch in the mapping given to :func:`locate_macs`."""
    if_index: int
    port_name: str
    fdb_id: int | None
    devices_on_port: int
    """Number of devices located on the same port; more than one means a hub, an unmanaged
    switch, an access point or a router is between the port and this device."""
    ip_addresses: tuple[str, ...] = ()
    """Addresses from the switches' neighbour caches, if any switch knew one."""


def port_name(interface: Interface) -> str:
    """Return the name a person knows the port by: ``ifName``, ``ifDescr`` or the index."""
    return interface.name or interface.descr or str(interface.index)


def is_ethernet_port(interface: Interface) -> bool:
    """Whether the interface is a physical Ethernet port (not a VLAN, CPU or trunk)."""
    return interface.type in ETHERNET_TYPES


def lag_members(
    lag_ports: Mapping[int, int], interfaces: Mapping[int, Interface]
) -> dict[int, int]:
    """Return the aggregator ``ifIndex`` by member ``ifIndex``, for ports in a trunk.

    ``dot3adAggPortAttachedAggID`` is 0 for a port in no trunk; the HPE Instant On 1930 reports
    the port's own index instead. Aggregators the switch does not list as interfaces are ignored.
    """
    return {
        member: aggregator
        for member, aggregator in lag_ports.items()
        if aggregator not in (0, member) and aggregator in interfaces
    }


def lag_interfaces(data: SwitchData) -> set[int]:
    """Return the ``ifIndex`` of the trunks (link aggregations).

    A trunk is an interface with at least one member, or one typed ``ieee8023adLag``.
    """
    members = lag_members(data.lag_ports, data.interfaces)
    typed = {index for index, interface in data.interfaces.items() if interface.type == LAG_TYPE}
    return set(members.values()) | typed


def lldp_port_if_index(
    lldp: Lldp, port_num: int, interfaces: Mapping[int, Interface]
) -> int | None:
    """Return the ``ifIndex`` of LLDP's local port number ``port_num``.

    The port ID is matched by name when the switch sends one (``ifName``, then ``ifDescr``, then
    ``ifAlias``); otherwise the port number is taken as the ``ifIndex``, which is what switches
    with a MAC address as port ID do (HPE 1920S). On a switch whose LLDP port numbers are not its
    interface indexes and whose port IDs match no name, the mapping fails or hits the wrong port,
    and :func:`uplink_ports` cannot see its uplinks.
    """
    local = lldp.ports.get(port_num)
    if local and local.port_id and local.port_id_subtype in _LLDP_PORT_NAME_SUBTYPES:
        # The switch's own names first; an alias is set by people and may repeat another name.
        for field in ("name", "descr", "alias"):
            for interface in interfaces.values():
                if getattr(interface, field) == local.port_id:
                    return interface.index
    return port_num if port_num in interfaces else None


def neighbors_by_port(data: SwitchData) -> dict[int, list[LldpRemote]]:
    """Return LLDP neighbours by the ``ifIndex`` of the port they were seen on.

    Neighbours on a trunk member are reported on the trunk.
    """
    if data.lldp is None:
        return {}
    members = lag_members(data.lag_ports, data.interfaces)
    result: dict[int, list[LldpRemote]] = defaultdict(list)
    for remote in data.lldp.remotes:
        if_index = lldp_port_if_index(data.lldp, remote.local_port_num, data.interfaces)
        if if_index is not None:
            result[members.get(if_index, if_index)].append(remote)
    return dict(result)


def switch_addresses(data: SwitchData) -> set[str]:
    """MAC addresses that belong to the switch itself (chassis and interfaces)."""
    own = {i.phys_address for i in data.interfaces.values() if i.phys_address}
    if data.lldp and data.lldp.chassis_id:
        own.add(data.lldp.chassis_id)
    return own


def uplink_ports(switches: Mapping[str, SwitchData]) -> dict[str, set[int]]:
    """Ports (``ifIndex``, trunks for their members) that lead to another of ``switches``.

    A port is an uplink when LLDP sees one of the other switches on it. Switches that are not in
    ``switches`` count as devices, so what is behind them is located on the port they hang on.
    """
    owners = {address: key for key, data in switches.items() for address in switch_addresses(data)}
    result: dict[str, set[int]] = {}
    for key, data in switches.items():
        result[key] = {
            if_index
            for if_index, remotes in neighbors_by_port(data).items()
            if any(owners.get(remote.chassis_id or "", key) != key for remote in remotes)
        }
    return result


def locate_macs(switches: Mapping[str, SwitchData]) -> dict[str, MacLocation]:
    """Return the switch port of every device the switches learned, by MAC address.

    A device appears in the address table of every switch between it and the switch that sees
    it last; only the port that is not an uplink to another of ``switches`` is where it is
    connected. A device that is only seen on uplinks (its entry aged out on the edge switch) is
    left out rather than placed wrongly, and so are the switches' own addresses.
    """
    uplinks = uplink_ports(switches)
    own = set().union(*(switch_addresses(data) for data in switches.values()))
    candidates: dict[str, list[tuple[str, int, int | None]]] = defaultdict(list)
    for key, data in switches.items():
        members = lag_members(data.lag_ports, data.interfaces)
        for entry in data.fdb:
            if entry.status not in (FdbStatus.LEARNED, None) or not entry.port:
                continue
            if_index = data.bridge_ports.get(entry.port, entry.port)
            if_index = members.get(if_index, if_index)
            if if_index in uplinks[key] or if_index not in data.interfaces:
                continue
            if entry.address not in own:
                candidates[entry.address].append((key, if_index, entry.fdb_id))
    per_port: dict[tuple[str, int], set[str]] = defaultdict(set)
    for address, places in candidates.items():
        for key, if_index, _ in places:
            per_port[key, if_index].add(address)
    ips: dict[str, set[str]] = defaultdict(set)
    for data in switches.values():
        for neighbor in data.neighbors:
            ips[neighbor.phys_address].add(neighbor.address)
    result = {}
    for address, places in sorted(candidates.items()):
        key, if_index, fdb_id = min(places, key=lambda p: (len(per_port[p[0], p[1]]), p[0], p[1]))
        result[address] = MacLocation(
            address=address,
            switch=key,
            if_index=if_index,
            port_name=port_name(switches[key].interfaces[if_index]),
            fdb_id=fdb_id,
            devices_on_port=len(per_port[key, if_index]),
            ip_addresses=tuple(sorted(ips.get(address, ()))),
        )
    return result
