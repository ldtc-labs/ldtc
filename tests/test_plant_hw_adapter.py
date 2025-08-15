from __future__ import annotations

import json
import socket
import time
import math

from ldtc.plant.hw_adapter import HardwarePlantAdapter
from ldtc.plant.models import Action


def test_hw_adapter_udp_ingest_and_read_state():
    # Bind to an ephemeral port for test isolation
    # Find a free UDP port by binding then closing
    tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tmp.bind(("127.0.0.1", 0))
    host, port = tmp.getsockname()
    tmp.close()

    adapter = HardwarePlantAdapter(
        transport="udp",
        udp_bind_host=host,
        udp_bind_port=port,
        telemetry_timeout_sec=1.0,
    )
    try:
        # Send one telemetry packet
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        msg = {"E": 0.5, "T": 0.25, "R": 0.9, "demand": 0.1, "io": 0.2, "H": 0.015}
        sock.sendto(json.dumps(msg).encode("utf-8"), (host, port))
        # Allow reader thread to process
        t0 = time.time()
        state = None
        while time.time() - t0 < 1.5:
            state = adapter.read_state()
            if state and all(
                (k in state)
                and (not math.isnan(state[k]))
                and (abs(state[k] - msg[k]) < 1e-6)
                for k in msg.keys()
            ):
                break
            time.sleep(0.01)
        assert state is not None
        for k, v in msg.items():
            assert not math.isnan(state[k])
            assert abs(state[k] - v) < 1e-6

        # Exercise actuator emit path (no assertion; just ensure no exception)
        adapter.write_actuators(
            Action(throttle=0.1, cool=0.0, repair=0.0, accept_cmd=True)
        )
        # Exercise omega forward path
        adapter.apply_omega("power_sag", drop=0.3)
    finally:
        adapter.close()
        try:
            sock.close()
        except Exception:
            pass
