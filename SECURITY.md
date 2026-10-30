# Security Policy

## Scope

This library only reads from network switches over SNMP. In scope: anything in this repository
that could leak a community or SNMPv3 keys, send a request that changes a switch, or let a
malicious switch answer harm the program using the library.

Vulnerabilities in a switch's firmware belong to its vendor.

## Reporting a vulnerability

Please report privately via GitHub's
[Report a vulnerability](https://github.com/eizedev/aiosnmpswitch/security/advisories/new)
(`Security` tab, `Advisories`, `Report a vulnerability`), not in a public issue. This opens a
private discussion until a fix is released. If you cannot use GitHub, email `oss@eize.dev`
instead.

Please include the library version, your switch model and firmware, and how to reproduce it.
Do not include communities, keys or unredacted switch output.

## Supported versions

Only the [latest release](https://github.com/eizedev/aiosnmpswitch/releases/latest) receives
fixes.

## What to expect

This is a community-maintained project without a service level. Reports are read and taken
seriously; confirmed vulnerabilities are fixed and released as soon as practical.
