# Errors

All exceptions derive from `SnmpError`. Messages never contain a community or a key.

| Exception | When | What to do |
| --- | --- | --- |
| `SnmpTimeoutError` | no answer in time: wrong address, SNMP off, a filter, or (v1/v2c) a wrong community, because switches stay silent then | retry later; check address and community |
| `SnmpAuthError` | the switch rejected the SNMPv3 user, its keys, protocols or security level | ask for new credentials, do not retry in a loop |
| `SnmpError` | anything else: the switch answered with an error status, the address cannot be resolved | log it; retry later |

SNMPv1 answers a request with an error when one of its objects is missing; the library then
reads each object on its own, so a missing object is left out as with v2c and v3.

A missing MIB is not an error: the getter returns an empty result, or `None` for
`get_stp()`. Values of the wrong type become `None` in the models; parsing never raises.
