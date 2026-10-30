---
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

<p class="hero-kicker">Python · asyncio · SNMP · read only</p>

# aiosnmpswitch

<p class="hero-lead">Reads what your <strong>managed network switches</strong> know: ports, PoE, the MAC address table, LLDP neighbours, trunks and spanning tree, and works out which device is connected to which port. Over SNMP, without changing a setting.</p>

<p class="hero-install"><code>pip install aiosnmpswitch</code></p>

[Get started](getting-started.md){ .md-button .md-button--primary }
[Source on GitHub](https://github.com/eizedev/aiosnmpswitch){ .md-button }

</div>

<div class="cards" markdown>

- [**Getting started**](getting-started.md)<br>Install, SNMPv3 or v2c, first read.
- [**What it can read**](reading.md)<br>Every getter, one per MIB group, and the helpers.
- [**Locating devices**](locating.md)<br>Which device is on which port, across switches.
- [**Errors**](errors.md)<br>Timeouts, rejected credentials, missing MIBs.
- [**Diagnostics**](diagnostics.md)<br>A report for an issue, without personal data.
- [**Compatibility**](compatibility.md)<br>Tested switches and vendor quirks.
- [**Design**](design.md)<br>Standard MIBs, read only, privacy.

</div>

## Why this library?

Home Assistant's built-in SNMP integration reads one OID per entity from YAML. This library
starts from the standard MIBs every managed switch implements:

| | aiosnmpswitch |
| --- | --- |
| **Async** | pysnmp 7 (also used by Home Assistant's SNMP integration); pysnmp is loaded, its MIB files read and its engine created in a worker thread, not in the event loop |
| **Read only** | only GET, GETNEXT and GETBULK; there is no code path that sets a value |
| **Vendor-neutral** | IF-MIB, BRIDGE-MIB, Q-BRIDGE-MIB, LLDP-MIB, IEEE8023-LAG-MIB, POWER-ETHERNET-MIB, IP-MIB, ENTITY-MIB, ENTITY-SENSOR-MIB; vendor quirks handled where they were measured |
| **Device locations** | combines the address tables and LLDP of all your switches: a device is on the port that is not an uplink |
| **Targeted reads** | walks only the tables it needs; a full walk of some switches takes minutes |
| **Typed and tested** | strict typing, 100 % test coverage against anonymized recordings of real switches |

> Not affiliated with any switch vendor. Product names are trademarks of their owners.
