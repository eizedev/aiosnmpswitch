"""Credentials: an SNMPv1/v2c community or an SNMPv3 user.

Both hide their secrets in ``repr()``, so they can be logged without leaking them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AuthProtocol(StrEnum):
    """SNMPv3 authentication protocol."""

    NONE = "none"
    MD5 = "md5"
    SHA = "sha"
    SHA224 = "sha224"
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"


class PrivProtocol(StrEnum):
    """SNMPv3 privacy (encryption) protocol."""

    NONE = "none"
    DES = "des"
    TRIPLE_DES = "3des"
    AES128 = "aes128"
    AES192 = "aes192"
    AES256 = "aes256"


@dataclass(frozen=True, slots=True)
class CommunityAuth:
    """SNMPv1 or v2c with a community string.

    v2c is the default: it reads 64-bit counters and walks tables in bulk.
    """

    community: str = field(repr=False)
    version: str = "2c"

    def __post_init__(self) -> None:
        """Reject versions other than 1 and 2c."""
        if self.version not in ("1", "2c"):
            raise ValueError("version must be '1' or '2c'")


@dataclass(frozen=True, slots=True)
class UsmAuth:
    """SNMPv3 user (User-based Security Model).

    Without ``auth_key`` the user is noAuthNoPriv; with ``auth_key`` only, authNoPriv; with both
    keys, authPriv. The protocols must match the switch's settings for the user.
    """

    user: str
    auth_key: str | None = field(default=None, repr=False)
    priv_key: str | None = field(default=None, repr=False)
    auth_protocol: AuthProtocol = AuthProtocol.SHA
    priv_protocol: PrivProtocol = PrivProtocol.AES128

    def __post_init__(self) -> None:
        """Reject a privacy key without an authentication key, which SNMPv3 does not allow."""
        if self.priv_key and not self.auth_key:
            raise ValueError("a privacy key needs an authentication key")

    @property
    def security_level(self) -> str:
        """``noAuthNoPriv``, ``authNoPriv`` or ``authPriv``."""
        if not self.auth_key:
            return "noAuthNoPriv"
        return "authPriv" if self.priv_key else "authNoPriv"


Auth = CommunityAuth | UsmAuth
