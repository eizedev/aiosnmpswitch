# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/eizedev/aiosnmpswitch/commits/main
