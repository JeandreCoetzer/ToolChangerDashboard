"""Mock Moonraker for UI testing. Uses the real btc_dashboard.py add-on on a
fake Klipper printer (from test_klippy.py) so the panel sees real status."""
import asyncio
import json
import os
import re
import sys

import websockets

sys.path.insert(0, os.path.dirname(__file__))
import test_klippy as tk  # noqa: E402

N = int(os.environ.get("TOOLS", "8"))
printer, gcode, mod, ps = tk.build(N)
ps.status["state"] = os.environ.get("PRINT_STATE", "standby")
spools = [
    {"id": 10 + i, "remaining_weight": w, "filament": {"id": i, "name": nm, "material": mat, "color_hex": c, "vendor": {"name": "Generic"}}}
    for i, (nm, mat, c, w) in enumerate([
        ("Orange", "PLA", "e8792b", 340), ("Galaxy Blue", "PLA", "3b82f6", 612), ("Natural", "PETG", "e8e8e4", 880),
        ("Grey", "TPU", "8a9099", 500), ("Black", "PLA", "2b2b2b", 950), ("Red", "ASA", "e53935", 410),
        ("Green", "PETG", "43a047", 720), ("White", "PLA", "f5f5f5", 150)])
]
for i in range(N):
    printer.objs["gcode_macro T%d" % i].variables["spool_id"] = 10 + i
# preheat a couple of tools and make T1 active
printer.objs["extruder"].status.update(temperature=150.2, target=150)
printer.objs["extruder5"].status.update(temperature=179.6, target=180) if N > 5 else None
printer.objs["heater_fan hotend_fan0"].status["speed"] = 1.0
gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": 0}))
gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": 1}))
printer.objs["extruder1"].status.update(temperature=215.1, target=215)
printer.objs["heater_fan hotend_fan1"].status["speed"] = 1.0
DB = {}
clients = set()


def status():
    return {"btc_dashboard": mod.get_status(0), "print_stats": {"state": ps.status["state"]},
            "toolhead": {"homed_axes": "xyz"}}


def run_gcode(script):
    for line in script.splitlines():
        line = line.strip()
        m = re.match(r"^T(\d+)$", line)
        if m:
            gcode.h["TOOL_PICKUP"](tk.FakeGcmd({"TOOLNUMBER": int(m.group(1))}))
            n = int(m.group(1)); ext = "extruder" if n == 0 else "extruder%d" % n
            printer.objs[ext].status.update(target=215, temperature=214.8)
            continue
        cmd, *args = line.split()
        params = dict(a.split("=", 1) for a in args if "=" in a)
        if cmd == "SET_HEATER_TEMPERATURE":
            printer.objs[params["HEATER"]].status["target"] = float(params["TARGET"])
        elif cmd in gcode.h:
            gcode.h[cmd](tk.FakeGcmd(params))
        elif cmd == "SET_GCODE_VARIABLE":
            obj = printer.objs["gcode_macro " + params["MACRO"]]
            v = params["VALUE"]
            obj.variables = dict(obj.variables, **{params["VARIABLE"]: None if v == "None" else json.loads(v)})
        print("gcode:", line)


async def handler(ws):
    clients.add(ws)
    try:
        async for raw in ws:
            msg = json.loads(raw)
            m, p, mid = msg["method"], msg.get("params", {}), msg.get("id")
            res, err = None, None
            if m == "server.info":
                res = {"klippy_state": "ready", "components": ["spoolman", "database"]}
            elif m == "printer.objects.list":
                res = {"objects": ["btc_dashboard", "print_stats", "toolhead"]}
            elif m == "printer.objects.subscribe":
                res = {"eventtime": 0, "status": status()}
            elif m == "printer.gcode.script":
                try:
                    run_gcode(p["script"]); res = "ok"
                except Exception as e:
                    err = {"code": 400, "message": str(e)}
            elif m == "server.database.get_item":
                k = (p["namespace"], p["key"])
                if k in DB: res = {"namespace": k[0], "key": k[1], "value": DB[k]}
                else: err = {"code": 404, "message": "not found"}
            elif m == "server.database.post_item":
                DB[(p["namespace"], p["key"])] = p["value"]; res = {"value": p["value"]}
            elif m == "server.spoolman.proxy":
                res = {"response": spools, "error": None}
            else:
                res = "ok"
            out = {"jsonrpc": "2.0", "id": mid}
            out["error" if err else "result"] = err or res
            await ws.send(json.dumps(out))
    finally:
        clients.discard(ws)


async def pusher():
    while True:
        await asyncio.sleep(0.5)
        for ws in list(clients):
            try:
                await ws.send(json.dumps({"jsonrpc": "2.0", "method": "notify_status_update", "params": [status(), 0]}))
            except Exception:
                pass


async def main():
    async with websockets.serve(handler, "127.0.0.1", 7125):
        await pusher()

asyncio.run(main())
