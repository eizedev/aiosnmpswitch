"""Fixtures: anonymized recordings of real switches, served by RecordedTransport."""

from __future__ import annotations

from pathlib import Path

import pytest

from aiosnmpswitch import RecordedTransport, SnmpSwitch
from aiosnmpswitch.diagnostics import load_recording

FIXTURES = Path(__file__).parent / "fixtures"
# Three switches of one network, recorded together (anonymized in one run):
# switch-1 and switch-2 are HPE OfficeConnect 1920S, switch-3 an HPE Instant On 1930.
RECORDINGS = {
    "switch-1": FIXTURES / "hpe-1920s-pd.02.22" / "switch-1.json",
    "switch-2": FIXTURES / "hpe-1920s-pd.02.22" / "switch-2.json",
    "switch-3": FIXTURES / "hpe-1930-3.4.0.0" / "switch-3.json",
}


def recorded(name: str) -> SnmpSwitch:
    """A client that answers from the recording of ``name``."""
    return SnmpSwitch(RecordedTransport(load_recording(RECORDINGS[name])))


@pytest.fixture(params=sorted(RECORDINGS))
def any_switch(request: pytest.FixtureRequest) -> SnmpSwitch:
    """Each recorded switch in turn."""
    return recorded(request.param)
