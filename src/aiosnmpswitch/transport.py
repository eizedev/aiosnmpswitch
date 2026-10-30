"""How requests reach a switch: a small protocol and its pysnmp implementation.

The client only needs ``get`` and ``walk``. Values come back as plain Python: ``int`` for numbers,
``bytes`` for strings and addresses, :class:`ObjectId` for OIDs. Tests and recordings use the
same interface (:class:`RecordedTransport`), so nothing above this module knows pysnmp.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from .auth import Auth, AuthProtocol, CommunityAuth, PrivProtocol, UsmAuth
from .errors import SnmpAuthError, SnmpError, SnmpTimeoutError


class ObjectId(str):
    """An OID value (for example ``sysObjectID``), dotted and without a leading dot."""

    __slots__ = ()


Value = int | bytes | ObjectId
"""A value read from a switch."""


class Transport(Protocol):
    """Reads values from one switch."""

    async def get(self, oids: Sequence[str]) -> dict[str, Value]:
        """Read single OIDs; OIDs the switch does not have are left out."""

    async def walk(self, oid: str) -> list[tuple[str, Value]]:
        """Read every OID below ``oid`` in order; an empty list if the switch has none."""

    async def close(self) -> None:
        """Release the transport's resources."""


class RecordedTransport:
    """Answers from a recording: a mapping of OID to value, as written by the diagnostics."""

    def __init__(self, values: Mapping[str, Value]) -> None:
        """Keep the values sorted the way a switch walks them."""
        self._values = dict(sorted(values.items(), key=lambda item: oid_key(item[0])))

    async def get(self, oids: Sequence[str]) -> dict[str, Value]:
        """Return the recorded values of ``oids``."""
        return {oid: self._values[oid] for oid in oids if oid in self._values}

    async def walk(self, oid: str) -> list[tuple[str, Value]]:
        """Return the recorded values below ``oid``."""
        prefix = oid + "."
        return [(key, value) for key, value in self._values.items() if key.startswith(prefix)]

    async def close(self) -> None:
        """Nothing to release."""


def oid_key(oid: str) -> tuple[int, ...]:
    """Sort key of a dotted OID, numerically by component."""
    return tuple(int(part) for part in oid.split("."))


# pysnmp error indications that mean the credentials are wrong rather than the switch unreachable.
_AUTH_ERRORS = frozenset(
    {
        "AuthenticationError",
        "AuthenticationFailure",
        "DecryptionError",
        "UnknownSecurityName",
        "UnknownUserName",
        "UnsupportedAuthProtocol",
        "UnsupportedPrivProtocol",
        "UnsupportedSecurityLevel",
        "WrongDigest",
    }
)


# A walk stops with an error after this many rows: a broken or hostile agent could otherwise
# send rows until memory runs out. The largest standard table read here has a few thousand.
MAX_WALK_ROWS = 100_000
_HLAPI = "pysnmp.hlapi.v3arch.asyncio"


class PysnmpTransport:
    """Reads a switch over UDP with pysnmp (asyncio).

    Create it with :meth:`create`, which also sets up the pysnmp engine outside the event loop
    (pysnmp reads files when it starts). Several transports may share one engine.
    """

    def __init__(
        self,
        engine: Any,
        auth_data: Any,
        target: Any,
        max_repetitions: int = 25,
        owns_engine: bool = False,
    ) -> None:
        """Use :meth:`create` instead; this takes pysnmp objects."""
        self._engine = engine
        self._auth = auth_data
        self._target = target
        self._max_repetitions = max_repetitions
        self._owns_engine = owns_engine

    @classmethod
    async def create(  # noqa: PLR0917 - the documented connection options
        cls,
        host: str,
        auth: Auth,
        port: int = 161,
        timeout: float = 5.0,  # noqa: ASYNC109 - the SNMP request timeout, per try
        retries: int = 1,
        max_repetitions: int = 25,
        engine: Any = None,
    ) -> PysnmpTransport:
        """Prepare requests to ``host``; nothing is sent yet.

        ``engine`` is a shared ``pysnmp`` ``SnmpEngine``; without one, the transport creates its
        own and closes it in :meth:`close`. An IPv6 address uses UDP over IPv6.
        """
        # pysnmp loads many modules on first use: import it in a worker thread, not in the loop.
        hlapi = await asyncio.to_thread(importlib.import_module, _HLAPI)
        owns_engine = engine is None
        if owns_engine:
            engine = await asyncio.to_thread(hlapi.SnmpEngine)
        target_class = hlapi.Udp6TransportTarget if ":" in host else hlapi.UdpTransportTarget
        try:
            target = await target_class.create((host, port), timeout=timeout, retries=retries)
        except Exception as err:
            if owns_engine:
                engine.close_dispatcher()
            raise SnmpError(f"cannot resolve the switch address: {type(err).__name__}") from err
        return cls(engine, _auth_data(auth), target, max_repetitions, owns_engine)

    async def get(self, oids: Sequence[str]) -> dict[str, Value]:
        """Read single OIDs in one request.

        SNMPv1 fails a whole request with ``noSuchName`` when one OID is missing; then each OID
        is read on its own and the missing ones are left out, as v2c and v3 do.
        """
        error, status, index, var_binds = await self._get(oids)
        if len(oids) > 1 and _no_such_name(error, status):
            values: dict[str, Value] = {}
            for oid in oids:
                values.update(await self.get([oid]))
            return values
        if _no_such_name(error, status):
            return {}
        _raise_for(error, status, index)
        return dict(_converted(var_binds))

    async def _get(self, oids: Sequence[str]) -> Any:
        hlapi = importlib.import_module(_HLAPI)  # loaded by create(); a dictionary lookup
        return await hlapi.get_cmd(
            self._engine,
            self._auth,
            self._target,
            hlapi.ContextData(),
            *(hlapi.ObjectType(hlapi.ObjectIdentity(oid)) for oid in oids),
            lookupMib=False,
        )

    async def walk(self, oid: str) -> list[tuple[str, Value]]:
        """Read every OID below ``oid`` with GETBULK (GETNEXT on SNMPv1).

        More than :data:`MAX_WALK_ROWS` rows raise :class:`SnmpError`.
        """
        hlapi = importlib.import_module(_HLAPI)

        rows: list[tuple[str, Value]] = []
        walk_options: dict[str, Any] = {"lexicographicMode": False, "lookupMib": False}
        start = hlapi.ObjectType(hlapi.ObjectIdentity(oid))
        context = hlapi.ContextData()
        if self._auth.message_processing_model == 0:  # SNMPv1 has no GETBULK
            replies = hlapi.walk_cmd(
                self._engine, self._auth, self._target, context, start, **walk_options
            )
        else:
            replies = hlapi.bulk_walk_cmd(
                self._engine,
                self._auth,
                self._target,
                context,
                0,
                self._max_repetitions,
                start,
                **walk_options,
            )
        async for error, status, index, var_binds in replies:
            if _no_such_name(error, status):  # SNMPv1: past the last OID
                break
            _raise_for(error, status, index)
            rows.extend(_converted(var_binds))
            if len(rows) > MAX_WALK_ROWS:
                raise SnmpError(f"more than {MAX_WALK_ROWS} rows below {oid}")
        return rows

    async def close(self) -> None:
        """Close the engine if the transport created it."""
        if self._owns_engine:
            self._engine.close_dispatcher()


def _auth_data(auth: Auth) -> Any:
    """Turn credentials into pysnmp's ``CommunityData`` or ``UsmUserData``."""
    hlapi = importlib.import_module(_HLAPI)

    if isinstance(auth, CommunityAuth):
        return hlapi.CommunityData(auth.community, mpModel=0 if auth.version == "1" else 1)
    return _usm_data(hlapi, auth)


def _usm_data(hlapi: Any, auth: UsmAuth) -> Any:
    """``UsmUserData`` for an SNMPv3 user at its security level."""
    auth_protocols = {
        AuthProtocol.NONE: hlapi.USM_AUTH_NONE,
        AuthProtocol.MD5: hlapi.USM_AUTH_HMAC96_MD5,
        AuthProtocol.SHA: hlapi.USM_AUTH_HMAC96_SHA,
        AuthProtocol.SHA224: hlapi.USM_AUTH_HMAC128_SHA224,
        AuthProtocol.SHA256: hlapi.USM_AUTH_HMAC192_SHA256,
        AuthProtocol.SHA384: hlapi.USM_AUTH_HMAC256_SHA384,
        AuthProtocol.SHA512: hlapi.USM_AUTH_HMAC384_SHA512,
    }
    priv_protocols = {
        PrivProtocol.NONE: hlapi.USM_PRIV_NONE,
        PrivProtocol.DES: hlapi.USM_PRIV_CBC56_DES,
        PrivProtocol.TRIPLE_DES: hlapi.USM_PRIV_CBC168_3DES,
        PrivProtocol.AES128: hlapi.USM_PRIV_CFB128_AES,
        PrivProtocol.AES192: hlapi.USM_PRIV_CFB192_AES,
        PrivProtocol.AES256: hlapi.USM_PRIV_CFB256_AES,
    }
    if not auth.auth_key:
        return hlapi.UsmUserData(auth.user)
    if not auth.priv_key:
        return hlapi.UsmUserData(
            auth.user, auth.auth_key, authProtocol=auth_protocols[auth.auth_protocol]
        )
    return hlapi.UsmUserData(
        auth.user,
        auth.auth_key,
        auth.priv_key,
        authProtocol=auth_protocols[auth.auth_protocol],
        privProtocol=priv_protocols[auth.priv_protocol],
    )


def _no_such_name(error: Any, status: Any) -> bool:
    """SNMPv1's answer for an OID it does not have, and for a walk past the last OID."""
    return not error and bool(status) and str(status.prettyPrint()) == "noSuchName"


def _raise_for(error: Any, status: Any, index: Any) -> None:
    """Map pysnmp's error indication or error status to our exceptions."""
    if error:
        name = type(error).__name__
        if name == "RequestTimedOut":
            raise SnmpTimeoutError("no answer from the switch")
        if name in _AUTH_ERRORS:
            raise SnmpAuthError(f"the switch rejected the SNMPv3 credentials ({name})")
        raise SnmpError(f"SNMP request failed ({name})")
    if status:
        raise SnmpError(f"the switch answered with an error ({status.prettyPrint()} at {index})")


def _converted(var_binds: Iterable[Any]) -> Iterable[tuple[str, Value]]:
    """Plain values of pysnmp variable bindings; missing objects are skipped."""
    for name, value in var_binds:
        converted = convert(value)
        if converted is not None:
            yield str(name), converted


def convert(value: Any) -> Value | None:
    """Convert a pysnmp value to ``int``, ``bytes`` or :class:`ObjectId`; ``None`` for none.

    ``NoSuchObject``, ``NoSuchInstance``, ``EndOfMibView`` and ``Null`` carry no value.
    """
    kind = type(value).__name__
    if kind in ("NoSuchObject", "NoSuchInstance", "EndOfMibView", "Null"):
        return None
    if kind in ("ObjectIdentifier", "ObjectName"):
        return ObjectId(str(value))
    if kind in ("OctetString", "IpAddress", "Opaque", "Bits"):
        return bytes(value.asOctets())
    return int(value)
