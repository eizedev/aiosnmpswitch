"""Device locations across the three recorded switches, and the helpers they use."""

from __future__ import annotations

from collections import Counter

from aiosnmpswitch import FdbEntry, FdbStatus, Interface, Lldp, LldpLocalPort, LldpRemote
from aiosnmpswitch.helpers import (
    SwitchData,
    is_ethernet_port,
    lag_interfaces,
    lag_members,
    lldp_port_if_index,
    locate_macs,
    neighbors_by_port,
    port_name,
    switch_addresses,
    uplink_ports,
)

from .conftest import RECORDINGS, recorded


async def network() -> dict[str, SwitchData]:
    result = {}
    for name in sorted(RECORDINGS):
        switch = recorded(name)
        result[name] = SwitchData(
            interfaces=await switch.get_interfaces(),
            bridge_ports=await switch.get_bridge_ports(),
            fdb=await switch.get_fdb(),
            lldp=await switch.get_lldp(),
            lag_ports=await switch.get_lag_ports(),
            neighbors=await switch.get_neighbors(),
        )
    return result


async def test_uplinks_are_the_links_between_the_switches() -> None:
    assert uplink_ports(await network()) == {
        "switch-1": {5, 7},
        "switch-2": {7},
        "switch-3": {1},
    }


async def test_a_switch_alone_has_no_uplinks() -> None:
    data = await network()
    assert uplink_ports({"switch-1": data["switch-1"]}) == {"switch-1": set()}


async def test_locate_macs() -> None:
    locations = await network()
    found = locate_macs(locations)
    per_port = Counter((loc.switch, loc.port_name) for loc in found.values())
    assert per_port == {
        ("switch-1", "1"): 14,  # the router: itself and everything behind it
        ("switch-1", "TRK 1"): 2,  # trunk members are located on their trunk
        ("switch-1", "TRK 2"): 3,
        ("switch-2", "4"): 9,  # an access point with its Wi-Fi clients
        ("switch-2", "6"): 1,
        ("switch-2", "8"): 1,
        ("switch-3", "2"): 1,
        ("switch-3", "3"): 1,
        ("switch-3", "4"): 1,
        ("switch-3", "7"): 1,
        ("switch-3", "8"): 1,
    }
    own = set().union(*(switch_addresses(d) for d in locations.values()))
    assert not own & found.keys()
    single = [loc for loc in found.values() if loc.switch == "switch-3" and loc.port_name == "2"]
    assert single[0].devices_on_port == 1
    assert single[0].if_index == 2
    assert single[0].fdb_id == 1
    with_ip = [loc for loc in found.values() if loc.ip_addresses]
    assert with_ip  # the 1930 knows some addresses from its neighbour cache


def _interfaces(*indexes: int, type_: int = 6) -> dict[int, Interface]:
    return {i: Interface(index=i, name=str(i), type=type_) for i in indexes}


def test_a_device_only_seen_on_uplinks_is_left_out() -> None:
    lldp_a = Lldp(
        4, "02:00:00:00:00:0a", "a", {}, [LldpRemote(0, 1, 1, chassis_id="02:00:00:00:00:0b")]
    )
    lldp_b = Lldp(
        4, "02:00:00:00:00:0b", "b", {}, [LldpRemote(0, 1, 1, chassis_id="02:00:00:00:00:0a")]
    )
    seen_on_uplink = FdbEntry(1, "02:00:00:00:00:01", 1, FdbStatus.LEARNED)
    data = {
        "a": SwitchData(interfaces=_interfaces(1), fdb=[seen_on_uplink], lldp=lldp_a),
        "b": SwitchData(interfaces=_interfaces(1), lldp=lldp_b),
    }
    assert locate_macs(data) == {}


def test_entries_without_port_or_unknown_status_or_interface() -> None:
    entries = [
        FdbEntry(None, "02:00:00:00:00:01", 0, FdbStatus.LEARNED),  # no port
        FdbEntry(None, "02:00:00:00:00:02", 1, FdbStatus.SELF),  # the switch itself
        FdbEntry(None, "02:00:00:00:00:03", 9, None),  # no such interface
        FdbEntry(None, "02:00:00:00:00:04", 1, None),  # no status: counted as learned
        FdbEntry(None, "02:00:00:00:00:05", 1, FdbStatus.LEARNED),  # the switch's own port MAC
    ]
    interfaces = {1: Interface(index=1, name="1", type=6, phys_address="02:00:00:00:00:05")}
    found = locate_macs({"a": SwitchData(interfaces=interfaces, fdb=entries)})
    assert list(found) == ["02:00:00:00:00:04"]


def test_lldp_port_name_wins_over_an_alias() -> None:
    interfaces = {1: Interface(index=1, alias="gi2"), 2: Interface(index=2, name="gi2")}
    lldp = Lldp(None, None, None, {9: LldpLocalPort(9, 5, "gi2")}, [])
    assert lldp_port_if_index(lldp, 9, interfaces) == 2


def test_lldp_port_mapping() -> None:
    interfaces = {
        1: Interface(index=1, name="gi1"),
        2: Interface(index=2, descr="Port 2"),
        3: Interface(index=3, alias="uplink"),
    }
    ports = {
        10: LldpLocalPort(10, 5, "gi1"),  # interface name
        11: LldpLocalPort(11, 7, "Port 2"),  # local, matches the description
        12: LldpLocalPort(12, 1, "uplink"),  # interface alias
        2: LldpLocalPort(2, 3, "02:00:00:00:00:01"),  # MAC address: the number is the index
        13: LldpLocalPort(13, 5, "missing"),
    }
    lldp = Lldp(None, None, None, ports, [])
    assert [lldp_port_if_index(lldp, n, interfaces) for n in (10, 11, 12, 2, 13, 3)] == [
        1,
        2,
        3,
        2,
        None,
        3,
    ]


def test_neighbors_by_port() -> None:
    remote = LldpRemote(0, 2, 1, sys_name="peer")
    unmapped = LldpRemote(0, 9, 2, sys_name="nowhere")
    lldp = Lldp(None, None, None, {}, [remote, unmapped])
    data = SwitchData(interfaces=_interfaces(1, 2, 50), lldp=lldp, lag_ports={2: 50})
    assert neighbors_by_port(data) == {50: [remote]}
    assert neighbors_by_port(SwitchData(interfaces={})) == {}


def test_lag_helpers() -> None:
    interfaces = {**_interfaces(1, 2, 3), 100: Interface(index=100, type=161)}
    lag_ports = {1: 0, 2: 100, 3: 3, 4: 99}  # none, member, itself, unknown aggregator
    assert lag_members(lag_ports, interfaces) == {2: 100}
    assert lag_interfaces(SwitchData(interfaces=interfaces, lag_ports=lag_ports)) == {100}


def test_port_names_and_types() -> None:
    assert port_name(Interface(index=3, name="gi3", descr="d")) == "gi3"
    assert port_name(Interface(index=3, descr="Port 3")) == "Port 3"
    assert port_name(Interface(index=3)) == "3"
    assert is_ethernet_port(Interface(index=1, type=6))
    assert not is_ethernet_port(Interface(index=1, type=161))
