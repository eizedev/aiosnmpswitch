"""Async, read-only Python client for managed network switches over SNMP."""

from __future__ import annotations

from .auth import AuthProtocol, CommunityAuth, PrivProtocol, UsmAuth
from .client import SnmpSwitch
from .errors import SnmpAuthError, SnmpError, SnmpTimeoutError
from .models import (
    AdminStatus,
    FdbEntry,
    FdbStatus,
    Interface,
    Lldp,
    LldpLocalPort,
    LldpRemote,
    MainPse,
    NeighborEntry,
    OperStatus,
    Poe,
    PseDetectionStatus,
    PseOperStatus,
    PsePort,
    StpInfo,
    StpPortState,
    SystemInfo,
)
from .transport import (
    ObjectId,
    PysnmpTransport,
    RecordedTransport,
    Transport,
    Value,
    create_engine,
)

try:
    from ._version import __version__
except ImportError:  # pragma: no cover - only in a source tree that was never built
    __version__ = "0.0.0"

__all__ = [
    "AdminStatus",
    "AuthProtocol",
    "CommunityAuth",
    "FdbEntry",
    "FdbStatus",
    "Interface",
    "Lldp",
    "LldpLocalPort",
    "LldpRemote",
    "MainPse",
    "NeighborEntry",
    "ObjectId",
    "OperStatus",
    "Poe",
    "PrivProtocol",
    "PseDetectionStatus",
    "PseOperStatus",
    "PsePort",
    "PysnmpTransport",
    "RecordedTransport",
    "SnmpAuthError",
    "SnmpError",
    "SnmpSwitch",
    "SnmpTimeoutError",
    "StpInfo",
    "StpPortState",
    "SystemInfo",
    "Transport",
    "UsmAuth",
    "Value",
    "__version__",
    "create_engine",
]
