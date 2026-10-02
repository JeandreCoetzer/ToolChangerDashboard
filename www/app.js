/* BTC Dashboard web panel - talks to Moonraker over its JSON-RPC websocket.
 * No build step, no dependencies. */
(() => {
  "use strict";
  const VERSION = "0.1.0";
  const DB_NS = "btc_dashboard";
  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------ state
  const S = {
    ws: null, rpcId: 1, pending: new Map(), connected: false,
    klippy: "disconnected",
    status: {},                  // merged printer object status
    spoolmanAvailable: false,
    spools: new Map(),           // id -> spool
    local: {},                   // per-tool material/colour when no Spoolman
    settings: { cols: "auto", strip: true, log: true, confirm: false },
    openTool: null, tileCount: -1, renderQueued: false,
  };

  // ------------------------------------------------------------------ rpc
  function wsUrl() {
    const q = new URLSearchParams(location.search).get("moonraker");
    if (q) return (q.startsWith("ws") ? q : `ws://${q}`) + (q.includes("/websocket") ? "" : "/websocket");
    return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/websocket`;
  }

  function rpc(method, params) {
    return new Promise((resolve, reject) => {
      if (!S.ws || S.ws.readyState !== 1) return reject(new Error("Not connected to Moonraker"));
      const id = S.rpcId++;
      S.pending.set(id, { resolve, reject });
      S.ws.send(JSON.stringify({ jsonrpc: "2.0", method, params: params || {}, id }));
    });
  }

  function connect() {
    const ws = new WebSocket(wsUrl());
    S.ws = ws;
    ws.onopen = async () => {
      S.connected = true;
      try {
        await rpc("server.connection.identify", { client_name: "btc-dashboard", version: VERSION, type: "web", url: "https://github.com/" });
      } catch (e) { /* older Moonraker */ }
      await loadSettings();
      await refreshServer();
    };
    ws.onmessage = (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.id && S.pending.has(msg.id)) {
        const p = S.pending.get(msg.id); S.pending.delete(msg.id);
        msg.error ? p.reject(new Error(msg.error.message || "Error")) : p.resolve(msg.result);
        return;
      }
      switch (msg.method) {
        case "notify_status_update": merge(S.status, msg.params[0]); queueRender(); break;
        case "notify_klippy_ready": refreshServer(); break;
        case "notify_klippy_shutdown": case "notify_klippy_disconnected":
          S.klippy = msg.method === "notify_klippy_shutdown" ? "shutdown" : "disconnected"; queueRender(); break;
        case "notify_active_spool_set": queueRender(); break;
      }
    };
    ws.onclose = () => {
      S.connected = false; S.klippy = "disconnected";
      for (const p of S.pending.values()) p.reject(new Error("Connection closed"));
      S.pending.clear(); queueRender();
      setTimeout(connect, 3000);
    };
  }

  async function refreshServer() {
    try {
      const info = await rpc("server.info");
      S.klippy = info.klippy_state;
      S.spoolmanAvailable = (info.components || []).includes("spoolman");
      if (S.klippy !== "ready") { queueRender(); setTimeout(refreshServer, 2000); return; }
      const objs = await rpc("printer.objects.list");
      const want = { print_stats: ["state"], toolhead: ["homed_axes"] };
      if (objs.objects.includes("btc_dashboard")) want.btc_dashboard = null;
      const res = await rpc("printer.objects.subscribe", { objects: want });
      S.status = res.status;
      if (useSpoolman()) loadSpools();
      queueRender();
    } catch (e) { toast(e.message, true); }
  }

  function merge(dst, src) {
    for (const k of Object.keys(src)) {
      const v = src[k];
      if (v && typeof v === "object" && !Array.isArray(v) && dst[k] && typeof dst[k] === "object") merge(dst[k], v);
      else dst[k] = v;
    }
  }

  async function gcode(script) {
    try { await rpc("printer.gcode.script", { script }); return true; }
    catch (e) { toast(e.message, true); return false; }
  }

  // ------------------------------------------------------------------ db
  async function dbGet(key, fallback) {
    try { return (await rpc("server.database.get_item", { namespace: DB_NS, key })).value; }
    catch { return fallback; }
  }
  const dbSet = (key, value) => rpc("server.database.post_item", { namespace: DB_NS, key, value }).catch((e) => toast(e.message, true));

  async function loadSettings() {
    Object.assign(S.settings, await dbGet("settings", {}));
    S.local = await dbGet("tools", {}) || {};
  }

  // ------------------------------------------------------------------ spoolman
  const btc = () => S.status.btc_dashboard;
  function useSpoolman() {
    const mode = btc()?.config?.spoolman || "auto";
    return mode === "yes" || (mode === "auto" && S.spoolmanAvailable);
  }
  async function loadSpools() {
    try {
      const r = await rpc("server.spoolman.proxy", { request_method: "GET", path: "/v1/spool", query: "allow_archived=false", use_v2_response: true });
      const list = (r && r.response) || [];
      S.spools = new Map(list.map((s) => [s.id, s]));
      queueRender();
    } catch (e) { /* spoolman offline: fall back to local info */ }
  }

  // ------------------------------------------------------------------ helpers
  function toolLook(t) {
    const sp = t.spool_id != null ? S.spools.get(Number(t.spool_id)) : null;
    if (useSpoolman() && sp) {
      const f = sp.filament || {};
      return { color: f.color_hex ? "#" + f.color_hex.replace(/^#/, "").slice(0, 6) : "#777",
        material: [f.material, f.name].filter(Boolean).join(" ") || "Spool #" + sp.id,
        spool: `Spool #${sp.id}` + (sp.remaining_weight != null ? ` · ${Math.round(sp.remaining_weight)} g left` : "") };
    }
    const l = S.local["T" + t.n] || {};
    return { color: l.color || "#777", material: l.material || (t.spool_id != null ? "Spool #" + t.spool_id : "No filament set"),
      spool: t.spool_id != null ? "Spool #" + t.spool_id : "No spool" };
  }
  function toolKind(t) { return t.active ? "active" : (t.target > 0 ? "standby" : "docked"); }
  const fmtT = (v) => (v == null ? "--" : Math.round(v));
  const fmtFan = (v) => (v == null ? "--" : Math.round(v * 100) + "%");
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const printing = () => ["printing", "paused"].includes(S.status.print_stats?.state);

  function hotendSvg(color, kind, cls) {
    const block = kind === "active" ? "#d84315" : kind === "standby" ? "#b86b2a" : "#4a4f57";
    const glow = kind === "active" ? "rgba(255,112,67,.55)" : kind === "standby" ? "rgba(255,152,0,.3)" : "none";
    const fins = [14, 20, 26, 32, 38].map((y) => `<rect x="14" y="${y}" width="32" height="3" rx="1" fill="#8b9098"/>`).join("");
    return `<svg class="${cls}" viewBox="0 0 60 80" aria-hidden="true">
      <rect x="28" y="0" width="4" height="8" fill="${color}"/><rect x="21" y="6" width="18" height="6" rx="2" fill="${color}"/>
      <rect x="24" y="12" width="12" height="30" fill="#5f646c"/>${fins}
      <rect x="27" y="42" width="6" height="8" fill="#b7bcc4"/>
      <rect x="16" y="50" width="28" height="14" rx="2" fill="${block}"/>
      <path d="M24 64h12l-4 8h-4z" fill="#c9a24a"/><circle cx="30" cy="75" r="5" fill="${glow}"/></svg>`;
  }
  const fanSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="2"/><path d="M12 10c0-4 1-7 4-7s3 5-2 8M14 12c4 0 7 1 7 4s-5 3-8-2M12 14c0 4-1 7-4 7s-3-5 2-8M10 12c-4 0-7-1-7-4s5-3 8 2"/></svg>`;

  // ------------------------------------------------------------------ render
  function queueRender() {
    if (S.renderQueued) return;
    S.renderQueued = true;
    requestAnimationFrame(() => { S.renderQueued = false; render(); });
  }

  function render() {
    const b = btc();
    const banner = $("banner");
    if (!S.connected) { showBanner("Connecting to Moonraker…", "info"); }
    else if (S.klippy !== "ready") { showBanner(`Klipper is ${S.klippy}.`, "info"); }
    else if (!b) { showBanner("BTC Dashboard add-on not found. Add [include btc_dashboard.cfg] to printer.cfg and restart Klipper.", ""); }
    else if (b.errors && b.errors.length) { showBanner(b.errors.map(esc).join("<br>"), ""); }
    else banner.hidden = true;

    if (!b) { $("grid").innerHTML = ""; $("grid").dataset.ids = ""; $("strip").innerHTML = ""; $("active-chip").hidden = true; return; }
    const tools = b.tools || [];
    const locked = printing() || b.busy;

    // header chip
    const chip = $("active-chip");
    chip.hidden = false;
    chip.className = "chip" + (b.active_tool < 0 ? " empty" : "");
    chip.textContent = b.active_tool < 0 ? "CARRIAGE EMPTY" : `T${b.active_tool} ACTIVE`;

    // status strip
    const strip = $("strip");
    strip.hidden = !S.settings.strip;
    const cs = b.carriage;
    const csMismatch = cs && ((cs === "PRESSED") !== (b.active_tool >= 0));
    const st = b.stats || {};
    const parts = [];
    if (b.config.carriage_sense) parts.push(`<span><span class="dot ${csMismatch ? "err" : cs === "PRESSED" ? "ok" : ""}"></span>Carriage <b>${cs === "PRESSED" ? "locked" : "empty"}</b>${csMismatch ? " · mismatch" : ""}</span>`);
    if (b.dockslide) parts.push(`<span>Dockslide <b>${esc(b.dockslide.state)}</b>${b.dockslide.homed ? "" : " (not homed)"}</span>`);
    parts.push(printing() ? `<span>Changes this print <b class="mono">${st.changes_print ?? 0}</b></span>` : `<span>Changes <b class="mono">${st.changes_total ?? 0}</b></span>`);
    if (b.busy) parts.push(`<span class="grow"></span><span><span class="dot warn"></span>Changing…</span>`);
    else if (st.last_result) parts.push(`<span class="grow"></span><span>Last <b class="mono">${(st.last_time ?? 0).toFixed(1)} s</b> <span style="color:var(--${st.last_result === "ok" ? "ok" : "err"})">${st.last_result === "ok" ? "OK" : "FAILED"}</span></span>`);
    strip.innerHTML = parts.join("");

    // grid
    const grid = $("grid");
    const cols = S.settings.cols === "auto" ? (tools.length <= 4 ? Math.max(tools.length, 1) : tools.length === 6 || tools.length === 5 ? 3 : 4) : Number(S.settings.cols);
    grid.style.setProperty("--cols", cols);
    // Tiles are built once, then patched in place so a click is never lost
    // to a re-render in the middle of it.
    const ids = tools.map((t) => t.n).join(",");
    if (grid.dataset.ids !== ids) {
      grid.dataset.ids = ids;
      grid.innerHTML = tools.map((t) => `<button type="button" role="listitem" class="tile" data-tool="${t.n}">
        <span class="top"><span class="id">T${t.n}</span><span class="state-dot"></span></span>
        <span class="art"></span>
        <span class="mat"><span class="swatch"></span><span class="mat-txt"></span></span>
        <span class="nums"><span class="temp"></span><span class="fan">${fanSvg}<span class="fan-txt"></span></span></span>
      </button>`).join("");
    }
    tools.forEach((t) => {
      const el = grid.querySelector(`[data-tool="${t.n}"]`); if (!el) return;
      const kind = toolKind(t), look = toolLook(t), hot = t.target > 0;
      el.className = "tile " + kind;
      el.setAttribute("aria-label", `T${t.n}, ${look.material}, ${kind}, ${fmtT(t.temperature)} degrees. Open tool options`);
      const dot = el.querySelector(".state-dot");
      dot.className = "state-dot " + kind + (t.docked === true ? " sensed" : "");
      dot.title = kind + (t.docked === true ? ", in dock" : t.docked === false ? ", not in dock" : "");
      const artKey = look.color + kind, art = el.querySelector(".art");
      if (art.dataset.k !== artKey) { art.dataset.k = artKey; art.innerHTML = hotendSvg(look.color, kind, "hotend"); }
      el.querySelector(".swatch").style.background = look.color;
      el.querySelector(".mat-txt").textContent = look.material;
      const tp = el.querySelector(".temp");
      tp.className = "temp" + (hot ? "" : " cold");
      tp.textContent = hot ? `${fmtT(t.temperature)}/${fmtT(t.target)}°` : `${fmtT(t.temperature)}° off`;
      el.querySelector(".fan-txt").textContent = fmtFan(t.fan_speed);
    });

    // actions
    $("btn-dockslide").hidden = !b.dockslide;
    const drop = $("btn-dropoff");
    drop.hidden = b.active_tool < 0;
    drop.textContent = `Drop off T${b.active_tool}`;
    document.querySelectorAll("#actions .btn").forEach((el) => { el.disabled = locked; });

    // log
    $("log-wrap").hidden = !S.settings.log;
    $("log").innerHTML = (b.log || []).slice(0, 12).map((e) => {
      const d = new Date(e.time * 1000);
      return `<li><span>${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</span><span>${esc(e.label)}</span>
        <span>${e.duration.toFixed(1)} s</span><span title="${esc(e.detail)}">${esc(e.detail)}</span><span class="res ${e.result}">${e.result === "ok" ? "OK" : "FAIL"}</span></li>`;
    }).join("") || `<li><span></span><span>No toolchanges yet</span></li>`;

    if (S.openTool != null) updateToolDialog(false);
  }

  function showBanner(html, cls) { const el = $("banner"); el.hidden = false; el.className = "banner " + cls; el.innerHTML = html; }

  // ------------------------------------------------------------------ tool dialog
  function currentTool() { return (btc()?.tools || []).find((t) => t.n === S.openTool); }

  function openToolDialog(n) {
    S.openTool = n;
    updateToolDialog(true);
    const d = $("tool-dialog");
    if (!d.open) d.showModal();
  }

  function updateToolDialog(first) {
    const t = currentTool(); const b = btc();
    if (!t || !b) return;
    const kind = toolKind(t), look = toolLook(t);
    $("td-title").textContent = `T${t.n} · ${look.material}`;
    $("td-swatch").style.background = look.color;
    $("td-hero").innerHTML = hotendSvg(look.color, kind, "");
    const dockTxt = t.docked === true ? " · sensed in dock" : t.docked === false ? " · not in dock!" : "";
    $("td-state").textContent = (kind === "active" ? "On carriage" : kind === "standby" ? "Docked · standby" : "Docked · off") + (kind === "active" ? "" : dockTxt);
    $("td-state").style.color = kind === "active" ? "var(--accent)" : kind === "standby" ? "var(--warn)" : "";
    $("td-temp").textContent = `${fmtT(t.temperature)} / ${fmtT(t.target)} °C`;
    $("td-fan").textContent = fmtFan(t.fan_speed);
    $("td-heater").textContent = t.extruder;
    const sh = t.shaper || {};
    $("td-shaper").textContent = sh.type_x ? `${sh.type_x} ${sh.freq_x} / ${sh.type_y} ${sh.freq_y} Hz` : "--";

    const locked = printing() || b.busy;
    const sel = $("td-select");
    sel.textContent = t.active ? "On carriage" : `Select T${t.n}`;
    sel.disabled = t.active || locked;
    sel.title = locked && !t.active ? "Tool changes are locked while printing" : "";
    $("td-dropoff").hidden = !t.active;
    $("td-dropoff").disabled = locked;

    if (!first) return;   // don't overwrite what the user is typing
    const spoolTemp = spoolPresetTemp(t);
    $("td-presets").innerHTML = [["Off", 0, "", true]].concat(toolPresets(t).map((p) => [p.label, p.temp, "", false]))
      .concat(spoolTemp ? [["Spool", spoolTemp, " spool", false]] : [])
      .map(([l, v, cls, isOff]) =>
        `<button type="button" class="btn small outline${cls}" data-temp="${v}">${esc(l)}${isOff ? "" : " " + v}</button>`).join("");
    const src = t.presets_source || "default";
    $("td-presetsrc").textContent = src === "tool" ? `Presets from variable_temp_presets in _VARIABLES_T${t.n}`
      : src === "config" ? `Presets from presets_t${t.n} in btc_dashboard.cfg`
        : `Presets from presets in btc_dashboard.cfg (add presets_t${t.n} for this tool)`;
    $("td-target").value = Math.round(t.target || 0);
    $("td-ox").value = t.xoffset; $("td-oy").value = t.yoffset; $("td-oz").value = t.zoffset;
    $("td-offhint").textContent = b.config.save_offsets
      ? "Saved to save_variables and restored after restart (overrides tool_" + t.n + ".cfg)."
      : "Applies until restart. Add [save_variables] to keep changes, or copy them into tool_" + t.n + ".cfg.";
    ["td-ox", "td-oy", "td-oz", "td-saveoff"].forEach((id) => { $(id).disabled = printing(); });

    const sm = useSpoolman();
    $("td-spoolman-row").hidden = !sm;
    $("td-local-row").hidden = sm;
    if (sm) {
      const opts = [`<option value="">No spool</option>`].concat([...S.spools.values()].map((s) => {
        const f = s.filament || {};
        return `<option value="${s.id}" ${Number(t.spool_id) === s.id ? "selected" : ""}>#${s.id} ${esc([f.vendor?.name, f.material, f.name].filter(Boolean).join(" "))}</option>`;
      }));
      $("td-spool").innerHTML = opts.join("");
    } else {
      const l = S.local["T" + t.n] || {};
      $("td-material").value = l.material || "";
      $("td-color").value = /^#[0-9a-f]{6}$/i.test(l.color || "") ? l.color : "#777777";
    }
  }

  // add-ons older than 0.2.0 do not publish presets
  const FALLBACK_PRESETS = [{ label: "Standby", temp: 150 }, { label: "PLA", temp: 215 }, { label: "PETG", temp: 240 }, { label: "ABS", temp: 255 }];
  function toolPresets(t) { return t.presets || btc()?.config?.default_presets || FALLBACK_PRESETS; }
  function spoolPresetTemp(t) {
    const sp = useSpoolman() && t.spool_id != null ? S.spools.get(Number(t.spool_id)) : null;
    const temp = sp?.filament?.settings_extruder_temp;
    return typeof temp === "number" && temp > 0 ? Math.round(temp) : null;
  }

  // ------------------------------------------------------------------ events
  $("grid").addEventListener("click", (e) => {
    const tile = e.target.closest(".tile"); if (tile) openToolDialog(Number(tile.dataset.tool));
  });
  $("tool-dialog").addEventListener("close", () => { S.openTool = null; });
  $("td-presets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-temp]"); if (!b) return;
    $("td-target").value = b.dataset.temp; setTemp();
  });
  $("td-settemp").addEventListener("click", setTemp);
  function setTemp() {
    const t = currentTool(); if (!t) return;
    const v = Math.max(0, Math.min(350, Math.round(+$("td-target").value || 0)));
    gcode(`SET_HEATER_TEMPERATURE HEATER=${t.extruder} TARGET=${v}`).then((ok) => ok && toast(`T${t.n} target ${v} °C`));
  }
  $("td-saveoff").addEventListener("click", () => {
    const t = currentTool(); if (!t) return;
    const x = +$("td-ox").value, y = +$("td-oy").value, z = +$("td-oz").value;
    if ([x, y, z].some((v) => isNaN(v) || Math.abs(v) > 20)) return toast("Offsets must be numbers within ±20 mm", true);
    gcode(`BTC_DASHBOARD_SET_OFFSET TOOL=${t.n} X=${x} Y=${y} Z=${z}`).then((ok) => ok && toast(`T${t.n} offsets saved`));
  });
  $("td-setspool").addEventListener("click", async () => {
    const t = currentTool(); if (!t) return;
    const id = $("td-spool").value;
    const val = id === "" ? "None" : Number(id);
    let script = `SET_GCODE_VARIABLE MACRO=T${t.n} VARIABLE=spool_id VALUE=${val}`;
    if (btc().config.save_variables) script += `\nSAVE_VARIABLE VARIABLE=t${t.n}__spool_id VALUE=${val}`;
    if (t.active) script += id === "" ? "\nCLEAR_ACTIVE_SPOOL" : `\nSET_ACTIVE_SPOOL ID=${val}`;
    if (await gcode(script)) toast(`T${t.n} spool ${id === "" ? "cleared" : "#" + id}`);
  });
  $("td-setlocal").addEventListener("click", () => {
    const t = currentTool(); if (!t) return;
    S.local["T" + t.n] = { material: $("td-material").value.trim(), color: $("td-color").value };
    dbSet("tools", S.local); queueRender(); toast(`T${t.n} filament saved`);
  });
  $("td-select").addEventListener("click", async () => {
    const t = currentTool(); if (!t) return;
    if (S.settings.confirm && !confirm(`Change to T${t.n}?`)) return;
    $("tool-dialog").close();
    if (await gcode(`T${t.n}`)) toast(`Changed to T${t.n}`);
  });
  $("td-dropoff").addEventListener("click", () => { const t = currentTool(); if (t) { $("tool-dialog").close(); gcode(`TOOL_DROPOFF TOOLNUMBER=${t.n}`); } });

  $("actions").addEventListener("click", (e) => {
    const el = e.target.closest("button"); if (!el || el.disabled) return;
    if (el.id === "btn-dropoff") return gcode(`TOOL_DROPOFF TOOLNUMBER=${btc().active_tool}`);
    if (el.dataset.gcode) gcode(el.dataset.gcode);
  });
  $("btn-collapse").addEventListener("click", (e) => {
    const btn = e.currentTarget, open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open)); $("body").hidden = open;
  });

  // settings
  $("btn-settings").addEventListener("click", () => {
    const s = S.settings;
    $("sd-cols").value = s.cols;
    $("sd-strip").checked = s.strip; $("sd-log").checked = s.log; $("sd-confirm").checked = s.confirm;
    $("settings-dialog").showModal();
  });
  $("sd-save").addEventListener("click", () => {
    Object.assign(S.settings, { cols: $("sd-cols").value, strip: $("sd-strip").checked,
      log: $("sd-log").checked, confirm: $("sd-confirm").checked });
    dbSet("settings", S.settings); $("settings-dialog").close(); queueRender();
  });

  let toastTimer;
  function toast(msg, err) {
    const el = $("toast"); el.textContent = msg; el.className = "toast show" + (err ? " err" : "");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.className = "toast"; }, 3500);
  }

  setInterval(() => { if (S.connected && useSpoolman()) loadSpools(); }, 60000);
  queueRender();
  connect();
})();
