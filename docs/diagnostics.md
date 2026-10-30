# Diagnostics

The package installs a command that describes what a switch answers, without any of its values:

```sh
aiosnmpswitch-diagnostics 192.0.2.10                       # SNMPv2c, asks for the community
aiosnmpswitch-diagnostics 192.0.2.10 --user monitor \
    --auth-protocol sha --priv-protocol des                 # SNMPv3, asks for the keys
```

Secrets are never taken from the command line; set `SNMP_COMMUNITY`, `SNMP_AUTH_KEY` and
`SNMP_PRIV_KEY` or type them when asked. The output names the model and firmware and counts what
each MIB returns, for example:

```text
model: HPE OfficeConnect Switch 1920S 8G PPoE+ (65W) JL383A, PD.02.22, ...
sysObjectID: 1.3.6.1.4.1.11.2.3.7.11.186
chassis (ENTITY-MIB): HPE OfficeConnect Switch 1920S 8G PPoE+ (65W) JL383A, model hpe1920S_8G_PPoE+, software PD.02.22
interfaces: 13 by ifType {1: 5, 6: 8}
address table: 39 entries, with VLAN (Q-BRIDGE-MIB)
LLDP: chassis ID subtype 4, local ports 8, port ID subtypes [3], neighbours 2 on 2 mapped ports
trunks: 2 with members, LAG-MIB rows 8
PoE: 1 supplies, 4 ports
```

It contains no MAC or IP addresses, port names or descriptions. The `model` and `chassis` lines
are the switch's `sysDescr` and its ENTITY-MIB chassis entry as they are: model and firmware on most switches, but some (Linux-based ones in
particular) put their host name or a serial number there. Read the output, then paste it into an
issue.

## Recordings for tests

`--record switch.raw.json` writes every value the library reads into a new file that only you
can read (the name must end in `.raw.json`, an existing file is not overwritten). It contains
your addresses and names: never share it as it is. Maintainers turn recordings into test fixtures with
`scripts/anonymize.py` (see CONTRIBUTING.md).
