# BTC Dashboard - status bridge for the Bikin Toolchanger (BTC) macros
# used by Lineux Hotswap and similar macro-based hotend changers.
#
# It does not move anything or change how BTC works. It:
#   * discovers the tools BTC defines (_VARIABLES_Tn macros) and maps each
#     one to its heater, hotend fan and spool
#   * publishes everything as one Klipper status object: printer.btc_dashboard
#   * times every toolchange and keeps a short log
#   * optionally persists tool offsets edited from the dashboard
#
# Install: symlink into klipper/klippy/extras/ and add [btc_dashboard]
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import re
import time

VERSION = "0.2.0"

DOCKSLIDE_STATES = {0: "unknown", 1: "parked", 2: "deployed", 3: "standby"}
DEFAULT_PRESETS = "Standby:150, PLA:215, PETG:240, ABS:255"
MAX_PRESET_LABEL = 20
MAX_PRESETS = 8


def parse_presets(raw, where):
    """Parse presets into [{"label", "temp"}] and a list of problems.

    Accepts "Standby:150, PLA:215" (also newline separated), a dict
    {"PLA": 215} or a list of [label, temp] pairs (macro variable forms).
    """
    items = []
    if raw is None:
        return [], []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                items.append((entry[0], entry[1]))
            else:
                items.append((str(entry), None))
    else:
        for part in re.split(r"[,\n]", str(raw)):
            part = part.strip()
            if not part:
                continue
            if ":" not in part:
                items.append((part, None))
                continue
            label, temp = part.rsplit(":", 1)
            items.append((label, temp))
    presets, problems = [], []
    for label, temp in items:
        label = str(label).strip()
        try:
            value = float(str(temp).strip())
        except (TypeError, ValueError):
            problems.append("%s: preset '%s' needs label:temperature" % (where, label))
            continue
        if not label:
            problems.append("%s: preset %s has no label" % (where, temp))
            continue
        presets.append({"label": label[:MAX_PRESET_LABEL], "temp": int(round(value))})
    if len(presets) > MAX_PRESETS:
        problems.append("%s: only the first %d presets are shown" % (where, MAX_PRESETS))
        presets = presets[:MAX_PRESETS]
    return presets, problems


class BTCDashboard:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object("gcode")

        # ---- options -------------------------------------------------
        tools = config.get("tools", "auto").strip().lower()
        self.tool_limit = None if tools == "auto" else config.getint("tools", minval=1, maxval=16)
        self.carriage_sense_name = config.get("carriage_sense", "carriage_sense").strip()
        self.dock_sense = config.getchoice(
            "dock_sense", {"none": "none", "per_tool": "per_tool"}, "none")
        self.dock_sense_template = config.get("dock_sense_button", "dock_sense_t{n}").strip()
        self.dockslide_opt = config.getchoice(
            "dockslide", {"auto": "auto", "yes": "yes", "no": "no"}, "auto")
        self.spoolman_opt = config.getchoice(
            "spoolman", {"auto": "auto", "yes": "yes", "no": "no"}, "auto")
        self.save_offsets_opt = config.getchoice(
            "save_offsets", {"auto": "auto", "yes": "yes", "no": "no"}, "auto")
        self.extruder_names = self._list_opt(config, "extruder_names")
        self.fan_names = self._list_opt(config, "hotend_fan_names")
        self.log_length = config.getint("log_length", 20, minval=1, maxval=200)
        # temperature preset buttons shown in the tool popup
        self.default_presets_raw = config.get("presets", DEFAULT_PRESETS)
        self.tool_presets_raw = {}
        for opt in config.get_prefix_options("presets_t"):
            m = re.match(r"^presets_t(\d+)$", opt)
            if m is None:
                raise config.error("btc_dashboard: option '%s' should be presets_t<number>, e.g. presets_t2" % opt)
            self.tool_presets_raw[int(m.group(1))] = config.get(opt)
        self.default_presets = []
        self.btc_vars_name = config.get("btc_variables_macro", "_BTC_VARIABLES")
        self.tool_vars_prefix = config.get("tool_variables_prefix", "_VARIABLES_T")

        # ---- runtime state ------------------------------------------
        self.tools = []            # list of dicts, see _discover()
        self.carriage_sense = None
        self.dockslide_vars = None
        self.dockslide_endstops = []
        self.btc_vars = None
        self.save_vars = None
        self.print_stats = None
        self.toolhead = None
        self.log = []
        self._stats = {"changes_total": 0, "changes_print": 0, "failed_total": 0,
                      "avg_time": 0.0, "last_time": 0.0, "last_result": "",
                      "tools_used_print": []}
        self._time_sum = 0.0
        self._timed = 0
        self._busy = None          # current change being timed
        self._last_print_state = None
        self.errors = []

        self.printer.register_event_handler("klippy:connect", self._handle_connect)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

        self.gcode.register_command(
            "BTC_DASHBOARD_STATUS", self.cmd_STATUS,
            desc="Show what BTC Dashboard discovered")
        self.gcode.register_command(
            "BTC_DASHBOARD_SET_OFFSET", self.cmd_SET_OFFSET,
            desc="Set (and optionally save) a tool's X/Y/Z offset")
        self.gcode.register_command(
            "BTC_DASHBOARD_CLEAR_SAVED_OFFSETS", self.cmd_CLEAR_SAVED,
            desc="Forget offsets saved by BTC Dashboard (cfg values apply after restart)")
        self.gcode.register_command(
            "BTC_DASHBOARD_RESET_STATS", self.cmd_RESET_STATS,
            desc="Clear toolchange counters and log")

    # ------------------------------------------------------------------
    @staticmethod
    def _list_opt(config, name):
        raw = config.get(name, "auto").strip()
        if raw.lower() == "auto":
            return None
        return [s.strip() for s in raw.split(",") if s.strip()]

    def _lookup(self, name):
        return self.printer.lookup_object(name, None)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def _handle_connect(self):
        self.toolhead = self._lookup("toolhead")
        self.print_stats = self._lookup("print_stats")
        self.btc_vars = self._lookup("gcode_macro " + self.btc_vars_name)
        if self.btc_vars is None:
            self.errors.append("gcode_macro %s not found - is BTC installed?" % self.btc_vars_name)
        self.carriage_sense = self._lookup("gcode_button " + self.carriage_sense_name)
        if self.carriage_sense is None:
            self.errors.append("gcode_button %s not found" % self.carriage_sense_name)
        self.save_vars = self._lookup("save_variables")

        use_ds = self.dockslide_opt == "yes" or (
            self.dockslide_opt == "auto" and self._lookup("gcode_macro DOCKSLIDE_HOME") is not None)
        if use_ds:
            self.dockslide_vars = self._lookup("gcode_macro _DOCKSLIDE_VARIABLES")
            for side in ("right", "left"):
                obj = self._lookup("gcode_button dockslide_endstop_" + side)
                if obj is not None:
                    self.dockslide_endstops.append((side, obj))

        self._discover()
        self._wrap_commands()

    def _raw_config(self):
        try:
            cfg = self.printer.lookup_object("configfile")
            return cfg.get_status(self.reactor.monotonic()).get("config", {})
        except Exception:
            return {}

    def _discover(self):
        raw = self._raw_config()
        pat = re.compile(r"^gcode_macro " + re.escape(self.tool_vars_prefix) + r"(\d+)$")
        nums = []
        for name, obj in self.printer.lookup_objects("gcode_macro"):
            m = pat.match(name)
            if m:
                nums.append(int(m.group(1)))
        nums.sort()
        if self.tool_limit is not None:
            nums = nums[:self.tool_limit]

        # heater_fan sections by the heater they follow
        fans_by_heater = {}
        for sec, opts in raw.items():
            if sec.startswith("heater_fan "):
                heater = str(opts.get("heater", "extruder")).strip()
                fans_by_heater.setdefault(heater, sec)

        self.tools = []
        for idx, n in enumerate(nums):
            ext = None
            if self.extruder_names and idx < len(self.extruder_names):
                ext = self.extruder_names[idx]
            else:
                # BTC's T macro / _CHECK_CARRIAGE_SECOND use extruder, extruder1, ...
                tsec = raw.get("gcode_macro T%d" % n, {})
                m = re.search(r"EXTRUDER=(\w+)", str(tsec.get("gcode", "")))
                ext = m.group(1) if m else ("extruder" if n == 0 else "extruder%d" % n)
            fan = None
            if self.fan_names and idx < len(self.fan_names):
                fan = self.fan_names[idx]
                if not fan.startswith("heater_fan "):
                    fan = "heater_fan " + fan
            else:
                fan = fans_by_heater.get(ext) or "heater_fan hotend_fan%d" % n
            dock_btn = None
            if self.dock_sense == "per_tool":
                dock_btn = self._lookup("gcode_button " + self.dock_sense_template.format(n=n))
                if dock_btn is None:
                    self.errors.append("dock sensor gcode_button %s not found"
                                       % self.dock_sense_template.format(n=n))
            heater_obj = self._lookup(ext)
            if heater_obj is None:
                self.errors.append("T%d: heater object '%s' not found" % (n, ext))
            self.tools.append({
                "n": n,
                "extruder": ext,
                "fan": fan,
                "heater_obj": heater_obj,
                "fan_obj": self._lookup(fan),
                "vars_obj": self._lookup("gcode_macro %s%d" % (self.tool_vars_prefix, n)),
                "tmacro_obj": self._lookup("gcode_macro T%d" % n),
                "dock_obj": dock_btn,
            })
        self._resolve_presets(raw)
        logging.info("btc_dashboard: discovered tools %s", [t["n"] for t in self.tools])

    def _resolve_presets(self, raw):
        self.default_presets, problems = parse_presets(self.default_presets_raw, "presets")
        self.errors.extend(problems)
        known = set(t["n"] for t in self.tools)
        for n in sorted(self.tool_presets_raw):
            if n not in known:
                self.errors.append("presets_t%d: there is no tool T%d" % (n, n))
        for t in self.tools:
            n = t["n"]
            tool_vars = t["vars_obj"].variables if t["vars_obj"] is not None else {}
            if tool_vars.get("temp_presets") is not None:
                where = "%s%d variable_temp_presets" % (self.tool_vars_prefix, n)
                presets, problems = parse_presets(tool_vars["temp_presets"], where)
                source = "tool"
            elif n in self.tool_presets_raw:
                where = "presets_t%d" % n
                presets, problems = parse_presets(self.tool_presets_raw[n], where)
                source = "config"
            else:
                where = "presets"
                presets, problems = list(self.default_presets), []
                source = "default"
            self.errors.extend(problems)
            max_temp = self._heater_max_temp(raw, t["extruder"])
            if max_temp is not None:
                too_hot = [p for p in presets if p["temp"] > max_temp]
                for p in too_hot:
                    self.errors.append("%s: T%d %s %d°C is above %s max_temp %g - not shown"
                                       % (where, n, p["label"], p["temp"], t["extruder"], max_temp))
                presets = [p for p in presets if p["temp"] <= max_temp]
            negative = [p for p in presets if p["temp"] < 0]
            for p in negative:
                self.errors.append("%s: T%d %s has a negative temperature" % (where, n, p["label"]))
            t["presets"] = [p for p in presets if p["temp"] >= 0]
            t["presets_source"] = source

    @staticmethod
    def _heater_max_temp(raw, section):
        try:
            return float(raw.get(section, {}).get("max_temp"))
        except (TypeError, ValueError):
            return None

    def _save_offsets_enabled(self):
        if self.save_offsets_opt == "no":
            return False
        return self.save_vars is not None

    def _handle_ready(self):
        if self.save_offsets_opt == "yes" and self.save_vars is None:
            self.errors.append("save_offsets: yes but no [save_variables] section")
        if self._save_offsets_enabled():
            self._restore_offsets()
        self.reactor.register_timer(self._poll, self.reactor.NOW)
        if self.errors:
            for e in self.errors:
                logging.warning("btc_dashboard: %s", e)

    def _restore_offsets(self):
        allv = getattr(self.save_vars, "allVariables", {}) or {}
        restored = []
        for t in self.tools:
            vo = t["vars_obj"]
            if vo is None:
                continue
            upd = {}
            for axis in ("x", "y", "z"):
                key = "btc_t%d_%soffset" % (t["n"], axis)
                if allv.get(key) is not None:
                    upd[axis + "offset"] = allv[key]
            if upd:
                v = dict(vo.variables)
                v.update(upd)
                vo.variables = v
                restored.append("T%d" % t["n"])
        if restored:
            msg = ("BTC Dashboard: restored saved offsets for %s "
                   "(these override the tool_N.cfg values)" % ", ".join(restored))
            logging.info(msg)
            self.reactor.register_callback(lambda e: self.gcode.respond_info(msg))

    # ------------------------------------------------------------------
    # Toolchange timing: wrap TOOL_PICKUP / TOOL_DROPOFF
    # ------------------------------------------------------------------
    def _wrap_commands(self):
        for cmd, kind in (("TOOL_PICKUP", "pickup"), ("TOOL_DROPOFF", "dropoff")):
            old = self.gcode.register_command(cmd, None)
            if old is None:
                self.errors.append("%s command not found - toolchange log disabled" % cmd)
                continue
            self.gcode.register_command(cmd, self._make_wrapper(kind, old),
                                        desc="BTC %s (timed by BTC Dashboard)" % kind)

    def _print_time(self):
        try:
            return self.toolhead.get_last_move_time()
        except Exception:
            return None

    def _make_wrapper(self, kind, old):
        def wrapper(gcmd):
            if self._busy is not None:
                # dropoff nested inside a pickup: part of the same change
                return old(gcmd)
            target = gcmd.get_int("TOOLNUMBER", 0)
            before = self._active_tool()
            self._busy = {"kind": kind, "to": target, "from": before,
                          "t0": time.time(), "w0": self.reactor.monotonic(),
                          "p0": self._print_time()}
            err = None
            try:
                old(gcmd)
            except Exception as e:
                err = e
            finally:
                self._finish_change(err)
            if err is not None:
                raise err
        return wrapper

    def _finish_change(self, err):
        b, self._busy = self._busy, None
        if b is None:
            return
        wall = self.reactor.monotonic() - b["w0"]
        p1 = self._print_time()
        motion = (p1 - b["p0"]) if (p1 is not None and b["p0"] is not None) else 0.0
        dur = max(wall, motion)
        after = self._active_tool()
        if b["kind"] == "pickup":
            if b["from"] == b["to"]:
                return  # "already on carriage" - not a change
            ok = err is None and after == b["to"]
            label = "%s → T%d" % ("T%d" % b["from"] if b["from"] >= 0 else "empty", b["to"])
        else:
            ok = err is None and self._btc_var("last_dropoff_successful", False) and after < 0
            label = "T%d → dock" % b["to"]
        if err is not None:
            detail = str(err)
        elif ok:
            detail = "verified by carriage sense"
        else:
            detail = ("tool not detected on carriage" if b["kind"] == "pickup"
                      else "tool still on carriage")
        entry = {"time": b["t0"], "kind": b["kind"], "label": label,
                 "from": b["from"], "to": b["to"], "duration": round(dur, 2),
                 "result": "ok" if ok else "fail", "detail": detail}
        self.log.insert(0, entry)
        del self.log[self.log_length:]
        s = self._stats
        s["changes_total"] += 1
        if self._is_printing():
            s["changes_print"] += 1
            if b["kind"] == "pickup" and b["to"] not in s["tools_used_print"]:
                s["tools_used_print"] = s["tools_used_print"] + [b["to"]]
        if not ok:
            s["failed_total"] += 1
        self._time_sum += dur
        self._timed += 1
        s["avg_time"] = round(self._time_sum / self._timed, 2)
        s["last_time"] = round(dur, 2)
        s["last_result"] = entry["result"]

    # ------------------------------------------------------------------
    def _poll(self, eventtime):
        state = self._print_state()
        if state == "printing" and self._last_print_state not in ("printing", "paused"):
            self._stats["changes_print"] = 0
            self._stats["tools_used_print"] = []
        self._last_print_state = state
        return eventtime + 1.0

    def _print_state(self):
        if self.print_stats is None:
            return None
        try:
            return self.print_stats.get_status(self.reactor.monotonic()).get("state")
        except Exception:
            return None

    def _is_printing(self):
        return self._print_state() in ("printing", "paused")

    def _btc_var(self, name, default=None):
        if self.btc_vars is None:
            return default
        return self.btc_vars.variables.get(name, default)

    def _active_tool(self):
        try:
            return int(self._btc_var("tool_current_asperbtc", -1))
        except (TypeError, ValueError):
            return -1

    @staticmethod
    def _num(v, default=0.0):
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Status object
    # ------------------------------------------------------------------
    def get_status(self, eventtime):
        active = self._active_tool()
        tools = []
        for t in self.tools:
            v = t["vars_obj"].variables if t["vars_obj"] is not None else {}
            tm = t["tmacro_obj"].variables if t["tmacro_obj"] is not None else {}
            h = t["heater_obj"].get_status(eventtime) if t["heater_obj"] is not None else {}
            f = t["fan_obj"].get_status(eventtime) if t["fan_obj"] is not None else {}
            docked = None
            if t["dock_obj"] is not None:
                docked = t["dock_obj"].get_status(eventtime).get("state") == "PRESSED"
            spool = tm.get("spool_id")
            tools.append({
                "n": t["n"],
                "name": "T%d" % t["n"],
                "active": t["n"] == active,
                "extruder": t["extruder"],
                "fan": t["fan"],
                "temperature": self._num(h.get("temperature"), None),
                "target": self._num(h.get("target"), 0.0),
                "power": self._num(h.get("power"), 0.0),
                "fan_speed": self._num(f.get("speed"), None),
                "xoffset": self._num(v.get("xoffset")),
                "yoffset": self._num(v.get("yoffset")),
                "zoffset": self._num(v.get("zoffset")),
                "shaper": {"type_x": v.get("shapertype_x"), "freq_x": v.get("shaperfreq_x"),
                           "type_y": v.get("shapertype_y"), "freq_y": v.get("shaperfreq_y")},
                "pressure_advance": self._num(v.get("pressure_advance")),
                "spool_id": spool if spool not in ("", "None") else None,
                "docked": docked,
                "presets": t.get("presets", []),
                "presets_source": t.get("presets_source", "default"),
            })
        carriage = None
        if self.carriage_sense is not None:
            carriage = self.carriage_sense.get_status(eventtime).get("state")
        dockslide = None
        if self.dockslide_vars is not None:
            dv = self.dockslide_vars.variables
            dockslide = {
                "state": DOCKSLIDE_STATES.get(int(dv.get("dockslide_status", 0) or 0), "unknown"),
                "homed": bool(dv.get("dockslide_homed", False)),
                "endstops": {side: o.get_status(eventtime).get("state")
                             for side, o in self.dockslide_endstops},
            }
        return {
            "version": VERSION,
            "config": {
                "tool_count": len(self.tools),
                "dock_sense": self.dock_sense,
                "dockslide": dockslide is not None,
                "spoolman": self.spoolman_opt,
                "save_offsets": self._save_offsets_enabled(),
                "save_variables": self.save_vars is not None,
                "carriage_sense": self.carriage_sense is not None,
                "default_presets": self.default_presets,
            },
            "active_tool": active,
            "carriage": carriage,
            "busy": self._busy is not None,
            "last_dropoff_successful": bool(self._btc_var("last_dropoff_successful", False)),
            "dockslide": dockslide,
            "tools": tools,
            "stats": dict(self._stats),
            "log": list(self.log),
            "errors": list(self.errors),
        }

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def cmd_STATUS(self, gcmd):
        lines = ["BTC Dashboard %s" % VERSION]
        for t in self.tools:
            lines.append("T%d: heater=%s%s fan=%s%s dock=%s" % (
                t["n"], t["extruder"], "" if t["heater_obj"] else " (MISSING)",
                t["fan"], "" if t["fan_obj"] else " (missing)",
                "yes" if t["dock_obj"] else "-"))
            lines.append("    presets (%s): %s" % (
                t.get("presets_source", "default"),
                ", ".join("%s %d" % (p["label"], p["temp"]) for p in t.get("presets", [])) or "none"))
        lines.append("carriage sense: %s" % (self.carriage_sense_name if self.carriage_sense else "not found"))
        lines.append("dockslide: %s" % ("yes" if self.dockslide_vars else "no"))
        lines.append("save offsets: %s" % ("yes" if self._save_offsets_enabled() else "no"))
        for e in self.errors:
            lines.append("WARNING: " + e)
        gcmd.respond_info("\n".join(lines))

    def _tool(self, gcmd):
        n = gcmd.get_int("TOOL")
        for t in self.tools:
            if t["n"] == n:
                return t
        raise gcmd.error("BTC Dashboard: unknown tool %d" % n)

    def cmd_SET_OFFSET(self, gcmd):
        t = self._tool(gcmd)
        vo = t["vars_obj"]
        if vo is None:
            raise gcmd.error("BTC Dashboard: %s%d macro missing" % (self.tool_vars_prefix, t["n"]))
        upd = {}
        for axis in ("X", "Y", "Z"):
            val = gcmd.get_float(axis, None)
            if val is not None:
                upd[axis.lower() + "offset"] = round(val, 4)
        if not upd:
            raise gcmd.error("BTC Dashboard: give at least one of X= Y= Z=")
        v = dict(vo.variables)
        v.update(upd)
        vo.variables = v
        saved = False
        if self._save_offsets_enabled() and gcmd.get_int("SAVE", 1):
            for k, val in upd.items():
                self.gcode.run_script_from_command(
                    "SAVE_VARIABLE VARIABLE=btc_t%d_%s VALUE=%r" % (t["n"], k, val))
            saved = True
        # apply straight away if this tool is on the carriage
        if t["n"] == self._active_tool() and not self._is_printing():
            z_adj = self._num(self._btc_var("gcode_offset_z_adjust", 0.0))
            self.gcode.run_script_from_command(
                "SET_GCODE_OFFSET X=%s Y=%s Z=%s\nSET_GCODE_OFFSET Z_ADJUST=%s" % (
                    v.get("xoffset", 0), v.get("yoffset", 0), v.get("zoffset", 0), z_adj))
        gcmd.respond_info("BTC Dashboard: T%d offsets now X=%s Y=%s Z=%s%s" % (
            t["n"], v.get("xoffset"), v.get("yoffset"), v.get("zoffset"),
            " (saved)" if saved else " (until restart)"))

    def cmd_CLEAR_SAVED(self, gcmd):
        if self.save_vars is None:
            raise gcmd.error("BTC Dashboard: no [save_variables] section")
        allv = getattr(self.save_vars, "allVariables", {}) or {}
        keys = [k for k in allv if re.match(r"^btc_t\d+_[xyz]offset$", k)]
        for k in keys:
            # SAVE_VARIABLE can't delete; store None so restore skips it
            self.gcode.run_script_from_command("SAVE_VARIABLE VARIABLE=%s VALUE=None" % k)
        gcmd.respond_info("BTC Dashboard: cleared %d saved offsets. Restart to reload cfg values." % len(keys))

    def cmd_RESET_STATS(self, gcmd):
        self.log = []
        for k in ("changes_total", "changes_print", "failed_total"):
            self._stats[k] = 0
        self._stats.update({"avg_time": 0.0, "last_time": 0.0, "last_result": "",
                           "tools_used_print": []})
        self._time_sum = 0.0
        self._timed = 0
        gcmd.respond_info("BTC Dashboard: stats cleared")


def load_config(config):
    return BTCDashboard(config)
