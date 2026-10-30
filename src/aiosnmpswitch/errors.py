"""Exceptions raised by aiosnmpswitch.

Messages never contain a community, a password or a key.
"""

from __future__ import annotations


class SnmpError(Exception):
    """Base class: the switch did not answer as expected."""


class SnmpTimeoutError(SnmpError):
    """The switch did not answer in time (wrong address, SNMP off, or a filtered port).

    SNMPv1 and v2c switches also stay silent when the community is wrong, so a wrong community
    shows up as a timeout, not as an authentication error.
    """


class SnmpAuthError(SnmpError):
    """The switch rejected the SNMPv3 user, its keys or its security level."""
