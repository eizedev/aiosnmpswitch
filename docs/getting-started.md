# Getting started

## Install

```sh
pip install aiosnmpswitch
```

Python 3.12 or newer. The package depends on [pysnmp](https://github.com/lextudio/pysnmp) 7 and
`cryptography` (for SNMPv3 encryption).

## Give the library read access

Create a **read-only** SNMP access on the switch. SNMPv3 is preferred: it authenticates every
request and encrypts the answers. SNMPv1 and v2c send the community in clear text, and anyone who
knows it can read the switch.

- **SNMPv3:** a user in a group with a read view (for example the whole tree `1.3.6.1` plus
  `1.0.8802` for LLDP and `1.2.840` for trunks), no write view, security level authPriv.
  Use the strongest protocols the switch offers; some older switches offer only SHA (SHA-1)
  and DES.
- **SNMPv2c:** a community that is not the default `public`, limited to the address of the
  program that reads it, if the switch can do that.

## First read

```python
import asyncio

from aiosnmpswitch import AuthProtocol, CommunityAuth, PrivProtocol, SnmpSwitch, UsmAuth


async def main() -> None:
    auth = UsmAuth("monitor", "auth-key", "priv-key", AuthProtocol.SHA, PrivProtocol.DES)
    # or: auth = CommunityAuth("my-community")
    async with await SnmpSwitch.connect("192.0.2.10", auth, timeout=5.0, retries=1) as switch:
        system = await switch.get_system()
        print(system.name, system.descr, system.up_time)


asyncio.run(main())
```

`SnmpSwitch.connect()` takes these options:

| Option | Default | Meaning |
| --- | --- | --- |
| `port` | 161 | UDP port of the SNMP agent |
| `timeout` | 5.0 | seconds per try |
| `retries` | 1 | tries after the first |
| `max_repetitions` | 25 | rows per GETBULK request; lower it for switches that answer "tooBig" |
| `engine` | own | a shared pysnmp `SnmpEngine`, for programs that read many switches |

An IPv6 address uses UDP over IPv6. pysnmp imports many modules and reads its MIB files on first
use, so `create_engine()` does both in a worker thread; the transport calls it when it gets no
engine. Programs with many switches can create one engine and pass it to every switch:

```python
from aiosnmpswitch import create_engine

engine = await create_engine()
switch = await SnmpSwitch.connect("192.0.2.10", auth, engine=engine)
```

Do not share one engine between switches that use the same SNMPv3 user name with different
passwords: pysnmp keeps the user in the engine by name, so the switches replace each other's
keys. Create one engine per set of credentials.

## Credentials in your program

`CommunityAuth` and `UsmAuth` never show their secrets in `repr()`, and no error message contains
them. Keep them out of command lines; the diagnostics command reads them from the environment or
asks for them.
