# aiosnmpswitch

<!-- === Badges: Release & distribution === -->

| PyPI | Python | Release Date | Downloads |
| ---- | ------ | ------------ | --------- |
| [![PyPI](https://img.shields.io/pypi/v/aiosnmpswitch?cacheSeconds=3600)](https://pypi.org/project/aiosnmpswitch/) | [![Python versions](https://img.shields.io/pypi/pyversions/aiosnmpswitch?cacheSeconds=3600)](https://pypi.org/project/aiosnmpswitch/) | [![GitHub release date](https://img.shields.io/github/release-date/eizedev/aiosnmpswitch?cacheSeconds=3600)](https://github.com/eizedev/aiosnmpswitch/releases/latest) | [![PyPI downloads](https://img.shields.io/pypi/dm/aiosnmpswitch?cacheSeconds=3600)](https://pypistats.org/packages/aiosnmpswitch) |

<!-- === Badges: Quality & community === -->

| CI | License | Typed | Issues | Discussions |
| -- | ------- | ----- | ------ | ----------- |
| [![CI](https://github.com/eizedev/aiosnmpswitch/actions/workflows/ci.yml/badge.svg)](https://github.com/eizedev/aiosnmpswitch/actions/workflows/ci.yml) | [![License](https://img.shields.io/github/license/eizedev/aiosnmpswitch.svg?cacheSeconds=3600)](https://github.com/eizedev/aiosnmpswitch/blob/main/LICENSE) | [![Checked with mypy](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/) | [![GitHub issues](https://img.shields.io/github/issues-raw/eizedev/aiosnmpswitch?cacheSeconds=3600)](https://github.com/eizedev/aiosnmpswitch/issues) | [![GitHub discussions](https://img.shields.io/badge/Discussions-ask%20and%20share-lightgrey)](https://github.com/eizedev/aiosnmpswitch/discussions) |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/eizedev/aiosnmpswitch/main/assets/header-dark.svg">
  <img alt="aiosnmpswitch" src="https://raw.githubusercontent.com/eizedev/aiosnmpswitch/main/assets/header-light.svg" height="72">
</picture>

A Python library that reads what your **managed network switches** know over SNMP: ports with
link, speed and traffic, PoE, the MAC address table, LLDP neighbours, trunks and spanning tree.
Across several switches it works out **which device is connected to which port**. It only reads
and never changes a setting.

It uses standard MIBs only, so it is vendor-neutral; HPE OfficeConnect 1920S and HPE Instant On
1930 are the tested references. It is built as a foundation for Home Assistant, but works in any
asyncio program.

**Documentation: [aiosnmpswitch.eize.dev](https://aiosnmpswitch.eize.dev/)**

## Which switches work?

| | |
| --- | --- |
| ✅ **Tested** | HPE OfficeConnect 1920S (JL383A, PD.02.22), HPE Instant On 1930 (JL680A, 3.4.0.0) |
| 🟡 **Expected to work** | Managed switches with SNMP and the standard MIBs (IF-MIB, Q-BRIDGE-MIB, LLDP-MIB) |
| ❔ **Partly** | Switches without LLDP or Q-BRIDGE-MIB: fewer details, no uplink detection |
| ❌ **Not in scope** | Unmanaged and "smart" switches without SNMP, changing settings |

Each getter returns an empty result when the switch lacks its MIB. How to report your model:
[Compatibility](https://aiosnmpswitch.eize.dev/compatibility/).

## Quick start

You need Python 3.12 or newer and SNMP read access to the switch: SNMPv3 (recommended) or a
v2c community.

```sh
pip install aiosnmpswitch
```

```python
import asyncio

from aiosnmpswitch import AuthProtocol, PrivProtocol, SnmpSwitch, UsmAuth
from aiosnmpswitch.helpers import SwitchData, locate_macs


async def main() -> None:
    auth = UsmAuth("monitor", "auth-key", "priv-key", AuthProtocol.SHA, PrivProtocol.AES128)
    async with await SnmpSwitch.connect("192.0.2.10", auth) as switch:
        system = await switch.get_system()
        print(system.name, system.descr)
        interfaces = await switch.get_interfaces()
        for port in interfaces.values():
            print(port.name, port.oper_status, port.high_speed, port.alias)

        data = SwitchData(
            interfaces=interfaces,
            bridge_ports=await switch.get_bridge_ports(),
            fdb=await switch.get_fdb(),
            lldp=await switch.get_lldp(),
            lag_ports=await switch.get_lag_ports(),
        )
        for mac, where in locate_macs({"core": data}).items():
            print(mac, "on port", where.port_name)


asyncio.run(main())
```

## Documentation

- [Getting started](https://aiosnmpswitch.eize.dev/getting-started/): install, SNMPv3 or v2c, first read
- [What it can read](https://aiosnmpswitch.eize.dev/reading/): every getter, one per MIB group, and the helpers
- [Locating devices](https://aiosnmpswitch.eize.dev/locating/): which device is on which port, across switches
- [Errors](https://aiosnmpswitch.eize.dev/errors/) and [Diagnostics](https://aiosnmpswitch.eize.dev/diagnostics/): a report to attach to an issue, without personal data
- [Compatibility](https://aiosnmpswitch.eize.dev/compatibility/) and [Design](https://aiosnmpswitch.eize.dev/design/)

## Roadmap

Planned work is grouped in [milestones](https://github.com/eizedev/aiosnmpswitch/milestones).

## Contributing

Reports with your switch model and firmware help most. See [CONTRIBUTING.md](https://github.com/eizedev/aiosnmpswitch/blob/main/CONTRIBUTING.md);
for security issues [SECURITY.md](https://github.com/eizedev/aiosnmpswitch/blob/main/SECURITY.md).

## License

[MIT](https://github.com/eizedev/aiosnmpswitch/blob/main/LICENSE). Provided "as is", without warranty of any kind. The icon and header images are
CC BY 4.0; their source is in [eizedev/brand](https://github.com/eizedev/brand).
