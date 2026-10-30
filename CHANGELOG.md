# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-30

### Added

- `get_temperatures()`: temperature sensors from the ENTITY-SENSOR-MIB, in degrees Celsius with
  name and status. On the HPE Instant On 1930, which has no standard sensor table, from its
  vendor table (measured; read only on that model). Diagnostics count the sensors; recordings
  include these tables and `entPhysicalName`.

## [0.2.0] - 2026-10-30

### Added

- `get_chassis()`: product name, model name and firmware of the chassis from the ENTITY-MIB, for
  switches whose `sysDescr` does not split into model and firmware. The diagnostics show it, and
  recordings include these three columns (no serial numbers).

## [0.1.0] - 2026-10-30

First release.

### Added

- `SnmpSwitch` with one getter per MIB group: system, interfaces (`ifTable`, `ifXTable`), bridge
  ports, address table (Q-BRIDGE-MIB, BRIDGE-MIB), spanning tree, LLDP, trunks (LAG-MIB), PoE
  (POWER-ETHERNET-MIB) and the neighbour cache (IP-MIB).
- SNMPv1, v2c and v3 (all authentication and privacy protocols pysnmp offers).
- `helpers.locate_macs()`: the port every device is connected to, across several switches, with
  uplinks found through LLDP and trunk members located on their trunk.
- `create_engine()`: a pysnmp engine prepared in a worker thread, to share between switches.
- `aiosnmpswitch-diagnostics`: a report without addresses or port names, and recordings for test
  fixtures.
- Tested on HPE OfficeConnect 1920S (PD.02.22) and HPE Instant On 1930 (3.4.0.0).

[Unreleased]: https://github.com/eizedev/aiosnmpswitch/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/eizedev/aiosnmpswitch/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/eizedev/aiosnmpswitch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/eizedev/aiosnmpswitch/releases/tag/v0.1.0
