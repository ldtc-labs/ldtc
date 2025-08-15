from __future__ import annotations

import json
import socket
import threading
import time
from typing import Dict, Optional, Mapping

from .models import Action


class HardwarePlantAdapter:
    """
    Hardware-in-the-loop adapter that ingests telemetry from UDP or Serial
    and exposes the same interface as the in-process PlantAdapter:
      - read_state() -> Dict[str, float]
      - write_actuators(action: Action) -> None
      - apply_omega(name: str, **kwargs) -> Dict[str, float | str]

    Telemetry schema (per message): JSON object with keys
      {"E", "T", "R", "demand", "io", "H"} -> float values in [0,1].

    Control/actuator schema (outbound, if configured): JSON object
      {"act": {"throttle", "cool", "repair", "accept_cmd"}}
      and for omega: {"omega": {"name": str, "args": {...}}}
    """

    def __init__(
        self,
        transport: str = "udp",
        # UDP params
        udp_bind_host: str = "0.0.0.0",
        udp_bind_port: int = 5005,
        udp_control_host: Optional[str] = None,
        udp_control_port: Optional[int] = None,
        # Serial params (optional; requires pyserial if used)
        serial_port: str = "/dev/ttyUSB0",
        serial_baud: int = 115200,
        # Behavior
        state_keys: Optional[list[str]] = None,
        telemetry_timeout_sec: float = 2.0,
    ) -> None:
        self._transport = transport.lower()
        self._udp_bind = (udp_bind_host, int(udp_bind_port))
        self._udp_ctrl = (
            (udp_control_host, int(udp_control_port))
            if udp_control_host and udp_control_port
            else None
        )
        self._serial_port = serial_port
        self._serial_baud = int(serial_baud)
        self._state_keys = state_keys or ["E", "T", "R", "demand", "io", "H"]
        self._telemetry_timeout_sec = float(telemetry_timeout_sec)

        self._lock = threading.Lock()
        self._last_action = Action()
        # Initialize state with NaNs so callers can detect missing telemetry
        self._state: Dict[str, float] = {k: float("nan") for k in self._state_keys}
        self._last_rx_ts = 0.0
        self._stop = threading.Event()

        if self._transport == "udp":
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(self._udp_bind)
            self._reader = threading.Thread(target=self._udp_reader, daemon=True)
            self._reader.start()
        elif self._transport == "serial":
            try:
                import serial
            except Exception as e:
                raise RuntimeError(
                    "pyserial is required for transport='serial'. Install pyserial and retry."
                ) from e
            self._ser = serial.Serial(self._serial_port, self._serial_baud, timeout=0.1)
            self._reader = threading.Thread(target=self._serial_reader, daemon=True)
            self._reader.start()
        else:
            raise ValueError(f"Unknown transport: {transport}")

    def close(self) -> None:
        self._stop.set()
        try:
            if hasattr(self, "_sock"):
                self._sock.close()
            if hasattr(self, "_ser"):
                self._ser.close()
        except Exception:
            pass

    # ——— Public API (mirrors PlantAdapter) ———
    def read_state(self) -> Dict[str, float]:
        with self._lock:
            # If telemetry has timed out, surface NaNs to indicate stale data
            if (
                self._last_rx_ts
                and (time.time() - self._last_rx_ts) > self._telemetry_timeout_sec
            ):
                return {k: float("nan") for k in self._state_keys}
            return dict(self._state)

    def write_actuators(self, action: Action) -> None:
        with self._lock:
            self._last_action = action
        # Optionally emit over UDP/Serial
        payload = {
            "act": {
                "throttle": float(action.throttle),
                "cool": float(action.cool),
                "repair": float(action.repair),
                "accept_cmd": bool(action.accept_cmd),
            }
        }
        self._emit_control(payload)

    def apply_omega(self, name: str, **kwargs: float) -> Dict[str, float | str]:
        # Forward omega request to control channel if available
        payload = {"omega": {"name": name, "args": {k: v for k, v in kwargs.items()}}}
        sent = self._emit_control(payload)
        return {"omega": name, "forwarded": bool(sent)}

    # ——— Internal readers/emitters ———
    def _udp_reader(self) -> None:
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(65535)
                self._ingest_bytes(data)
            except Exception:
                # Best-effort reader; continue
                continue

    def _serial_reader(self) -> None:
        # Read line-delimited JSON from serial
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(1024)
                if not chunk:
                    continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._ingest_bytes(line)
            except Exception:
                continue

    def _ingest_bytes(self, b: bytes) -> None:
        try:
            obj = json.loads(b.decode("utf-8"))
            if not isinstance(obj, dict):
                return
            parsed: Dict[str, float] = {}
            for k in self._state_keys:
                v = obj.get(k)
                if v is None:
                    continue
                try:
                    parsed[k] = float(v)
                except Exception:
                    continue
            if parsed:
                with self._lock:
                    self._state.update(parsed)
                    self._last_rx_ts = time.time()
        except Exception:
            return

    def _emit_control(self, payload: Mapping[str, object]) -> bool:
        try:
            data = json.dumps(payload).encode("utf-8")
        except Exception:
            return False
        # UDP control
        if self._udp_ctrl is not None and hasattr(self, "_sock"):
            try:
                self._sock.sendto(data, self._udp_ctrl)
                return True
            except Exception:
                return False
        # Serial control
        if hasattr(self, "_ser"):
            try:
                self._ser.write(data + b"\n")
                return True
            except Exception:
                return False
        return False
