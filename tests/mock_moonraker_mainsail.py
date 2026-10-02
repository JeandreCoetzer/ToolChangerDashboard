"""Mock Moonraker good enough to boot a Mainsail build and show the BTC panel.
Uses the real btc_dashboard.py add-on on the fake Klipper from test_klippy.py.

    TOOLS=8 python3 tests/mock_moonraker_mainsail.py     # ws + http on :7125
"""
import asyncio
import http
import json
import os
import re
import sys
import time

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

sys.path.insert(0, os.path.dirname(__file__))
import test_klippy as tk  # noqa: E402

N = int(os.environ.get("TOOLS", "8"))
printer, gcode, mod, ps = tk.build(N, {
    "presets": "Standby:150, PLA:215, PETG:240",
    "presets_t3": "Standby:0, TPU:225, TPU-95A:235",
}, tool_vars={2: {"temp_presets": "Standby:160, PETG:240, ASA:255"}})
ps.status["state"] = os.environ.get("PRINT_STATE", "standby")

SPOOLS = [
    {"id": 10 + i, "registered": "2026-01-01T00:00:00", "archived": False, "remaining_weight": w,
     "used_weight": 1000 - w, "remaining_length": w * 330, "used_length": 0, "last_used": "2026-09-27T10:00:00",
     "first_used": "2026-01-02T00:00:00",
     "filament": {"id": i, "name": nm, "material": mat, "color_hex": c, "density": 1.24, "diameter": 1.75,
                  "weight": 1000, "spool_weight": 200, "price": 25, "settings_extruder_temp": 228 if mat == "TPU" else 215,
                  "settings_bed_temp": 60, "registered": "2026-01-01T00:00:00",
                  "vendor": {"id": 1, "name": "Generic", "registered": "2026-01-01T00:00:00"}}}
    for i, (nm, mat, c, w) in enumerate([
        ("Sunset Orange", "PLA", "e8792b", 340), ("Galaxy Blue", "PLA", "3b82f6", 612),
        ("Natural", "PETG", "e8e8e4", 880), ("Grey", "TPU", "8a9099", 500), ("Black", "PLA", "2b2b2b", 950),
        ("Red", "ASA", "e53935", 410), ("Green", "PETG", "43a047", 720), ("White", "PLA", "f5f5f5", 150)])
]
for i in range(N):
    printer.objs["gcode_macro T%d" % i].variables["spool_id"] = 10 + i
printer.objs["extruder"].status.update(temperature=150.2, target=150)
if N > 5:
    printer.objs["extruder5"].status.update(temperature=179.6, target=180)
printer.objs["heater_fan hotend_fan0"].status["speed"] = 1.0
gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": 0}))
gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": 1}))
printer.objs["extruder1"].status.update(temperature=215.1, target=215)
printer.objs["heater_fan hotend_fan1"].status["speed"] = 1.0

DB = {"mainsail": {"initVersion": "v2.19.0", "general": {"printername": "Voron2.4"}}}
clients = set()
unknown = set()
exts = ["extruder"] + ["extruder%d" % i for i in range(1, N)]


def klipper_objects():
    objs = {
        "webhooks": {"state": "ready", "state_message": "Printer is ready"},
        "toolhead": {"homed_axes": "xyz", "extruder": exts[max(mod._active_tool(), 0)], "position": [150, 150, 10, 0],
                     "max_velocity": 500, "max_accel": 2400, "square_corner_velocity": 5, "minimum_cruise_ratio": 0.5,
                     "axis_minimum": [0, 0, 0, 0], "axis_maximum": [300, 300, 280, 0], "print_time": 0,
                     "estimated_print_time": 0, "stalls": 0},
        "gcode_move": {"homing_origin": [0, 0, 0, 0], "position": [150, 150, 10, 0], "gcode_position": [150, 150, 10, 0],
                       "speed_factor": 1, "extrude_factor": 1, "absolute_coordinates": True, "absolute_extrude": True, "speed": 1500},
        "print_stats": {"state": ps.status["state"], "filename": "", "total_duration": 0, "print_duration": 0,
                        "filament_used": 0, "message": "", "info": {"total_layer": None, "current_layer": None}},
        "virtual_sdcard": {"progress": 0, "is_active": False, "file_position": 0},
        "idle_timeout": {"state": "Ready", "printing_time": 0},
        "display_status": {"progress": 0, "message": None},
        "heater_bed": {"temperature": 60.1, "target": 60, "power": 0.3},
        "heaters": {"available_heaters": ["heater_bed"] + exts, "available_sensors": ["heater_bed"] + exts,
                    "available_monitors": []},
        "configfile": {"config": {}, "warnings": [], "save_config_pending": False, "settings": {
            "printer": {"kinematics": "corexy", "max_velocity": 500, "max_accel": 2400},
            "heater_bed": {"min_temp": 0, "max_temp": 120},
            "save_variables": {"filename": "~/printer_data/config/variables.cfg"},
            **{e: {"min_temp": 0, "max_temp": 300, "min_extrude_temp": 170, "nozzle_diameter": 0.4,
                   "filament_diameter": 1.75, "max_extrude_only_distance": 100} for e in exts}}},
        "btc_dashboard": mod.get_status(0),
        "save_variables": {"variables": {}},
    }
    for i, e in enumerate(exts):
        st = printer.objs[e].status
        objs[e] = {"temperature": st["temperature"], "target": st["target"], "power": st["power"],
                   "can_extrude": st["temperature"] > 170, "pressure_advance": 0.03, "smooth_time": 0.04}
        objs["heater_fan hotend_fan%d" % i] = {"speed": printer.objs["heater_fan hotend_fan%d" % i].status["speed"], "rpm": None}
        m = printer.objs["gcode_macro T%d" % i].variables
        objs["gcode_macro T%d" % i] = {"spool_id": m.get("spool_id"), "active": i == mod._active_tool()}
    return objs


def rpc(method, p):
    if method == "server.info":
        return {"klippy_connected": True, "klippy_state": "ready", "components": [
            "database", "file_manager", "klippy_apis", "machine", "data_store", "history", "spoolman", "webcam",
            "announcements", "update_manager", "authorization", "job_queue"],
            "failed_components": [], "registered_directories": ["config", "gcodes", "logs"], "warnings": [],
            "websocket_count": 1, "moonraker_version": "v0.9.3-60", "api_version": [1, 5, 0], "api_version_string": "1.5.0"}
    if method == "server.connection.identify":
        return {"connection_id": 1}
    if method == "server.config":
        return {"config": {"server": {"port": 7125}, "spoolman": {"server": "http://localhost:7912"}}, "orig": {}, "files": []}
    if method == "printer.info":
        return {"state": "ready", "state_message": "Printer is ready", "hostname": "voron", "software_version": "v0.13.0",
                "cpu_info": "4 core ARM", "klipper_path": "/home/pi/klipper", "python_path": "", "log_file": "", "config_file": "", "app": "Klipper"}
    if method == "printer.objects.list":
        return {"objects": list(klipper_objects().keys())}
    if method in ("printer.objects.subscribe", "printer.objects.query"):
        return {"eventtime": time.monotonic(), "status": klipper_objects()}
    if method == "printer.gcode.script":
        run_gcode(p["script"])
        return "ok"
    if method == "server.database.list":
        return {"namespaces": list(DB.keys())}
    if method == "server.database.get_item":
        ns = DB.get(p["namespace"])
        if ns is None:
            raise KeyError("404")
        if "key" in p and p["key"] is not None:
            return {"namespace": p["namespace"], "key": p["key"], "value": get_key(ns, p["key"])}
        return {"namespace": p["namespace"], "key": None, "value": ns}
    if method == "server.database.post_item":
        set_key(DB.setdefault(p["namespace"], {}), p["key"], p["value"])
        return {"namespace": p["namespace"], "key": p["key"], "value": p["value"]}
    if method == "server.spoolman.proxy":
        if p.get("path", "").startswith("/v1/spool"):
            return SPOOLS if not p.get("use_v2_response") else {"response": SPOOLS, "error": None}
        if p.get("path", "").startswith("/v1/info"):
            return {"version": "0.21.0", "debug_mode": False, "automatic_backups": True, "data_dir": "", "backups_dir": ""}
        return []
    if method == "server.spoolman.status":
        return {"spoolman_connected": True, "pending_reports": [], "spool_id": None}
    if method == "server.spoolman.get_spool_id":
        return {"spool_id": None}
    if method == "server.temperature_store":
        return {e: {"temperatures": [], "targets": [], "powers": []} for e in ["heater_bed"] + exts}
    if method == "server.gcode_store":
        return {"gcode_store": []}
    if method == "machine.system_info":
        return {"system_info": {"cpu_info": {"cpu_count": 4}, "sd_info": {}, "distribution": {"name": "Debian"},
                                "available_services": ["klipper", "moonraker"], "service_state": {}, "virtualization": {}, "network": {}}}
    if method == "machine.update.status":
        return {"busy": False, "github_rate_limit": 60, "github_requests_remaining": 60, "version_info": {}}
    if method in ("server.webcams.list",):
        return {"webcams": []}
    if method == "server.announcements.list":
        return {"entries": [], "feeds": []}
    if method == "server.files.roots":
        return [{"name": "config", "path": "", "permissions": "rw"}, {"name": "gcodes", "path": "", "permissions": "rw"}]
    if method == "server.files.get_directory":
        return {"dirs": [], "files": [], "disk_usage": {"total": 1, "used": 0, "free": 1}, "root_info": {"name": p.get("path", "gcodes"), "permissions": "rw"}}
    if method == "server.history.list":
        return {"count": 0, "jobs": []}
    if method == "server.history.totals":
        return {"job_totals": {"total_jobs": 0, "total_time": 0, "total_print_time": 0, "total_filament_used": 0, "longest_job": 0, "longest_print": 0}, "auxiliary_totals": []}
    if method == "server.job_queue.status":
        return {"queued_jobs": [], "queue_state": "ready"}
    if method == "machine.device_power.devices":
        return {"devices": []}
    if method == "server.sensors.list":
        return {"sensors": {}}
    if method == "machine.proc_stats":
        return {"moonraker_stats": [], "throttled_state": {"bits": 0, "flags": []}, "cpu_temp": 45, "network": {}, "system_cpu_usage": {}, "system_memory": {}, "websocket_connections": 1}
    if method == "access.get_user":
        return {"username": "_TRUSTED_USER_", "source": "moonraker", "created_on": 0}
    if method == "access.users.list":
        return {"users": []}
    if method == "access.get_api_key":
        return "mock-api-key"
    if method == "server.files.list":
        return []
    if method == "access.oneshot_token":
        return "token"
    unknown.add(method)
    return {}


def get_key(ns, key):
    cur = ns
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError("404")
        cur = cur[part]
    return cur


def set_key(ns, key, value):
    parts = key.split(".")
    cur = ns
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def run_gcode(script):
    for line in script.splitlines():
        line = line.strip()
        print("gcode:", line, flush=True)
        m = re.match(r"^T(\d+)$", line)
        if m:
            n = int(m.group(1))
            gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": n}))
            printer.objs[exts[n]].status.update(target=215, temperature=214.8)
            continue
        cmd, *args = line.split() or [""]
        params = dict(a.split("=", 1) for a in args if "=" in a)
        if cmd == "SET_HEATER_TEMPERATURE":
            printer.objs[params["HEATER"]].status["target"] = float(params["TARGET"])
        elif cmd == "SET_GCODE_VARIABLE":
            obj = printer.objs["gcode_macro " + params["MACRO"]]
            v = params["VALUE"]
            obj.variables = dict(obj.variables, **{params["VARIABLE"]: None if v == "None" else json.loads(v)})
        elif cmd in gcode.h:
            gcode.h[cmd](tk.FakeGcmd(params))


CORS = [("Access-Control-Allow-Origin", "*"), ("Access-Control-Allow-Headers", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"), ("Content-Type", "application/json")]


def http_response(status, obj):
    body = json.dumps(obj).encode()
    return Response(status, http.HTTPStatus(status).phrase, Headers(CORS + [("Content-Length", str(len(body)))]), body)


def process_request(connection, request):
    if request.path.startswith("/websocket"):
        return None
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None
    path = request.path.split("?")[0]
    if path.startswith("/server/files/config/") and path.endswith(".json"):
        return http_response(404, {"error": {"code": 404, "message": "not found"}})
    if path == "/server/database/item":
        q = dict(kv.split("=", 1) for kv in request.path.split("?", 1)[1].split("&") if "=" in kv) if "?" in request.path else {}
        ns = DB.get(q.get("namespace", ""), None)
        if ns is None:
            return http_response(404, {"error": {"code": 404, "message": "namespace not found"}})
        return http_response(200, {"result": {"namespace": q.get("namespace"), "key": q.get("key"), "value": ns}})
    return http_response(200, {"result": {}})


async def handler(ws):
    clients.add(ws)
    try:
        async for raw in ws:
            msg = json.loads(raw)
            m, p, mid = msg.get("method"), msg.get("params", {}) or {}, msg.get("id")
            out = {"jsonrpc": "2.0", "id": mid}
            try:
                out["result"] = rpc(m, p)
            except KeyError:
                out["error"] = {"code": -32601, "message": "Not found"}
            except Exception as e:  # noqa: BLE001
                out["error"] = {"code": 400, "message": str(e)}
            await ws.send(json.dumps(out))
    finally:
        clients.discard(ws)


async def pusher():
    while True:
        await asyncio.sleep(0.5)
        payload = json.dumps({"jsonrpc": "2.0", "method": "notify_status_update", "params": [klipper_objects(), time.monotonic()]})
        for ws in list(clients):
            try:
                await ws.send(payload)
            except Exception:  # noqa: BLE001
                pass
        if unknown:
            print("unknown methods:", sorted(unknown), flush=True)
            unknown.clear()


async def main():
    async with serve(handler, "127.0.0.1", 7125, process_request=process_request, max_size=None):
        await pusher()

asyncio.run(main())
