# Compatibility

| Switch | Firmware | Status |
| --- | --- | --- |
| HPE OfficeConnect 1920S 8G PPoE+ (JL383A) | PD.02.22 | ✅ tested |
| HPE Networking Instant On 1930 8p (JL680A) | 3.4.0.0 | ✅ tested |
| Other managed switches with the standard MIBs | | 🟡 expected to work |

## What each tested switch answers

| | 1920S | 1930 |
| --- | --- | --- |
| Interfaces, 64-bit counters | yes | yes (physical ports and trunks) |
| Address table | Q-BRIDGE-MIB | Q-BRIDGE-MIB and BRIDGE-MIB |
| LLDP | yes, port ID is the switch MAC address | yes, port ID is the port name |
| Trunks | LAG-MIB; trunks are typed `other` | LAG-MIB; trunks typed `ieee8023adLag` |
| PoE | supplies and port status, no watts per port | no PoE |
| Neighbour cache | none | IPv6 in `ipNetToPhysicalTable`, IPv4 in `ipNetToMediaTable` |
| SNMPv3 | engine present | engine present, engine ID `0000000001` |

## Quirks the library handles

- **HPE 1920S** sends LLDP capabilities with the two octets swapped; they are read the other way
  round when the first octet is empty.
- **HPE 1920S** uses one MAC address as LLDP port ID for all ports, so the LLDP port number is
  taken as the `ifIndex`.
- **HPE Instant On 1930** attaches a port in no trunk to itself in `dot3adAggPortAttachedAggID`
  instead of 0.
- **HPE Instant On 1930** has no ENTITY-SENSOR-MIB table; its two temperature sensors (`PP`,
  `PHY`) are in a vendor table with the same columns (`1.3.6.1.4.1.11.2.83.2.1.1.1`, names in
  `.83.3.1.4`). Its precision column says one decimal place, but the value is whole degrees
  (54 means 54 °C), so `get_temperatures()` ignores it there. The HPE 1920S has no temperature
  sensor in SNMP.
- **HPE Instant On 1930**: a full SNMP walk takes more than ten minutes (over 300,000 vendor
  entries); the library walks only the standard tables it needs (about 1.5 seconds).

## Reporting your switch

Open a [Model or firmware report](https://github.com/eizedev/aiosnmpswitch/issues/new/choose)
with the output of [`aiosnmpswitch-diagnostics`](diagnostics.md).
