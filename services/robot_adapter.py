#!/usr/bin/env python3
"""
Robot data adapter for the Huayan welding MES assistant prototype.

The browser cannot call the robot controller TCP protocol or ZeroMQ welding
status stream directly, so this small local service exposes a read-only HTTP
JSON endpoint for the HTML prototype.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_CONTROLLER_PORT = 10003
DEFAULT_WELD_STATUS_PORT = 30601
MAX_SEGMENT_MM = 250.0


class RobotCache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_tcp_xyz: dict[str, tuple[float, float, float]] = {}
        self.length_mm: dict[str, float] = {}
        self.weld_status: dict[str, dict[str, Any]] = {}
        self.arc_active: dict[str, bool] = {}
        self.subscribers: dict[str, threading.Thread] = {}

    def update_tcp_length(
        self,
        key: str,
        xyz: tuple[float, float, float] | None,
        arc_active: bool,
    ) -> float:
        if xyz is None:
            return self.length_mm.get(key, 0.0)
        with self.lock:
            previous = self.last_tcp_xyz.get(key)
            if arc_active and previous is not None:
                segment = distance(previous, xyz)
                if 0.0 < segment <= MAX_SEGMENT_MM:
                    self.length_mm[key] = self.length_mm.get(key, 0.0) + segment
            self.last_tcp_xyz[key] = xyz
            return self.length_mm.get(key, 0.0)

    def get_weld_status(self, host: str, port: int) -> dict[str, Any]:
        key = f"{host}:{port}"
        self.ensure_weld_subscriber(host, port)
        with self.lock:
            return dict(self.weld_status.get(key, {}))

    def set_arc_active(self, host: str, port: int, active: bool) -> None:
        with self.lock:
            self.arc_active[f"{host}:{port}"] = active

    def is_arc_active(self, host: str, port: int) -> bool:
        with self.lock:
            return self.arc_active.get(f"{host}:{port}", False)

    def ensure_weld_subscriber(self, host: str, port: int) -> None:
        key = f"{host}:{port}"
        if key in self.subscribers:
            return
        thread = threading.Thread(
            target=weld_status_worker,
            args=(self, host, port),
            daemon=True,
            name=f"weld-status-{key}",
        )
        self.subscribers[key] = thread
        thread.start()


cache = RobotCache()


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def send_controller_command(host: str, port: int, command: str, timeout: float = 1.2) -> str:
    payload = command if command.endswith(";") else f"{command};"
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload.encode("utf-8"))
        chunks: list[bytes] = []
        end = time.time() + timeout
        while time.time() < end:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", errors="ignore")
            if ";" in text:
                return text
        return b"".join(chunks).decode("utf-8", errors="ignore")


def numbers(text: str) -> list[float]:
    return [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]


def command_ok(text: str) -> bool:
    lowered = text.lower()
    if not text.strip():
        return False
    return not any(token in lowered for token in ("fail", "error", "false"))


def read_robot_state(host: str, port: int, rbt_id: int) -> dict[str, Any]:
    raw = send_controller_command(host, port, f"ReadRobotState,{rbt_id},")
    vals = numbers(raw)
    return {
        "raw": raw,
        "ok": command_ok(raw),
        "moving_state": int(vals[1]) if len(vals) > 1 else None,
        "enable_state": int(vals[2]) if len(vals) > 2 else None,
        "error_state": int(vals[3]) if len(vals) > 3 else None,
        "error_code": int(vals[4]) if len(vals) > 4 else None,
    }


def read_tcp_position(host: str, port: int, rbt_id: int) -> dict[str, Any]:
    raw = send_controller_command(host, port, f"ReadActPos,{rbt_id},")
    vals = numbers(raw)
    # The protocol returns joint values first and Cartesian/TCP values later.
    # Prefer dTcp_X/Y/Z when present; fall back to dX/Y/Z.
    xyz = None
    if len(vals) >= 15:
        xyz = (vals[12], vals[13], vals[14])
    elif len(vals) >= 9:
        xyz = (vals[6], vals[7], vals[8])
    return {"raw": raw, "ok": command_ok(raw), "tcp_xyz": xyz}


def read_tcp_velocity(host: str, port: int, rbt_id: int) -> dict[str, Any]:
    raw = send_controller_command(host, port, f"ReadActTcpVel,{rbt_id},")
    vals = numbers(raw)
    linear = None
    if len(vals) >= 4:
        linear = math.sqrt(vals[1] ** 2 + vals[2] ** 2 + vals[3] ** 2)
    elif len(vals) >= 3:
        linear = math.sqrt(vals[0] ** 2 + vals[1] ** 2 + vals[2] ** 2)
    return {"raw": raw, "ok": command_ok(raw), "tcp_speed_mm_s": linear}


def read_soft_motion_progress(host: str, port: int, rbt_id: int) -> dict[str, Any]:
    try:
        raw = send_controller_command(host, port, f"ReadSoftMotionProgress,{rbt_id},", timeout=0.8)
    except OSError:
        return {"raw": "", "ok": False, "progress": None, "point_index": None}
    vals = numbers(raw)
    return {
        "raw": raw,
        "ok": command_ok(raw),
        "progress": vals[1] if len(vals) > 1 else (vals[0] if vals else None),
        "point_index": int(vals[2]) if len(vals) > 2 else None,
    }


def pick_number(payload: dict[str, Any], names: tuple[str, ...]) -> float | None:
    lowered = {str(k).lower(): v for k, v in payload.items()}
    for name in names:
        value = lowered.get(name.lower())
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    for value in payload.values():
        if isinstance(value, dict):
            nested = pick_number(value, names)
            if nested is not None:
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested = pick_number(item, names)
                    if nested is not None:
                        return nested
    return None


def text_values(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(text_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(text_values(item))
    elif isinstance(payload, str):
        values.append(payload)
    return values


def infer_arc_event(payload: dict[str, Any], flattened: dict[str, Any]) -> str | None:
    combined = " ".join(text_values(payload)).lower()
    arc_on_tokens = (
        "起弧",
        "arcstart",
        "arc_start",
        "arcon",
        "arc_on",
        "startarc",
        "weldstart",
        "weld_start",
    )
    arc_off_tokens = (
        "收弧",
        "arcoff",
        "arc_off",
        "arcend",
        "arc_end",
        "endarc",
        "weldend",
        "weld_end",
    )
    if any(token in combined for token in arc_off_tokens):
        return "off"
    if any(token in combined for token in arc_on_tokens):
        return "on"

    current = flattened.get("realtime_current_a")
    voltage = flattened.get("realtime_voltage_v")
    if isinstance(current, (int, float)) and current > 5:
        return "on"
    if isinstance(voltage, (int, float)) and voltage > 5:
        return "on"
    if current == 0 or voltage == 0:
        return "off"
    return None


def flatten_weld_status(payload: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        "task_id": payload.get("taskID") or payload.get("taskId"),
        "action_id": payload.get("actionID") or payload.get("actionId"),
        "action_name": payload.get("actionName") or payload.get("actionType") or payload.get("action"),
        "task_status": payload.get("taskStatus"),
        "weld_error_code": payload.get("weldErrorCode"),
        "wire_speed": pick_number(payload, ("realtimeWireSpeed", "wireSpeed", "realTimeWireSpeed")),
        "realtime_current_a": pick_number(
            payload,
            ("realtimeCurrent", "realTimeCurrent", "actualCurrent", "weldCurrent", "current"),
        ),
        "realtime_voltage_v": pick_number(
            payload,
            ("realtimeVoltage", "realTimeVoltage", "actualVoltage", "weldVoltage", "voltage"),
        ),
    }
    flattened["arc_event"] = infer_arc_event(payload, flattened)
    return flattened


def weld_status_worker(robot_cache: RobotCache, host: str, port: int) -> None:
    try:
        import zmq  # type: ignore
    except ImportError:
        return

    key = f"{host}:{port}"
    context = zmq.Context.instance()
    socket_ = context.socket(zmq.SUB)
    socket_.setsockopt_string(zmq.SUBSCRIBE, "")
    socket_.setsockopt(zmq.RCVTIMEO, 1000)
    socket_.connect(f"tcp://{host}:{port}")
    while True:
        try:
            message = socket_.recv()
        except Exception:
            continue
        payload = decode_weld_message(message)
        if not payload:
            continue
        flattened = flatten_weld_status(payload)
        if flattened.get("arc_event") == "on":
            robot_cache.set_arc_active(host, port, True)
        elif flattened.get("arc_event") == "off":
            robot_cache.set_arc_active(host, port, False)
        with robot_cache.lock:
            robot_cache.weld_status[key] = flattened | {
                "arc_active": robot_cache.arc_active.get(key, False),
                "sample_time": time.time(),
                "raw": payload,
            }


def decode_weld_message(message: bytes) -> dict[str, Any] | None:
    text = message.decode("utf-8", errors="ignore").strip()
    if "####" in text and "$$$$" in text:
        start = text.find("####") + 12
        end = text.rfind("$$$$")
        text = text[start:end]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload.get("StatusMessage") if isinstance(payload.get("StatusMessage"), dict) else payload
    return None


def build_sample(host: str, controller_port: int, weld_port: int, rbt_id: int) -> dict[str, Any]:
    started = time.time()
    response: dict[str, Any] = {
        "sample_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": host,
        "connected": False,
        "realtime_current_a": None,
        "realtime_voltage_v": None,
        "tcp_speed_mm_s": None,
        "tcp_length_mm": None,
        "arc_active": False,
        "alarm_code": "无",
    }
    try:
        state = read_robot_state(host, controller_port, rbt_id)
        position = read_tcp_position(host, controller_port, rbt_id)
        velocity = read_tcp_velocity(host, controller_port, rbt_id)
        progress = read_soft_motion_progress(host, controller_port, rbt_id)
        weld = cache.get_weld_status(host, weld_port)
        arc_active = bool(weld.get("arc_active") or cache.is_arc_active(host, weld_port))
        length = cache.update_tcp_length(host, position.get("tcp_xyz"), arc_active)
        response.update(
            {
                "connected": state["ok"],
                "robot_state": state,
                "tcp_xyz": position.get("tcp_xyz"),
                "tcp_speed_mm_s": velocity.get("tcp_speed_mm_s"),
                "tcp_length_mm": length,
                "arc_active": arc_active,
                "path_progress": progress.get("progress"),
                "path_point_index": progress.get("point_index"),
                "weld_status": weld,
                "realtime_current_a": weld.get("realtime_current_a"),
                "realtime_voltage_v": weld.get("realtime_voltage_v"),
                "weld_error_code": weld.get("weld_error_code"),
                "alarm_code": "无" if not weld.get("weld_error_code") else str(weld.get("weld_error_code")),
            }
        )
    except OSError as exc:
        response["error"] = str(exc)
    response["duration_ms"] = round((time.time() - started) * 1000, 1)
    return response


class Handler(BaseHTTPRequestHandler):
    server_version = "HuayanRobotAdapter/0.1"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/robot/sample", "/api/robot/status"):
            self.send_json({"error": "not found"}, status=404)
            return
        params = parse_qs(parsed.query)
        host = params.get("host", ["192.168.0.10"])[0]
        rbt_id = int(params.get("rbt_id", ["0"])[0])
        controller_port = int(params.get("controller_port", [str(DEFAULT_CONTROLLER_PORT)])[0])
        weld_port = int(params.get("weld_port", [str(DEFAULT_WELD_STATUS_PORT)])[0])
        self.send_json(build_sample(host, controller_port, weld_port, rbt_id))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Huayan robot read-only data adapter")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Robot adapter listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
