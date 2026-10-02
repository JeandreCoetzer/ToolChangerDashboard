"""Offline test of btc_dashboard.py against a fake Klipper printer."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "klippy"))
import btc_dashboard as bd  # noqa: E402


class CmdError(Exception):
    pass


class FakeReactor:
    NOW = 0.0
    def __init__(self): self.t = 100.0
    def monotonic(self): self.t += 0.5; return self.t
    def register_timer(self, cb, when): self.timer = cb
    def register_callback(self, cb): cb(0)


class Obj:
    def __init__(self, status=None, variables=None):
        self.status = status or {}
        if variables is not None:
            self.variables = variables
    def get_status(self, et): return dict(self.status)


class FakeGcmd:
    def __init__(self, params): self.params = params; self.out = []
    def get_int(self, k, default=None): return int(self.params[k]) if k in self.params else default
    def get_float(self, k, default=None): return float(self.params[k]) if k in self.params else default
    def respond_info(self, m): self.out.append(m); print("  >>", m.replace("\n", "\n  >> "))
    def error(self, m): return CmdError(m)


class FakeGcode:
    def __init__(self): self.h = {}; self.scripts = []
    def register_command(self, cmd, func, desc=None):
        if func is None:
            return self.h.pop(cmd, None)
        self.h[cmd] = func
    def respond_info(self, m): print("  >>", m)
    def run_script_from_command(self, s): self.scripts.append(s)


class FakeToolhead:
    def __init__(self): self.pt = 10.0
    def get_last_move_time(self): return self.pt


class FakeConfig:
    def __init__(self, printer, opts): self.p = printer; self.o = opts
    def get_printer(self): return self.p
    def get(self, k, default=None): return self.o.get(k, default)
    def getint(self, k, default=None, minval=None, maxval=None):
        return int(self.o.get(k, default))
    def getchoice(self, k, choices, default):
        return choices[self.o.get(k, default)]
    def get_prefix_options(self, prefix):
        return [k for k in self.o if k.startswith(prefix)]
    def error(self, msg):
        return ValueError(msg)


class FakePrinter:
    def __init__(self):
        self.objs = {}; self.events = {}; self.reactor = FakeReactor()
    def get_reactor(self): return self.reactor
    def lookup_object(self, n, default=None):
        return self.objs.get(n, default)
    def lookup_objects(self, module):
        return [(k, v) for k, v in self.objs.items() if k.startswith(module)]
    def register_event_handler(self, e, cb): self.events[e] = cb


def build(n_tools=4, opts=None, dock_sense=False, tool_vars=None):
    p = FakePrinter()
    g = FakeGcode(); p.objs["gcode"] = g
    th = FakeToolhead(); p.objs["toolhead"] = th
    ps = Obj({"state": "standby"}); p.objs["print_stats"] = ps
    btc = Obj(variables={"tool_current_asperbtc": -1, "last_dropoff_successful": False,
                         "gcode_offset_z_adjust": 0.0})
    p.objs["gcode_macro _BTC_VARIABLES"] = btc
    cs = Obj({"state": "RELEASED"}); p.objs["gcode_button carriage_sense"] = cs
    p.objs["gcode_macro DOCKSLIDE_HOME"] = Obj(variables={})
    p.objs["gcode_macro _DOCKSLIDE_VARIABLES"] = Obj(variables={"dockslide_status": 1, "dockslide_homed": True})
    p.objs["gcode_button dockslide_endstop_right"] = Obj({"state": "RELEASED"})
    p.objs["gcode_button dockslide_endstop_left"] = Obj({"state": "RELEASED"})
    sv = Obj(); sv.allVariables = {"btc_t2_xoffset": 0.5, "btc_t3_yoffset": None}
    p.objs["save_variables"] = sv
    raw = {}
    for n in range(n_tools):
        ext = "extruder" if n == 0 else "extruder%d" % n
        p.objs["gcode_macro _VARIABLES_T%d" % n] = Obj(variables={
            "xoffset": 0.1 * n, "yoffset": -0.1 * n, "zoffset": 0.01 * n,
            "shapertype_x": "mzv", "shaperfreq_x": 60 + n, "shapertype_y": "mzv",
            "shaperfreq_y": 40 + n, "pressure_advance": 0.03, **((tool_vars or {}).get(n, {}))})
        p.objs["gcode_macro T%d" % n] = Obj(variables={"spool_id": (10 + n) if n % 2 else None, "active": False})
        p.objs[ext] = Obj({"temperature": 24.0 + n, "target": 0.0, "power": 0.0})
        p.objs["heater_fan hotend_fan%d" % n] = Obj({"speed": 0.0, "rpm": None})
        raw["heater_fan hotend_fan%d" % n] = {"heater": ext}
        raw[ext] = {"max_temp": "300"}
        raw["gcode_macro T%d" % n] = {"gcode": "TOOL_PICKUP TOOLNUMBER=%d\nACTIVATE_EXTRUDER EXTRUDER=%s" % (n, ext)}
        if dock_sense:
            p.objs["gcode_button dock_sense_t%d" % n] = Obj({"state": "PRESSED"})
    p.objs["configfile"] = Obj({"config": raw})

    # fake BTC macros
    def pickup(gcmd):
        tgt = gcmd.get_int("TOOLNUMBER")
        th.pt += 12.3
        if gcmd.params.get("FAIL"):
            btc.variables = dict(btc.variables, tool_current_asperbtc=-1)
            return
        if gcmd.params.get("RAISE"):
            raise CmdError("BTC: Tool %d not detected at carriage!!" % tgt)
        cur = btc.variables["tool_current_asperbtc"]
        if cur >= 0 and cur != tgt:
            g.h["TOOL_DROPOFF"](FakeGcmd({"TOOLNUMBER": cur, "FROMPICKUP": 1}))
        btc.variables = dict(btc.variables, tool_current_asperbtc=tgt)
        cs.status["state"] = "PRESSED"

    def dropoff(gcmd):
        th.pt += 5.0
        btc.variables = dict(btc.variables, tool_current_asperbtc=-1, last_dropoff_successful=True)
        cs.status["state"] = "RELEASED"

    g.h["TOOL_PICKUP"] = pickup
    g.h["TOOL_DROPOFF"] = dropoff

    o = {"tools": "auto", "dock_sense": "per_tool" if dock_sense else "none"}
    o.update(opts or {})
    mod = bd.load_config(FakeConfig(p, o))
    p.events["klippy:connect"]()
    p.events["klippy:ready"]()
    return p, g, mod, ps


def main():
    p, g, mod, ps = build(4)
    # Klipper's statistics module calls obj.stats(eventtime) on every object
    # that has a "stats" attribute - we must not define one by accident.
    assert not hasattr(mod, "stats") or callable(mod.stats), "attribute 'stats' clashes with Klipper statistics"
    assert [t["n"] for t in mod.tools] == [0, 1, 2, 3]
    assert mod.tools[1]["extruder"] == "extruder1"
    assert mod.tools[1]["fan"] == "heater_fan hotend_fan1"
    # restored save_variables offset for T2, None for T3 skipped
    st = mod.get_status(0)
    assert st["tools"][2]["xoffset"] == 0.5, st["tools"][2]
    assert st["tools"][3]["yoffset"] == -0.3
    assert st["dockslide"]["state"] == "parked"

    ps.status["state"] = "printing"; mod._poll(0)
    g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 0}))
    g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 1}))
    g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 1}))   # already on -> not logged
    g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 2, "FAIL": 1}))
    try:
        g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 3, "RAISE": 1}))
        raise AssertionError("expected error")
    except CmdError:
        pass
    g.h["TOOL_PICKUP"](FakeGcmd({"TOOLNUMBER": 0}))
    g.h["TOOL_DROPOFF"](FakeGcmd({"TOOLNUMBER": 0}))
    st = mod.get_status(0)
    labels = [(e["label"], e["result"]) for e in st["log"]]
    print("log:", labels)
    assert labels[-1] == ("empty → T0", "ok")
    assert labels[-2] == ("T0 → T1", "ok")
    assert ("T1 → T2", "fail") in labels and ("empty → T3", "fail") in labels
    assert labels[0] == ("T0 → dock", "ok")
    assert st["stats"]["changes_total"] == 6, st["stats"]
    assert st["stats"]["failed_total"] == 2
    assert st["stats"]["tools_used_print"] == [0, 1, 2, 3]
    assert st["busy"] is False

    # offsets
    g.scripts.clear()
    g.h["BTC_DASHBOARD_SET_OFFSET"](FakeGcmd({"TOOL": 1, "X": -0.12, "Z": 0.04}))
    assert any("btc_t1_xoffset" in s for s in g.scripts), g.scripts
    assert mod.get_status(0)["tools"][1]["xoffset"] == -0.12
    g.h["BTC_DASHBOARD_STATUS"](FakeGcmd({}))

    json.dumps(mod.get_status(0))  # must be serialisable for Moonraker

    # per-tool dock sense + fixed tool count
    p, g, mod, ps = build(8, {"tools": "6"}, dock_sense=True)
    st = mod.get_status(0)
    assert st["config"]["tool_count"] == 6
    assert st["tools"][0]["docked"] is True
    # ---- temperature presets
    p, g, mod, ps = build(4, {
        "presets": "Standby:150, PLA:215",
        "presets_t1": "Standby:160, PETG:240, ASA:255",
        "presets_t2": "Hot:320, Bad, PLA:210",
        "presets_t9": "PLA:200",
    }, tool_vars={3: {"temp_presets": {"TPU": 225, "Standby": 0}}})
    st = mod.get_status(0)
    pr = {t["name"]: (t["presets_source"], [(x["label"], x["temp"]) for x in t["presets"]]) for t in st["tools"]}
    print("presets:", pr)
    assert pr["T0"] == ("default", [("Standby", 150), ("PLA", 215)])
    assert pr["T1"] == ("config", [("Standby", 160), ("PETG", 240), ("ASA", 255)])
    assert pr["T2"] == ("config", [("PLA", 210)])          # 320 > max_temp, 'Bad' malformed
    assert pr["T3"] == ("tool", [("TPU", 225), ("Standby", 0)])
    errs = " | ".join(st["errors"])
    assert "max_temp" in errs and "needs label:temperature" in errs and "no tool T9" in errs, errs
    assert st["config"]["default_presets"] == [{"label": "Standby", "temp": 150}, {"label": "PLA", "temp": 215}]
    try:
        build(2, {"presets_tx": "PLA:200"})
        raise AssertionError("expected config error for presets_tx")
    except ValueError as e:
        assert "presets_t<number>" in str(e)
    # no presets configured -> built-in defaults
    p, g, mod, ps = build(2)
    assert [x["label"] for x in mod.get_status(0)["tools"][0]["presets"]] == ["Standby", "PLA", "PETG", "ABS"]
    json.dumps(mod.get_status(0))

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
