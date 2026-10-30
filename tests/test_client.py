"""The getters against recordings of an HPE OfficeConnect 1920S and an HPE Instant On 1930."""

from __future__ import annotations

from aiosnmpswitch import (
    FdbStatus,
    ObjectId,
    OperStatus,
    PseDetectionStatus,
    PseOperStatus,
    RecordedTransport,
    SnmpSwitch,
    StpPortState,
)
from aiosnmpswitch.helpers import lag_members

from .conftest import recorded


async def test_system() -> None:
    system = await recorded("switch-1").get_system()
    assert system.descr is not None
    assert system.descr.startswith("HPE OfficeConnect Switch 1920S")
    assert system.object_id == "1.3.6.1.4.1.11.2.3.7.11.186"
    assert system.up_time == 103711200
    assert (system.name, system.location, system.contact) == (
        "switch-1",
        "location 1",
        "network admin",
    )
    assert (await recorded("switch-3").get_system()).contact is None  # empty sysContact


async def test_interfaces_1920s() -> None:
    interfaces = await recorded("switch-1").get_interfaces()
    assert sorted(interfaces) == [1, 2, 3, 4, 5, 6, 7, 8, 53, 54, 55, 56, 57]
    port = interfaces[1]
    assert (port.name, port.type, port.oper_status, port.high_speed) == (
        "1",
        6,
        OperStatus.UP,
        1000,
    )
    assert port.alias == "port description 1"
    assert port.phys_address == "02:00:00:00:00:01"
    assert port.hc_in_octets is not None
    assert port.descr == "1 Gigabit - Level"
    assert interfaces[4].oper_status is OperStatus.DOWN
    assert interfaces[4].high_speed == 0
    assert interfaces[54].name == "TRK 1"
    assert interfaces[54].type == 1  # the 1920S types its trunks as "other"


async def test_interfaces_1930() -> None:
    interfaces = await recorded("switch-3").get_interfaces()
    assert len(interfaces) == 34
    assert interfaces[1000].name == "TRK1"
    assert interfaces[1000].type == 161
    assert interfaces[2].high_speed == 100
    assert interfaces[5].oper_status is OperStatus.DOWN
    assert interfaces[5].high_speed == 1000  # the 1930 reports the speed of a port without link


async def test_bridge_ports(any_switch: SnmpSwitch) -> None:
    ports = await any_switch.get_bridge_ports()
    assert all(port == if_index for port, if_index in ports.items())


async def test_fdb() -> None:
    entries = await recorded("switch-3").get_fdb()
    assert len(entries) == 36
    assert entries[0].fdb_id == 1
    assert entries[0].status is FdbStatus.LEARNED
    assert all(len(e.address) == 17 for e in entries)
    own = [e for e in await recorded("switch-1").get_fdb() if e.status is FdbStatus.MGMT]
    assert own
    assert own[0].port == 53  # the 1920S lists its own address on the CPU interface


async def test_fdb_falls_back_to_bridge_mib() -> None:
    values = {
        "1.3.6.1.2.1.17.4.3.1.2.2.0.0.0.0.1": 3,
        "1.3.6.1.2.1.17.4.3.1.3.2.0.0.0.0.1": 3,
        "1.3.6.1.2.1.17.4.3.1.2.2.0.0.0.1": 3,  # five octets: not an address, skipped
    }
    entries = await SnmpSwitch(RecordedTransport(values)).get_fdb()
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.fdb_id, entry.address, entry.port, entry.status) == (
        None,
        "02:00:00:00:00:01",
        3,
        FdbStatus.LEARNED,
    )


async def test_stp() -> None:
    stp = await recorded("switch-1").get_stp()
    assert stp is not None
    assert stp.root_port == 0  # switch-1 is the root bridge
    assert stp.designated_root == "1000.020000000002"
    assert stp.top_changes == 2
    assert stp.port_states[1] is StpPortState.FORWARDING
    assert stp.port_states[2] is StpPortState.DISABLED  # a trunk member
    other = await recorded("switch-2").get_stp()
    assert other is not None
    assert other.root_port == 7
    assert await SnmpSwitch(RecordedTransport({})).get_stp() is None


async def test_lldp_1920s() -> None:
    lldp = await recorded("switch-1").get_lldp()
    assert (lldp.chassis_id_subtype, lldp.chassis_id, lldp.sys_name) == (
        4,
        "02:00:00:00:00:02",
        "switch-1",
    )
    assert lldp.ports[7].port_id_subtype == 3  # the 1920S uses one MAC address for all ports
    by_port = {remote.local_port_num: remote for remote in lldp.remotes}
    assert sorted(by_port) == [5, 7]
    switch_2, switch_3 = by_port[7], by_port[5]
    assert (switch_2.sys_name, switch_2.chassis_id, switch_2.port_id_subtype) == (
        "switch-2",
        "02:00:00:00:00:0a",
        3,
    )
    assert switch_2.sys_cap_enabled == frozenset({"bridge"})
    assert switch_2.management_addresses == ("192.0.2.2",)
    assert switch_2.port_desc == "port description 6"
    assert (switch_3.sys_name, switch_3.port_id) == ("switch-3", "1")
    assert switch_3.sys_desc is not None
    assert "1930" in switch_3.sys_desc


async def test_lldp_1930() -> None:
    lldp = await recorded("switch-3").get_lldp()
    assert lldp.ports[1].port_id_subtype == 5
    assert lldp.ports[1].port_id == "1"  # interface name
    assert [(r.local_port_num, r.sys_name) for r in lldp.remotes] == [(1, "switch-1")]


async def test_lag() -> None:
    switch = recorded("switch-1")
    assert lag_members(await switch.get_lag_ports(), await switch.get_interfaces()) == {
        2: 54,
        3: 54,
        6: 55,
        8: 55,
    }
    other = recorded("switch-3")
    lag_ports = await other.get_lag_ports()
    assert lag_ports[1] == 1  # the 1930 attaches a port in no trunk to itself
    assert lag_members(lag_ports, await other.get_interfaces()) == {}


async def test_poe() -> None:
    poe = await recorded("switch-1").get_poe()
    assert len(poe.supplies) == 1
    supply = poe.supplies[0]
    assert (supply.group, supply.power, supply.consumption_power, supply.usage_threshold) == (
        1,
        65,
        0,
        99,
    )
    assert supply.oper_status is PseOperStatus.OFF
    assert [(p.group, p.index) for p in poe.ports] == [(1, 1), (1, 2), (1, 3), (1, 4)]
    assert poe.ports[0].admin_enable is True
    assert poe.ports[0].detection_status is PseDetectionStatus.SEARCHING
    assert poe.ports[0].power_classifications is None
    empty = await recorded("switch-3").get_poe()
    assert (empty.supplies, empty.ports) == ([], [])


async def test_neighbors() -> None:
    entries = await recorded("switch-3").get_neighbors()
    addresses = {e.address for e in entries}
    assert "fe80::4" in addresses  # IPv6 link-local from ipNetToPhysicalTable, zone index dropped
    assert "192.0.2.6" in addresses  # IPv4 only in ipNetToMediaTable on the 1930
    assert len(addresses) == len(entries)
    assert await recorded("switch-1").get_neighbors() == []


async def test_neighbors_skip_malformed_rows() -> None:
    mac = b"\x02\x00\x00\x00\x00\x01"
    values = {
        "1.3.6.1.2.1.4.35.1.4.5.1.4.192.0.2.1": mac,  # IPv4
        "1.3.6.1.2.1.4.35.1.4.5.2.16.32.1.13.184.0.0.0.0.0.0.0.0.0.0.0.1": mac,  # IPv6
        "1.3.6.1.2.1.4.35.1.4.5.1.5.192.0.2.1.1": mac,  # wrong length for IPv4
        "1.3.6.1.2.1.4.35.1.4.5.1.4.192.0.2.2": b"\x01",  # not a MAC address
        "1.3.6.1.2.1.4.22.1.2.5.192.0.2.1": mac,  # already known
        "1.3.6.1.2.1.4.22.1.2.5.192.0.2.9": b"",  # not a MAC address
    }
    entries = await SnmpSwitch(RecordedTransport(values)).get_neighbors()
    assert [e.address for e in entries] == ["192.0.2.1", "2001:db8::1"]


async def test_lldp_without_addresses_or_bad_index() -> None:
    values: dict[str, int | bytes | ObjectId] = {
        "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": b"peer",
        "1.0.8802.1.1.2.1.4.2.1.3.0.1.1.1.4.192.0.2.1": 2,
        "1.0.8802.1.1.2.1.4.2.1.3.0.1.1.3.2.1.2": 2,  # an address family other than IP
        "1.0.8802.1.1.2.1.4.2.1.3.0.1": 2,  # too short to hold an address
        "1.0.8802.1.1.2.1.4.1.1.9.0.1": b"x",  # remote index of two parts: skipped
        "1.0.8802.1.1.2.1.3.7.1.3.1.1": b"x",  # local port index of two parts: skipped
    }
    lldp = await SnmpSwitch(RecordedTransport(values)).get_lldp()
    assert lldp.chassis_id is None
    assert lldp.ports == {}
    assert [(r.sys_name, r.management_addresses) for r in lldp.remotes] == [
        ("peer", ("192.0.2.1",))
    ]


async def test_supplies_and_ports_with_odd_indexes() -> None:
    values = {
        "1.3.6.1.2.1.105.1.3.1.1.2.1.1": 30,  # supply index of two parts: skipped
        "1.3.6.1.2.1.105.1.1.1.3.1": 1,  # port index of one part: skipped
    }
    poe = await SnmpSwitch(RecordedTransport(values)).get_poe()
    assert (poe.supplies, poe.ports) == ([], [])


async def test_context_manager_closes() -> None:
    async with SnmpSwitch(RecordedTransport({})) as switch:
        assert await switch.get_bridge_ports() == {}
