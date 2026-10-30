"""Whatever a switch answers, the getters and helpers do not raise."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from aiosnmpswitch import ObjectId, RecordedTransport, SnmpSwitch, Value
from aiosnmpswitch.diagnostics import RECORDED_SUBTREES
from aiosnmpswitch.helpers import SwitchData, locate_macs

values: st.SearchStrategy[Value] = st.one_of(
    st.integers(min_value=-(2**31), max_value=2**64),
    st.binary(max_size=24),
    st.builds(ObjectId, st.sampled_from(["0.0", "1.3.6.1"])),
)
oids = st.builds(
    lambda subtree, tail: ".".join([subtree, *map(str, tail)]),
    st.sampled_from(RECORDED_SUBTREES),
    st.lists(st.integers(min_value=0, max_value=300), min_size=1, max_size=24),
)


@settings(max_examples=150, deadline=None)
@given(st.dictionaries(oids, values, max_size=60))
async def test_getters_never_raise(recording: dict[str, Value]) -> None:
    switch = SnmpSwitch(RecordedTransport(recording))
    await switch.get_system()
    await switch.get_stp()
    await switch.get_poe()
    await switch.get_chassis()
    await switch.get_temperatures()
    data = SwitchData(
        interfaces=await switch.get_interfaces(),
        bridge_ports=await switch.get_bridge_ports(),
        fdb=await switch.get_fdb(),
        lldp=await switch.get_lldp(),
        lag_ports=await switch.get_lag_ports(),
        neighbors=await switch.get_neighbors(),
    )
    locate_macs({"a": data, "b": data})
