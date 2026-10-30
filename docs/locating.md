# Locating devices

A switch learns the MAC address of every device whose traffic passes it, together with the port
it came in on. In a network of several switches, a device therefore appears on its own port of
the switch it is plugged into, and on the uplink port of every switch between that one and the
others.

`helpers.locate_macs()` takes the reads of all your switches and returns, for every device, the
one port that is not an uplink:

```python
from aiosnmpswitch.helpers import SwitchData, locate_macs

switches = {
    "hallway": SwitchData(interfaces=..., bridge_ports=..., fdb=..., lldp=..., lag_ports=...),
    "living-room": SwitchData(...),
}
for mac, where in locate_macs(switches).items():
    print(mac, where.switch, where.port_name, where.devices_on_port, where.ip_addresses)
```

How it decides:

1. **Uplinks** are ports on which LLDP sees another of the given switches, recognised by its
   chassis ID or one of its interface MAC addresses. A switch that is not in the mapping (an
   unmanaged switch, a switch without SNMP) counts as a device: everything behind it is located
   on the port it hangs on.
2. Address-table entries on uplinks are ignored, as are the switches' own addresses and entries
   that are not learned (the switch itself, management).
3. Trunk members are located on their trunk.
4. If a device is still seen on more than one port, the port with the fewest devices wins.
5. A device seen only on uplinks (its entry aged out on the edge switch) is left out rather than
   placed wrongly.

`devices_on_port` greater than one means something is between the port and the device: an access
point with its Wi-Fi clients, a router, a hub or an unmanaged switch. `ip_addresses` come from
the switches' own neighbour caches, which usually know only a few devices; take addresses from
your router or DHCP server instead.

Address tables age out after about five minutes of silence (the switch's setting), so a device
that sends nothing for a while disappears until it talks again.
