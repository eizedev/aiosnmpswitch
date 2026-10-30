# What it can read

One getter per MIB group. Each returns frozen dataclasses whose fields are named after the MIB
objects (``ifHighSpeed`` → `Interface.high_speed`) and keep the MIB's units. A field is `None`
when the switch does not have the object; a getter returns an empty result when the switch lacks
the whole MIB.

| Getter | MIB | Returns |
| --- | --- | --- |
| `get_system()` | SNMPv2-MIB | `SystemInfo`: description (model, firmware), object ID, uptime, name, contact, location |
| `get_interfaces()` | IF-MIB `ifTable`, `ifXTable` | `Interface` by `ifIndex`: name, alias, type, status, speed, MAC address, 32- and 64-bit counters, errors, discards |
| `get_bridge_ports()` | BRIDGE-MIB | `ifIndex` by bridge port number |
| `get_fdb()` | Q-BRIDGE-MIB, else BRIDGE-MIB | `FdbEntry` list: MAC address, VLAN, bridge port, status (learned, self, management) |
| `get_stp()` | BRIDGE-MIB | `StpInfo`: topology changes, root bridge, root port, port states; `None` without spanning tree |
| `get_lldp()` | LLDP-MIB | `Lldp`: own chassis and ports, neighbours with name, description, port, capabilities and management addresses |
| `get_lag_ports()` | IEEE8023-LAG-MIB | aggregator `ifIndex` by member `ifIndex` (raw; see `helpers.lag_members`) |
| `get_poe()` | POWER-ETHERNET-MIB | `Poe`: supplies (budget, consumption, status) and ports (enabled, detection status, class) |
| `get_neighbors()` | IP-MIB | `NeighborEntry` list: the switch's own ARP and IPv6 neighbour cache |

Units worth knowing:

- `Interface.high_speed` is Mbit/s, `Interface.speed` bit/s. Some switches report 0 for a port
  without link, others the port's nominal speed.
- `SystemInfo.up_time`, `Interface.last_change` and `StpInfo.time_since_topology_change` are in
  hundredths of a second.
- `MainPse.power` and `consumption_power` are watts. Per-port power is not in the standard MIB.

## Helpers

`aiosnmpswitch.helpers` interprets the reads; nothing there talks to a switch.

| Helper | What it does |
| --- | --- |
| `port_name(interface)` | the name a person knows the port by |
| `is_ethernet_port(interface)` | physical Ethernet port, not VLAN, CPU or trunk |
| `lag_members(lag_ports, interfaces)` | aggregator by member, for ports in a trunk |
| `lag_interfaces(data)` | the trunks |
| `lldp_port_if_index(lldp, port_num, interfaces)` | maps LLDP's local port number to the `ifIndex` |
| `neighbors_by_port(data)` | LLDP neighbours by port, trunk members on their trunk |
| `uplink_ports(switches)` | ports that lead to another of your switches |
| `locate_macs(switches)` | the port every device is connected to: [Locating devices](locating.md) |
