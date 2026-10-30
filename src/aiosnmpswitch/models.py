"""What a switch answers, one frozen dataclass per MIB table or group.

Fields are named after the MIB objects in snake_case, without the table prefix (``ifHighSpeed``
becomes ``Interface.high_speed``), and keep the MIB's units. A field is ``None`` when the switch
does not have the object. Interpretation (which port a device is on, uplinks, trunks) lives in
:mod:`aiosnmpswitch.helpers`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class AdminStatus(IntEnum):
    """``ifAdminStatus``."""

    UP = 1
    DOWN = 2
    TESTING = 3


class OperStatus(IntEnum):
    """``ifOperStatus``."""

    UP = 1
    DOWN = 2
    TESTING = 3
    UNKNOWN = 4
    DORMANT = 5
    NOT_PRESENT = 6
    LOWER_LAYER_DOWN = 7


class FdbStatus(IntEnum):
    """``dot1qTpFdbStatus`` / ``dot1dTpFdbStatus``."""

    OTHER = 1
    INVALID = 2
    LEARNED = 3
    SELF = 4
    MGMT = 5


class StpPortState(IntEnum):
    """``dot1dStpPortState``."""

    DISABLED = 1
    BLOCKING = 2
    LISTENING = 3
    LEARNING = 4
    FORWARDING = 5
    BROKEN = 6


class PseDetectionStatus(IntEnum):
    """``pethPsePortDetectionStatus``."""

    DISABLED = 1
    SEARCHING = 2
    DELIVERING_POWER = 3
    FAULT = 4
    TEST = 5
    OTHER_FAULT = 6


class PseOperStatus(IntEnum):
    """``pethMainPseOperStatus``."""

    ON = 1
    OFF = 2
    FAULTY = 3


class SensorStatus(IntEnum):
    """``entPhySensorOperStatus``."""

    OK = 1
    UNAVAILABLE = 2
    NONOPERATIONAL = 3


@dataclass(frozen=True, slots=True)
class Temperature:
    """One temperature sensor of the switch."""

    index: int
    """``entPhysicalIndex`` of the sensor (or the vendor table's index)."""
    name: str | None
    """The sensor's name as the switch gives it, for example ``PHY``."""
    celsius: float | None
    """The reading in degrees Celsius, or ``None`` without a value."""
    status: SensorStatus | None


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """SNMPv2-MIB system group."""

    descr: str | None
    """``sysDescr``: model and firmware, as the vendor writes them."""
    object_id: str | None
    """``sysObjectID``: the vendor's model OID."""
    up_time: int | None
    """``sysUpTime``, in hundredths of a second since the SNMP agent started."""
    contact: str | None
    name: str | None
    location: str | None


@dataclass(frozen=True, slots=True)
class Chassis:
    """ENTITY-MIB: the switch's chassis, the first ``entPhysicalTable`` row of class chassis."""

    descr: str | None
    """``entPhysicalDescr``: the vendor's product name, often with the part number."""
    model_name: str | None
    """``entPhysicalModelName``: the vendor's model name or part number."""
    software_rev: str | None
    """``entPhysicalSoftwareRev``: the firmware version."""


@dataclass(frozen=True, slots=True)
class Interface:
    """One row of ``ifTable`` and ``ifXTable``."""

    index: int
    """``ifIndex``."""
    descr: str | None = None
    type: int | None = None
    """``ifType`` (IANAifType): 6 Ethernet, 161 IEEE 802.3ad link aggregation, ..."""
    mtu: int | None = None
    speed: int | None = None
    """``ifSpeed``, bits per second, capped at 4294967295."""
    phys_address: str | None = None
    """``ifPhysAddress`` as ``aa:bb:cc:dd:ee:ff``."""
    admin_status: AdminStatus | None = None
    oper_status: OperStatus | None = None
    last_change: int | None = None
    """``ifLastChange``: ``sysUpTime`` at the last status change, hundredths of a second."""
    in_octets: int | None = None
    in_discards: int | None = None
    in_errors: int | None = None
    out_octets: int | None = None
    out_discards: int | None = None
    out_errors: int | None = None
    name: str | None = None
    """``ifName``, the name the switch shows for the port."""
    hc_in_octets: int | None = None
    hc_in_ucast_pkts: int | None = None
    hc_in_multicast_pkts: int | None = None
    hc_in_broadcast_pkts: int | None = None
    hc_out_octets: int | None = None
    hc_out_ucast_pkts: int | None = None
    hc_out_multicast_pkts: int | None = None
    hc_out_broadcast_pkts: int | None = None
    high_speed: int | None = None
    """``ifHighSpeed``, megabits per second; 0 on many switches while the link is down."""
    alias: str | None = None
    """``ifAlias``, the description an administrator gave the port."""


@dataclass(frozen=True, slots=True)
class FdbEntry:
    """One learned or static address of the forwarding database (MAC address table)."""

    fdb_id: int | None
    """``dot1qFdbId`` (usually the VLAN); ``None`` from BRIDGE-MIB's ``dot1dTpFdbTable``."""
    address: str
    """MAC address as ``aa:bb:cc:dd:ee:ff``."""
    port: int | None
    """Bridge port number (``dot1dBasePort``); 0 or ``None`` if the switch does not say."""
    status: FdbStatus | None


@dataclass(frozen=True, slots=True)
class StpInfo:
    """BRIDGE-MIB spanning tree scalars and port states."""

    time_since_topology_change: int | None
    """Hundredths of a second."""
    top_changes: int | None
    designated_root: str | None
    """Bridge ID of the root: priority and MAC address as hex, ``8000.aabbccddeeff``."""
    root_cost: int | None
    root_port: int | None
    """Bridge port towards the root; 0 on the root itself."""
    port_states: dict[int, StpPortState] = field(default_factory=dict)
    """``dot1dStpPortState`` by bridge port number."""


@dataclass(frozen=True, slots=True)
class LldpLocalPort:
    """One row of ``lldpLocPortTable``: how this switch names a port in its LLDP messages."""

    port_num: int
    """``lldpLocPortNum``, the number ``LldpRemote.local_port_num`` refers to."""
    port_id_subtype: int | None
    port_id: str | None


@dataclass(frozen=True, slots=True)
class LldpRemote:
    """One neighbour from ``lldpRemTable``."""

    time_mark: int
    local_port_num: int
    """``lldpRemLocalPortNum``: the port of this switch the neighbour was seen on."""
    index: int
    chassis_id_subtype: int | None = None
    chassis_id: str | None = None
    """MAC address as ``aa:bb:cc:dd:ee:ff`` for subtype 4, otherwise text or hex."""
    port_id_subtype: int | None = None
    port_id: str | None = None
    port_desc: str | None = None
    sys_name: str | None = None
    sys_desc: str | None = None
    sys_cap_enabled: frozenset[str] = frozenset()
    """Enabled capabilities: ``other``, ``repeater``, ``bridge``, ``wlanAccessPoint``,
    ``router``, ``telephone``, ``docsisCableDevice``, ``stationOnly``."""
    management_addresses: tuple[str, ...] = ()
    """IPv4 and IPv6 addresses from ``lldpRemManAddrTable``."""


@dataclass(frozen=True, slots=True)
class Lldp:
    """LLDP-MIB: this switch's identity and its neighbours."""

    chassis_id_subtype: int | None
    chassis_id: str | None
    sys_name: str | None
    ports: dict[int, LldpLocalPort]
    remotes: list[LldpRemote]


@dataclass(frozen=True, slots=True)
class PsePort:
    """One row of ``pethPsePortTable``."""

    group: int
    index: int
    """``pethPsePortIndex``; on the switches tested so far the same number as the ``ifIndex``."""
    admin_enable: bool | None
    detection_status: PseDetectionStatus | None
    power_classifications: int | None
    """Power class of the powered device as ``class0`` = 1 ... ``class4`` = 5."""


@dataclass(frozen=True, slots=True)
class MainPse:
    """One row of ``pethMainPseTable``: a power supply group."""

    group: int
    power: int | None
    """Nominal power of the supply, watts."""
    oper_status: PseOperStatus | None
    consumption_power: int | None
    """Power drawn by all powered devices, watts."""
    usage_threshold: int | None
    """Percent of ``power`` at which the switch warns."""


@dataclass(frozen=True, slots=True)
class Poe:
    """POWER-ETHERNET-MIB: supplies and ports."""

    supplies: list[MainPse]
    ports: list[PsePort]


@dataclass(frozen=True, slots=True)
class NeighborEntry:
    """One entry of the switch's own ARP or IPv6 neighbour cache (IP-MIB)."""

    if_index: int
    address: str
    """IPv4 or IPv6 address."""
    phys_address: str
    """MAC address as ``aa:bb:cc:dd:ee:ff``."""
