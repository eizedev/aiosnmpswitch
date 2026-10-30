"""The switch client: one getter per MIB table or group, all of them reads."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, Self

from . import oids
from ._parse import (
    bridge_id,
    capabilities,
    ip_from_octets,
    lldp_id,
    to_enum,
    to_int,
    to_mac,
    to_oid,
    to_str,
    to_truth,
)
from .auth import Auth
from .models import (
    AdminStatus,
    Chassis,
    FdbEntry,
    FdbStatus,
    Interface,
    Lldp,
    LldpLocalPort,
    LldpRemote,
    MainPse,
    NeighborEntry,
    OperStatus,
    Poe,
    PseDetectionStatus,
    PseOperStatus,
    PsePort,
    SensorStatus,
    StpInfo,
    StpPortState,
    SystemInfo,
    Temperature,
)
from .transport import PysnmpTransport, Transport, Value

Column = dict[tuple[int, ...], Value]
"""Values of one table column by index."""

# InetAddressType values in the index of ipNetToPhysicalTable and lengths of their addresses.
_INET_ADDRESS_LENGTH = {1: 4, 2: 16, 3: 8, 4: 20}
_MAC_OCTETS = 6
_CHASSIS = 3  # entPhysicalClass chassis(3)
_CELSIUS = 8  # entPhySensorType celsius(8)
_UNITS = 9  # entPhySensorScale units(9); each step is a factor of 1000 (RFC 3433, yocto to tera)
# Scales 14-17 (exa, peta, zetta, yotta, not in ascending order in the RFC) are left out on purpose:
# no temperature needs them.
_SCALES = range(1, 14)
_PRECISIONS = range(-8, 10)  # entPhySensorPrecision, RFC 3433
# A vendor table's reading outside this range is taken as misread (wrong unit or precision).
_PLAUSIBLE_CELSIUS = (-40, 150)
_SENSOR_COLUMNS = range(1, 6)  # type, scale, precision, value, oper status
_NET_TO_PHYSICAL_PREFIX = 3  # ifIndex, address type, address length
_LLDP_REM_INDEX_PARTS = 3
_LLDP_MAN_ADDR_PREFIX = 5  # time mark, local port, index, address subtype, address length


class SnmpSwitch:
    """Reads a managed switch over SNMP.

    Every getter reads one MIB group and returns an empty result when the switch does not have
    it, so the same code works on switches with fewer MIBs. Errors on the way (timeout, wrong
    credentials) raise :class:`~aiosnmpswitch.errors.SnmpError` subclasses.
    """

    def __init__(self, transport: Transport) -> None:
        """Read through ``transport``; :meth:`connect` creates one for a host."""
        self.transport = transport

    @classmethod
    async def connect(cls, host: str, auth: Auth, **options: Any) -> Self:
        """Client for ``host``; ``options`` go to :meth:`PysnmpTransport.create`."""
        return cls(await PysnmpTransport.create(host, auth, **options))

    async def close(self) -> None:
        """Release the transport."""
        await self.transport.close()

    async def __aenter__(self) -> Self:
        """Use the client in ``async with``."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close the transport."""
        await self.close()

    async def _table(self, table: str) -> dict[str, Column]:
        """Walk ``table`` (the OID of its entry) and split the rows into columns."""
        columns: dict[str, Column] = defaultdict(dict)
        prefix_length = len(table.split("."))
        for oid, value in await self.transport.walk(table):
            parts = oid.split(".")
            if len(parts) <= prefix_length + 1:  # a column without a row index: not a cell
                continue
            column = ".".join(parts[: prefix_length + 1])
            columns[column][tuple(int(p) for p in parts[prefix_length + 1 :])] = value
        return columns

    async def get_system(self) -> SystemInfo:
        """SNMPv2-MIB system group."""
        names = (
            oids.SYS_DESCR,
            oids.SYS_OBJECT_ID,
            oids.SYS_UP_TIME,
            oids.SYS_CONTACT,
            oids.SYS_NAME,
            oids.SYS_LOCATION,
        )
        values = await self.transport.get([f"{oid}.0" for oid in names])

        def value(oid: str) -> Value | None:
            return values.get(f"{oid}.0")

        return SystemInfo(
            descr=to_str(value(oids.SYS_DESCR)),
            object_id=to_oid(value(oids.SYS_OBJECT_ID)),
            up_time=to_int(value(oids.SYS_UP_TIME)),
            contact=to_str(value(oids.SYS_CONTACT)),
            name=to_str(value(oids.SYS_NAME)),
            location=to_str(value(oids.SYS_LOCATION)),
        )

    async def get_chassis(self) -> Chassis | None:
        """ENTITY-MIB: model and firmware of the chassis, or ``None`` without the MIB.

        ``sysDescr`` holds the same for many switches, but in a vendor's own format; the chassis
        row names them separately.
        """
        classes = await self.transport.walk(oids.ENT_PHYSICAL_CLASS)
        chassis = sorted(int(oid.rsplit(".", 1)[1]) for oid, value in classes if value == _CHASSIS)
        if not chassis:
            return None
        index = chassis[0]
        names = (
            oids.ENT_PHYSICAL_DESCR,
            oids.ENT_PHYSICAL_MODEL_NAME,
            oids.ENT_PHYSICAL_SOFTWARE_REV,
        )
        values = await self.transport.get([f"{oid}.{index}" for oid in names])
        descr, model_name, software_rev = (to_str(values.get(f"{oid}.{index}")) for oid in names)
        return Chassis(descr=descr, model_name=model_name, software_rev=software_rev)

    async def get_temperatures(self) -> list[Temperature]:
        """Temperature sensors: ENTITY-SENSOR-MIB, else a known vendor table; empty without.

        The HPE Instant On 1930 has no ``entPhySensorTable`` but the same columns under a vendor
        OID. Its precision column says one decimal place while the value is whole degrees (54
        means 54 °C, measured), so the vendor reading ignores the precision.
        """
        table = await self._table(oids.ENT_PHY_SENSOR_ENTRY)
        if table:
            indexes = [
                i[0]
                for i, v in table.get(oids.ENT_PHY_SENSOR_TYPE, {}).items()
                if v == _CELSIUS and len(i) == 1
            ]
            values = await self.transport.get([f"{oids.ENT_PHYSICAL_NAME}.{i}" for i in indexes])
            names = {i: to_str(values.get(f"{oids.ENT_PHYSICAL_NAME}.{i}")) for i in indexes}
            return _temperatures(table, names, indexes, precise=True)
        object_id = await self.transport.get([f"{oids.SYS_OBJECT_ID}.0"])
        if to_oid(object_id.get(f"{oids.SYS_OBJECT_ID}.0")) != oids.HPE_1930_OBJECT_ID:
            return []
        vendor_table: dict[str, Column] = {}
        for number in _SENSOR_COLUMNS:  # only the columns used, not the whole entry
            column = f"{oids.HPE_1930_SENSOR_ENTRY}.{number}"
            vendor_table[column] = {
                (int(oid.rsplit(".", 1)[1]),): value
                for oid, value in await self.transport.walk(column)
                if oid.rsplit(".", 1)[1].isdigit()
            }
        type_column = vendor_table[f"{oids.HPE_1930_SENSOR_ENTRY}.1"]
        indexes = [i[0] for i, v in type_column.items() if v == _CELSIUS]
        names = {
            int(oid.rsplit(".", 1)[1]): to_str(value)
            for oid, value in await self.transport.walk(oids.HPE_1930_SENSOR_NAME)
        }
        # the same columns as entPhySensorTable: rename them to read both alike
        vendor = {
            oids.ENT_PHY_SENSOR_ENTRY + key.removeprefix(oids.HPE_1930_SENSOR_ENTRY): rows
            for key, rows in vendor_table.items()
        }
        return _temperatures(vendor, names, indexes, precise=False)

    async def get_interfaces(self) -> dict[int, Interface]:
        """IF-MIB ``ifTable`` and ``ifXTable``, by ``ifIndex``."""
        table = await self._table("1.3.6.1.2.1.2.2.1")
        table.update(await self._table("1.3.6.1.2.1.31.1.1.1"))
        indexes = {index[0] for column in table.values() for index in column if len(index) == 1}

        def get[T](column: str, convert: Callable[[Value | None], T], index: int) -> T:
            return convert(table.get(column, {}).get((index,)))

        return {
            index: Interface(
                index=index,
                descr=get(oids.IF_DESCR, to_str, index),
                type=get(oids.IF_TYPE, to_int, index),
                mtu=get(oids.IF_MTU, to_int, index),
                speed=get(oids.IF_SPEED, to_int, index),
                phys_address=get(oids.IF_PHYS_ADDRESS, to_mac, index),
                admin_status=get(oids.IF_ADMIN_STATUS, _enum(AdminStatus), index),
                oper_status=get(oids.IF_OPER_STATUS, _enum(OperStatus), index),
                last_change=get(oids.IF_LAST_CHANGE, to_int, index),
                in_octets=get(oids.IF_IN_OCTETS, to_int, index),
                in_discards=get(oids.IF_IN_DISCARDS, to_int, index),
                in_errors=get(oids.IF_IN_ERRORS, to_int, index),
                out_octets=get(oids.IF_OUT_OCTETS, to_int, index),
                out_discards=get(oids.IF_OUT_DISCARDS, to_int, index),
                out_errors=get(oids.IF_OUT_ERRORS, to_int, index),
                name=get(oids.IF_NAME, to_str, index),
                hc_in_octets=get(oids.IF_HC_IN_OCTETS, to_int, index),
                hc_in_ucast_pkts=get(oids.IF_HC_IN_UCAST_PKTS, to_int, index),
                hc_in_multicast_pkts=get(oids.IF_HC_IN_MULTICAST_PKTS, to_int, index),
                hc_in_broadcast_pkts=get(oids.IF_HC_IN_BROADCAST_PKTS, to_int, index),
                hc_out_octets=get(oids.IF_HC_OUT_OCTETS, to_int, index),
                hc_out_ucast_pkts=get(oids.IF_HC_OUT_UCAST_PKTS, to_int, index),
                hc_out_multicast_pkts=get(oids.IF_HC_OUT_MULTICAST_PKTS, to_int, index),
                hc_out_broadcast_pkts=get(oids.IF_HC_OUT_BROADCAST_PKTS, to_int, index),
                high_speed=get(oids.IF_HIGH_SPEED, to_int, index),
                alias=get(oids.IF_ALIAS, to_str, index),
            )
            for index in sorted(indexes)
        }

    async def get_bridge_ports(self) -> dict[int, int]:
        """BRIDGE-MIB ``dot1dBasePortIfIndex``: ``ifIndex`` by bridge port number."""
        rows = await self.transport.walk(oids.DOT1D_BASE_PORT_IF_INDEX)
        return {
            int(oid.rsplit(".", 1)[1]): if_index
            for oid, value in rows
            if (if_index := to_int(value)) is not None
        }

    async def get_fdb(self) -> list[FdbEntry]:
        """Read the forwarding database (MAC address table).

        Q-BRIDGE-MIB first, which knows the VLAN; BRIDGE-MIB if the switch has no Q-BRIDGE table.
        """
        table = await self._table("1.3.6.1.2.1.17.7.1.2.2.1")
        port_column, status_column, has_fdb_id = (
            oids.DOT1Q_TP_FDB_PORT,
            oids.DOT1Q_TP_FDB_STATUS,
            True,
        )
        if not table:
            table = await self._table("1.3.6.1.2.1.17.4.3.1")
            port_column, status_column, has_fdb_id = (
                oids.DOT1D_TP_FDB_PORT,
                oids.DOT1D_TP_FDB_STATUS,
                False,
            )
        ports, statuses = table.get(port_column, {}), table.get(status_column, {})
        entries = []
        for index in sorted(ports.keys() | statuses.keys()):
            fdb_id, mac = (index[0], index[1:]) if has_fdb_id else (None, index)
            if len(mac) != _MAC_OCTETS or max(mac) > 0xFF:  # noqa: PLR2004 - octets
                continue
            entries.append(
                FdbEntry(
                    fdb_id=fdb_id,
                    address=bytes(mac).hex(":"),
                    port=to_int(ports.get(index)),
                    status=to_enum(FdbStatus, statuses.get(index)),
                )
            )
        return entries

    async def get_stp(self) -> StpInfo | None:
        """BRIDGE-MIB spanning tree; ``None`` if the switch has none."""
        names = (
            oids.DOT1D_STP_TIME_SINCE_TOPOLOGY_CHANGE,
            oids.DOT1D_STP_TOP_CHANGES,
            oids.DOT1D_STP_DESIGNATED_ROOT,
            oids.DOT1D_STP_ROOT_COST,
            oids.DOT1D_STP_ROOT_PORT,
        )
        values = await self.transport.get([f"{oid}.0" for oid in names])
        states = await self.transport.walk(oids.DOT1D_STP_PORT_STATE)
        if not values and not states:
            return None
        return StpInfo(
            time_since_topology_change=to_int(
                values.get(f"{oids.DOT1D_STP_TIME_SINCE_TOPOLOGY_CHANGE}.0")
            ),
            top_changes=to_int(values.get(f"{oids.DOT1D_STP_TOP_CHANGES}.0")),
            designated_root=bridge_id(values.get(f"{oids.DOT1D_STP_DESIGNATED_ROOT}.0")),
            root_cost=to_int(values.get(f"{oids.DOT1D_STP_ROOT_COST}.0")),
            root_port=to_int(values.get(f"{oids.DOT1D_STP_ROOT_PORT}.0")),
            port_states={
                int(oid.rsplit(".", 1)[1]): state
                for oid, value in states
                if (state := to_enum(StpPortState, value)) is not None
            },
        )

    async def get_lldp(self) -> Lldp:
        """LLDP-MIB: this switch's chassis and ports, and the neighbours it sees."""
        scalars = (
            oids.LLDP_LOC_CHASSIS_ID_SUBTYPE,
            oids.LLDP_LOC_CHASSIS_ID,
            oids.LLDP_LOC_SYS_NAME,
        )
        local = await self.transport.get([f"{oid}.0" for oid in scalars])
        port_table = await self._table("1.0.8802.1.1.2.1.3.7.1")
        remote = await self._table("1.0.8802.1.1.2.1.4.1.1")
        addresses = await self._table("1.0.8802.1.1.2.1.4.2.1")

        def scalar(oid: str) -> Value | None:
            return local.get(f"{oid}.0")

        chassis_subtype = to_int(scalar(oids.LLDP_LOC_CHASSIS_ID_SUBTYPE))
        port_subtypes = port_table.get(oids.LLDP_LOC_PORT_ID_SUBTYPE, {})
        port_ids = port_table.get(oids.LLDP_LOC_PORT_ID, {})
        ports = {
            index[0]: LldpLocalPort(
                port_num=index[0],
                port_id_subtype=(subtype := to_int(port_subtypes.get(index))),
                port_id=lldp_id(subtype, port_ids.get(index), chassis=False),
            )
            for index in sorted(port_subtypes.keys() | port_ids.keys())
            if len(index) == 1
        }
        management: dict[tuple[int, ...], list[str]] = defaultdict(list)
        for index in addresses.get(oids.LLDP_REM_MAN_ADDR_IF_SUBTYPE, {}):
            if (address := _management_address(index)) is not None:
                management[index[:_LLDP_REM_INDEX_PARTS]].append(address)
        return Lldp(
            chassis_id_subtype=chassis_subtype,
            chassis_id=lldp_id(chassis_subtype, scalar(oids.LLDP_LOC_CHASSIS_ID), chassis=True),
            sys_name=to_str(scalar(oids.LLDP_LOC_SYS_NAME)),
            ports=ports,
            remotes=_remotes(remote, management),
        )

    async def get_lag_ports(self) -> dict[int, int]:
        """IEEE8023-LAG-MIB ``dot3adAggPortAttachedAggID`` by member ``ifIndex``.

        The value is the aggregator's ``ifIndex``; 0, or the port's own ``ifIndex`` (HPE Instant
        On 1930), means the port is in no trunk. :func:`~aiosnmpswitch.helpers.lag_members`
        interprets it.
        """
        rows = await self.transport.walk(oids.DOT3AD_AGG_PORT_ATTACHED_AGG_ID)
        return {
            int(oid.rsplit(".", 1)[1]): aggregator
            for oid, value in rows
            if (aggregator := to_int(value)) is not None
        }

    async def get_poe(self) -> Poe:
        """POWER-ETHERNET-MIB supplies and ports; empty lists on switches without PoE."""
        ports = await self._table("1.3.6.1.2.1.105.1.1.1")
        supplies = await self._table("1.3.6.1.2.1.105.1.3.1.1")
        port_indexes = sorted({index for column in ports.values() for index in column})
        supply_indexes = sorted({index for column in supplies.values() for index in column})

        def port(column: str, index: tuple[int, ...]) -> Value | None:
            return ports.get(column, {}).get(index)

        def supply(column: str, index: tuple[int, ...]) -> Value | None:
            return supplies.get(column, {}).get(index)

        return Poe(
            supplies=[
                MainPse(
                    group=index[0],
                    power=to_int(supply(oids.PETH_MAIN_PSE_POWER, index)),
                    oper_status=to_enum(
                        PseOperStatus, supply(oids.PETH_MAIN_PSE_OPER_STATUS, index)
                    ),
                    consumption_power=to_int(supply(oids.PETH_MAIN_PSE_CONSUMPTION_POWER, index)),
                    usage_threshold=to_int(supply(oids.PETH_MAIN_PSE_USAGE_THRESHOLD, index)),
                )
                for index in supply_indexes
                if len(index) == 1
            ],
            ports=[
                PsePort(
                    group=index[0],
                    index=index[1],
                    admin_enable=to_truth(port(oids.PETH_PSE_PORT_ADMIN_ENABLE, index)),
                    detection_status=to_enum(
                        PseDetectionStatus, port(oids.PETH_PSE_PORT_DETECTION_STATUS, index)
                    ),
                    power_classifications=to_int(
                        port(oids.PETH_PSE_PORT_POWER_CLASSIFICATIONS, index)
                    ),
                )
                for index in port_indexes
                if len(index) == 2  # noqa: PLR2004 - group and port
            ],
        )

    async def get_neighbors(self) -> list[NeighborEntry]:
        """Read the switch's own ARP and IPv6 neighbour cache (IP-MIB).

        Both ``ipNetToPhysicalTable`` (IPv4 and IPv6) and the older ``ipNetToMediaTable`` (IPv4)
        are read, because some switches (HPE Instant On 1930) list IPv4 only in the older one;
        an address in both appears once. Many switches keep only the addresses they talked to
        themselves, so this is not a list of all devices.
        """
        entries = []
        for oid, value in await self.transport.walk(oids.IP_NET_TO_PHYSICAL_PHYS_ADDRESS):
            index = [
                int(p) for p in oid[len(oids.IP_NET_TO_PHYSICAL_PHYS_ADDRESS) + 1 :].split(".")
            ]
            if len(index) < _NET_TO_PHYSICAL_PREFIX:
                continue
            if_index, address_type, length, address = index[0], index[1], index[2], index[3:]
            if _INET_ADDRESS_LENGTH.get(address_type) != length or len(address) != length:
                continue
            # The zoned types (3, 4) end with a four-octet zone index, which is not shown.
            ip = ip_from_octets(address[:4] if address_type in (1, 3) else address[:16])
            mac = to_mac(value)
            if ip and mac:
                entries.append(NeighborEntry(if_index=if_index, address=ip, phys_address=mac))
        known = {entry.address for entry in entries}
        for oid, value in await self.transport.walk(oids.IP_NET_TO_MEDIA_PHYS_ADDRESS):
            index = [int(p) for p in oid[len(oids.IP_NET_TO_MEDIA_PHYS_ADDRESS) + 1 :].split(".")]
            ip = ip_from_octets(index[1:])
            mac = to_mac(value)
            if ip and mac and ip not in known and len(index) > 1:
                entries.append(NeighborEntry(if_index=index[0], address=ip, phys_address=mac))
        return entries


def _enum[E: (AdminStatus, OperStatus)](enum: type[E]) -> Callable[[Value | None], E | None]:
    """Return a converter to ``enum`` for :meth:`SnmpSwitch.get_interfaces`."""
    return lambda value: to_enum(enum, value)


def _management_address(index: tuple[int, ...]) -> str | None:
    """Return the address in an ``lldpRemManAddrTable`` index (IPv4 and IPv6 only)."""
    if len(index) < _LLDP_MAN_ADDR_PREFIX:
        return None
    subtype, length, address = index[3], index[4], index[_LLDP_MAN_ADDR_PREFIX:]
    if subtype not in (1, 2) or len(address) != length:
        return None
    return ip_from_octets(address)


def _remotes(
    table: dict[str, Column], management: dict[tuple[int, ...], list[str]]
) -> list[LldpRemote]:
    """Rows of ``lldpRemTable`` as :class:`LldpRemote`."""

    def get(column: str, index: tuple[int, ...]) -> Value | None:
        return table.get(column, {}).get(index)

    indexes = sorted(
        {
            index
            for column in table.values()
            for index in column
            if len(index) == _LLDP_REM_INDEX_PARTS
        }
    )
    remotes = []
    for index in indexes:
        chassis_subtype = to_int(get(oids.LLDP_REM_CHASSIS_ID_SUBTYPE, index))
        port_subtype = to_int(get(oids.LLDP_REM_PORT_ID_SUBTYPE, index))
        remotes.append(
            LldpRemote(
                time_mark=index[0],
                local_port_num=index[1],
                index=index[2],
                chassis_id_subtype=chassis_subtype,
                chassis_id=lldp_id(
                    chassis_subtype, get(oids.LLDP_REM_CHASSIS_ID, index), chassis=True
                ),
                port_id_subtype=port_subtype,
                port_id=lldp_id(port_subtype, get(oids.LLDP_REM_PORT_ID, index), chassis=False),
                port_desc=to_str(get(oids.LLDP_REM_PORT_DESC, index)),
                sys_name=to_str(get(oids.LLDP_REM_SYS_NAME, index)),
                sys_desc=to_str(get(oids.LLDP_REM_SYS_DESC, index)),
                sys_cap_enabled=capabilities(get(oids.LLDP_REM_SYS_CAP_ENABLED, index)),
                management_addresses=tuple(management.get(index, ())),
            )
        )
    return remotes


def _temperatures(
    table: dict[str, Column], names: dict[int, str | None], indexes: list[int], *, precise: bool
) -> list[Temperature]:
    """Turn ``entPhySensorTable`` rows into temperatures in degrees Celsius.

    A reading is ``None`` when the sensor reports itself not ok, or when scale or precision are
    missing or outside RFC 3433. ``precise=False`` (a vendor table whose precision is wrong)
    ignores the precision and drops readings outside a plausible range instead.
    """

    def cell(column: str, index: int) -> Value | None:
        return table.get(column, {}).get((index,))

    result = []
    for index in sorted(indexes):
        value = to_int(cell(oids.ENT_PHY_SENSOR_VALUE, index))
        scale = to_int(cell(oids.ENT_PHY_SENSOR_SCALE, index))
        precision = to_int(cell(oids.ENT_PHY_SENSOR_PRECISION, index)) if precise else 0
        status = to_enum(SensorStatus, cell(oids.ENT_PHY_SENSOR_OPER_STATUS, index))
        celsius = None
        if (
            value is not None
            and scale in _SCALES
            and precision in _PRECISIONS
            and status in (None, SensorStatus.OK)
        ):
            exponent = 3 * (scale - _UNITS) - precision  # type: ignore[operator]  # checked above
            try:
                celsius = round(value * 10.0**exponent, 3)
            except OverflowError:  # a value beyond any float
                celsius = None
            low, high = _PLAUSIBLE_CELSIUS
            if celsius is not None and not precise and not low <= celsius <= high:
                celsius = None
        result.append(
            Temperature(index=index, name=names.get(index), celsius=celsius, status=status)
        )
    return result
