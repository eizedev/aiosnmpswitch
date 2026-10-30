"""Credentials validate their combinations and never show secrets."""

from __future__ import annotations

import pytest

from aiosnmpswitch import AuthProtocol, CommunityAuth, PrivProtocol, UsmAuth


def test_community() -> None:
    auth = CommunityAuth("secret-community")
    assert auth.version == "2c"
    assert "secret-community" not in repr(auth)
    assert CommunityAuth("c", version="1").version == "1"
    with pytest.raises(ValueError, match="version"):
        CommunityAuth("c", version="3")


def test_usm_levels_and_repr() -> None:
    assert UsmAuth("u").security_level == "noAuthNoPriv"
    assert UsmAuth("u", "auth-secret").security_level == "authNoPriv"
    full = UsmAuth("u", "auth-secret", "priv-secret", AuthProtocol.SHA, PrivProtocol.DES)
    assert full.security_level == "authPriv"
    assert "secret" not in repr(full)
    with pytest.raises(ValueError, match="authentication key"):
        UsmAuth("u", priv_key="priv-secret")
