# Design

## Read only by construction

The transport offers `get` and `walk`, nothing else. There is no SET request anywhere in the
library, so no bug and no caller can change a switch through it.

## Standard MIBs, mirrored

Each getter reads one MIB group, and each model mirrors its table: field names are the MIB
objects in snake_case without the table prefix, units are the MIB's. Interpretation that combines
tables or switches (trunks, uplinks, device locations) lives in `helpers`, so a reader can always
see what the switch said and what was derived.

## Targeted reads

Getters walk whole tables in one GETBULK sequence each (GETNEXT on SNMPv1), with MIB lookups off,
so requests do not resolve names. The engine loads pysnmp's MIB modules once, in
`create_engine()`, outside the event loop. Only the standard subtrees are read; vendor trees can
be huge. The one exception is a vendor table for something the standard MIB lacks on a model,
measured on that model and read only there, by `sysObjectID` and by column: the temperature
sensors of the HPE Instant On 1930 (`get_temperatures()`).

## Parsers never raise

Values of the wrong type or with unexpected indexes become `None` or are skipped. Property-based
tests feed random answers to every getter and helper.

## Privacy

Test data are recordings of real switches, anonymized by an allowlist script: MAC addresses
become locally administered `02:00:00:00:xx:xx`, IP addresses documentation addresses, names and
descriptions placeholders. A test fails on any address that may be real, in the files and in
unpublished commits.
