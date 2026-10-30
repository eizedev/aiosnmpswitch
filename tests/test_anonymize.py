"""The anonymizer: replaced values, consistent across files, and refusing what it cannot judge.

The input here is made up but must look real to test the anonymizer (test_privacy.py skips it).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("anonymize", ROOT / "scripts/anonymize.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["anonymize"] = module
    spec.loader.exec_module(module)
    return module


anon = _load()
REAL_MAC = "0011320000aa"  # a vendor prefix on purpose: real-looking
OTHER_MAC = "0011320000bb"


def text(value: str) -> dict[str, str]:
    return {"hex": value.encode().hex()}


def recording(**values: Any) -> dict[str, Any]:
    return {"format": 1, "values": values}


def write(tmp_path: Path, name: str, data: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_replaces_addresses_names_and_indexes(tmp_path: Path) -> None:
    raw = recording(
        **{
            "1.3.6.1.2.1.1.1.0": text("Switch 8p, 1.2.3"),
            "1.3.6.1.2.1.1.5.0": text("office-switch"),
            "1.3.6.1.2.1.1.6.0": text("Kitchen"),
            "1.3.6.1.2.1.1.4.0": text("Jane"),
            "1.3.6.1.2.1.2.2.1.6.1": {"hex": REAL_MAC},
            "1.3.6.1.2.1.31.1.1.1.18.1": text("TV living room"),
            "1.3.6.1.2.1.17.7.1.2.2.1.2.1.0.17.50.0.0.170": 1,
            "1.3.6.1.2.1.4.22.1.2.5.10.1.2.3": {"hex": OTHER_MAC},
            "1.3.6.1.2.1.4.35.1.4.5.4.20.254.128.0.0.0.0.0.0.0.0.0.0.0.0.0.9.0.0.0.1": {
                "hex": OTHER_MAC
            },
            "1.0.8802.1.1.2.1.4.2.1.3.0.1.1.1.4.10.1.2.3": 2,
            "1.0.8802.1.1.2.1.4.1.1.7.0.1.1": text("serial123456"),
            "1.0.8802.1.1.2.1.4.1.1.10.0.1.1": text("Linux nas 6.1"),
            "1.3.6.1.2.1.17.2.5.0": {"hex": "8000" + REAL_MAC},
            "1.0.8802.1.1.2.1.4.2.1.5.0.1.1.1.4.10.1.2.3": {"oid": "1.3.6.1.4.1.9.9"},
            "1.3.6.1.2.1.2.2.1.8.1": 1,
        }
    )
    out = tmp_path / "out.json"
    assert anon.main([str(write(tmp_path, "a.raw.json", raw)), str(out)]) == 0
    result = out.read_text(encoding="utf-8")
    for original in ("office-switch", "Kitchen", "Jane", "TV living room", "serial123456", "nas"):
        assert original.encode().hex() not in result
    assert REAL_MAC not in result
    assert ".0.17.50.0.0.170" not in result
    assert "10.1.2.3" not in result
    values = json.loads(result)["values"]
    assert values["1.3.6.1.2.1.2.2.1.6.1"] == {"hex": "020000000001"}
    assert values["1.3.6.1.2.1.17.2.5.0"] == {"hex": "8000020000000001"}  # the same fake MAC
    assert "1.3.6.1.2.1.4.22.1.2.5.192.0.2.1" in values
    assert any(".254.128." in oid and ".0.9." not in oid for oid in values)  # link-local kept
    assert values["1.3.6.1.2.1.2.2.1.8.1"] == 1
    assert values["1.3.6.1.2.1.1.1.0"] == text("Switch 8p, 1.2.3")


def test_same_device_same_fake_across_files(tmp_path: Path) -> None:
    descr = text("Model X")
    a = recording(**{"1.3.6.1.2.1.1.1.0": descr, "1.0.8802.1.1.2.1.3.2.0": {"hex": REAL_MAC}})
    b = recording(
        **{
            "1.0.8802.1.1.2.1.4.1.1.5.0.1.1": {"hex": REAL_MAC},
            "1.0.8802.1.1.2.1.4.1.1.10.0.1.1": descr,  # the other switch's description: kept
        }
    )
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    args = [str(write(tmp_path, "a.raw.json", a)), str(out_a)]
    args += [str(write(tmp_path, "b.raw.json", b)), str(out_b)]
    assert anon.main(args) == 0
    fake_a = json.loads(out_a.read_text())["values"]["1.0.8802.1.1.2.1.3.2.0"]
    values_b = json.loads(out_b.read_text())["values"]
    assert values_b["1.0.8802.1.1.2.1.4.1.1.5.0.1.1"] == fake_a
    assert values_b["1.0.8802.1.1.2.1.4.1.1.10.0.1.1"] == descr


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"1.3.6.1.2.1.99.1": text("x")}, "unclassified octet string"),
        ({"1.3.6.1.2.1.31.1.1.1.1.1": text("port 10.1.2.3")}, "looks like an address"),
        ({"1.3.6.1.2.1.17.2.5.0": {"hex": "8000"}}, "bridge ID"),
        ({"1.3.6.1.2.1.4.35.1.4.5.2.3.1.2.3": {"hex": OTHER_MAC}}, "unexpected length"),
    ],
)
def test_refuses(tmp_path: Path, values: dict[str, Any], message: str) -> None:
    with pytest.raises(SystemExit, match=message):
        anon.main([str(write(tmp_path, "a.raw.json", recording(**values))), str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()


def test_refuses_unknown_format_and_bad_arguments(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="unknown recording format"):
        anon.main([str(write(tmp_path, "a.raw.json", {"format": 9, "values": {}})), "o"])
    assert anon.main([]) == 2


def test_many_ipv4_addresses_use_all_documentation_networks() -> None:
    anonymizer = anon.Anonymizer()
    fakes = [anonymizer.ip(bytes((10, 0, n // 256, n % 256))) for n in range(255)]
    assert bytes(fakes[-1][:3]) == bytes((198, 51, 100))
    for n in range(255, 762):
        anonymizer.ip(bytes((10, 1, n // 256, n % 256)))
    with pytest.raises(SystemExit, match="documentation networks"):
        anonymizer.ip(bytes((10, 9, 9, 9)))
    assert anonymizer.ip(bytes(16))[:2] == bytes.fromhex("2001")


def test_leftover_check_stops_writing(tmp_path: Path) -> None:
    anonymizer = anon.Anonymizer()
    anonymizer.mac(bytes.fromhex(REAL_MAC))
    assert anon.leftovers(anonymizer, json.dumps({"x": REAL_MAC})) == [REAL_MAC]
