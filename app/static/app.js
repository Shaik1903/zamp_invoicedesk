"use strict";
// ---------- helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => (v == null ? "—" : (v < 0 ? "-$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const money0 = (v) => "$" + Math.round(v || 0).toLocaleString("en-US");
const ago = (ts) => new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const day = (iso) => { const d = new Date(iso + "T00:00:00"); return isNaN(d) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }); };
const STAGE_LABELS = { intake: "Intake", extract: "Read (AI)", validate: "Validate document", vendor: "Vendor check", po_match: "PO match", three_way: "Three-way match", duplicates: "Duplicate check", decision: "Decision" };
const STEP_LABELS = { intake: "Intake", extract: "Read (AI)", validate: "Validate", vendor: "Vendor", po_match: "PO match", three_way: "Three-way", duplicates: "Duplicates", decision: "Decision" };
const STAGES = Object.keys(STAGE_LABELS);
const GONE_HTML = `<div class="card verdict v-REJECT"><span class="v-word dec-REJECT">Not found</span>
  <p class="v-text" style="margin-top:14px">This run is no longer on the server (a restart clears the demo data). Start it again from <a href="#/new">New run</a>.</p></div>`;
const DECISION_WORD = { APPROVE: "Approved", HOLD: "On hold", REJECT: "Rejected" };
const DEC_COLOR = { APPROVE: "#0e9f6e", HOLD: "#d97706", REJECT: "#dc2626" };

const svg = (d, w = 2.4) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const I = {
  check: svg('<path d="M5 12l5 5L20 7"/>', 3), bang: svg('<path d="M12 7v6"/><path d="M12 17h.01"/>', 3), dash: svg('<path d="M7 12h10"/>', 3),
  pause: svg('<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>', 2.4),
  x: svg('<path d="M6 6l12 12M18 6L6 18"/>', 3), arrow: svg('<path d="M5 12h14M13 6l6 6-6 6"/>', 2.2), chev: svg('<path d="M9 6l6 6-6 6"/>', 2.4),
  upload: svg('<path d="M12 16V4M6 10l6-6 6 6"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>', 2.2),
  info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>', 2.2), copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>', 2),
  eye: svg('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>', 2), cols: svg('<rect x="3" y="4" width="8" height="16" rx="1.5"/><rect x="13" y="4" width="8" height="16" rx="1.5"/>', 2),
};
const DEC_ICON = { APPROVE: I.check, HOLD: I.pause, REJECT: I.x };
const STATUS_ICON = { pending: "", running: `<span class="spin"></span>`, pass: I.check, warn: I.bang, fail: I.bang, skip: I.dash };

const PALETTE = ["#4f46e5", "#7c3aed", "#0369a1", "#0f766e", "#15803d", "#b45309", "#be123c", "#9333ea", "#0e7490", "#c2410c"];
function avatar(name, cls = "") {
  const n = String(name || "?"), words = n.replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  const ini = ((words[0] || "?")[0] + (words[1] ? words[1][0] : "")).toUpperCase();
  let hsh = 0; for (const c of n) hsh = (hsh * 31 + c.charCodeAt(0)) >>> 0;
  return `<span class="avatar ${cls}" style="background:${PALETTE[hsh % PALETTE.length]}">${esc(ini)}</span>`;
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
}
function stream(path, onData, onGone) {
  const es = new EventSource(path);
  es.onmessage = (e) => onData(JSON.parse(e.data));
  es.addEventListener("done", () => es.close());
  // The server sends a named "error" event (with data) when the run or batch no longer exists, e.g. after a
  // restart cleared the demo data. Network blips fire a plain error event (no data): EventSource retries those.
  es.addEventListener("error", (e) => { if (e.data !== undefined) { es.close(); if (onGone) onGone(); } });
  return () => es.close();
}
function decChip(d, code) {
  return d ? `<span class="pill dec-${d}">${DECISION_WORD[d]}${code ? ` <span class="mono" style="font-size:11px;opacity:.8">${esc(code)}</span>` : ""}</span>`
    : `<span class="pill dec-WORK">Working</span>`;
}
function segs(statuses) { return `<div class="segs">${statuses.map((s) => `<span class="seg st-${s}"></span>`).join("")}</div>`; }
function toast(el, msg) { el.prepend(h(`<p class="badge bad">${I.info.replace("<svg", '<svg width="16" height="16"')}${esc(msg)}</p>`)); }
function spark(pts, color, fill = true) {
  if (pts.length < 2) pts = [0, ...pts, ...(pts.length ? [] : [0])];
  const w = 200, ht = 34, mx = Math.max(...pts), mn = Math.min(...pts);
  const d = pts.map((v, i) => `${((i / (pts.length - 1)) * w).toFixed(1)},${(ht - 4 - ((v - mn) / (mx - mn || 1)) * (ht - 8)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${ht}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>
    ${fill ? `<polygon points="0,${ht} ${d} ${w},${ht}" fill="${color}" opacity=".12"/>` : ""}</svg>`;
}
function hbars(rows, color, fmt) {
  if (!rows.length) return `<p class="muted">Nothing stopped yet.</p>`;
  const mx = Math.max(...rows.map((r) => r[1]));
  return `<div class="hbars">${rows.map(([l, v]) => `<div class="r"><span title="${esc(l)}">${esc(l)}</span><div class="track"><div class="fill" style="width:${(v / mx) * 100}%;background:${color}"></div></div><b>${fmt(v)}</b></div>`).join("")}</div>`;
}

// ---------- router ----------
const VIEWS = {};
let cleanup = [];
function route() {
  cleanup.forEach((f) => f()); cleanup = [];
  const [, name = "new", arg] = location.hash.split("/");
  const navName = name === "batch" || name === "run" ? "new" : name;
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navName));
  const view = $("#view"); view.innerHTML = "";
  (VIEWS[name] || VIEWS.new)(view, arg);
  window.scrollTo(0, 0);
}
addEventListener("hashchange", route);

// Page data is drawn from memory at once and refreshed in the background, so switching pages never starts blank.
const CACHE = {};
function cachedApi(path, onFresh) {
  const had = path in CACHE;
  const req = api(path).then((d) => {
    const changed = !had || JSON.stringify(d) !== JSON.stringify(CACHE[path]);
    CACHE[path] = d;
    if (had && changed && onFresh) onFresh(d);
    return d;
  });
  if (!had) return req;
  req.catch(() => {});
  return Promise.resolve(CACHE[path]);
}
function prefetch() {
  for (const p of ["/api/fixtures", "/api/assumptions", "/api/reference", "/api/runs"]) {
    if (!(p in CACHE)) api(p).then((d) => { if (!(p in CACHE)) CACHE[p] = d; }).catch(() => {});
  }
}
addEventListener("DOMContentLoaded", async () => {
  route();
  prefetch();
  try {
    const hl = await api("/api/health");
    // Only offline mode is announced: then the answers come from the test key, and people must know that.
    $("#engine").innerHTML = hl.offline ? `<span class="engine off"><span class="live"></span>Offline mode: answers come from the test key, not AI</span>` : "";
  } catch { /* health is informational */ }
});

// fetch() cannot report upload progress; XMLHttpRequest can, so uploads of real files go through here.
function postForm(url, form, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total, false); };
    x.upload.onload = () => onProgress(1, 1, true);
    x.onload = () => {
      let body = {};
      try { body = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) resolve(body); else reject(new Error(body.detail || x.statusText || "Upload failed"));
    };
    x.onerror = () => reject(new Error("Upload failed. Check your connection and try again."));
    x.send(form);
  });
}
async function startBatch(form, onProgress) {
  form.append("reextract", $("#reextract")?.checked ? "true" : "false");
  const r = onProgress ? await postForm("/api/batches", form, onProgress) : await api("/api/batches", { method: "POST", body: form });
  location.hash = r.run_ids.length === 1 ? `#/run/${r.run_ids[0]}` : `#/batch/${r.batch_id}`;
}

// ---------- New run ----------
const DEMO_BLURB = { "Happy path": "A clean digital invoice that passes all eight checks.",
  EC1: "The second invoice on a blanket PO would push it past its limit.",
  EC2: "An invoice already paid, rescanned and sent again under a new number.",
  EC3: "A perfect invoice, except it asks for payment to a new bank account.",
  EC4: "A crumpled phone photo with no PO and tax included in the prices." };
VIEWS.new = async (el) => {
  el.append(h(`
    <section class="intro">
      <div class="card intro-copy">
        <h1>Invoices in. <em>Decisions</em> out, with every reason shown.</h1>
        <p>Drop one invoice or a whole inbox. AI reads each document, digital or scanned, photographed or handwritten. Fixed, tested rules then decide approve, hold or reject.</p>
        <div class="flow">${STAGES.map((s) => `<span>${STEP_LABELS[s]}</span>`).join("<i></i>")}</div>
        <div class="principle-inline">${I.info.replace("<svg", '<svg width="16" height="16"')}<span><b>AI reads, code decides.</b> Every amount is checked against the document itself.</span></div>
      </div>
      <div class="drop-side">
        <section class="drop" id="drop" tabindex="0" role="button" aria-label="Upload invoices">
          <input type="file" id="pick" multiple accept=".pdf,.jpg,.jpeg,.png" hidden>
          <div class="drop-body" id="dropBody">
            <span class="drop-icon" aria-hidden="true">${I.upload.replace("<svg", '<svg width="24" height="24"')}</span><b>Drop invoices here</b>
            <span class="muted">or click to choose files. PDF, JPG or PNG, up to 100 at once.</span>
          </div>
        </section>
        <label class="check-opt"><input type="checkbox" id="reextract"> Read again with AI instead of using cached results</label>
        <div id="fresh"></div>
      </div>
    </section>
    <h2>Prepared demo runs</h2><div class="cards" id="demo"></div>
    <h2>Run any test scenario</h2>
    <div class="card any"><select id="any" aria-label="Test scenario"></select><button class="btn primary" id="runAny">Run scenario ${I.arrow}</button></div>`));
  const drop = $("#drop"), pick = $("#pick"), body = $("#dropBody"), idle = body.innerHTML;
  const mb = (b) => (b / 1048576).toFixed(1);
  // While files upload, the drop zone shows progress and ignores new drops: without it the page looks frozen.
  let uploading = false;
  const progress = (n, loaded, total, sent) => {
    const pct = total ? Math.round((loaded / total) * 100) : 0;
    body.innerHTML = `<span class="spin" style="width:28px;height:28px;border-width:3px"></span>
      <b>${sent ? "Starting the batch..." : `Uploading ${n} invoice${n > 1 ? "s" : ""}...`}</b>
      <span class="muted">${sent ? "Files received. Opening the live view." : `${mb(loaded)} of ${mb(total)} MB · ${pct}%`}</span>
      <span class="upbar"><span style="width:${sent ? 100 : pct}%"></span></span>`;
  };
  const send = async (files) => {
    if (uploading) return;
    if (!files.length) return;
    uploading = true;
    drop.classList.add("busy");
    const total = [...files].reduce((a, x) => a + x.size, 0);
    progress(files.length, 0, total, false);
    const f = new FormData(); [...files].forEach((x) => f.append("files", x, x.name));
    try { await startBatch(f, (loaded, t, sent) => progress(files.length, sent ? total : loaded, sent ? total : t, sent)); }
    catch (e) { toast(el, e.message); }
    finally { uploading = false; drop.classList.remove("busy"); body.innerHTML = idle; pick.value = ""; }
  };
  drop.onclick = () => { if (!uploading) pick.click(); };
  drop.onkeydown = (e) => { if (!uploading && (e.key === "Enter" || e.key === " ")) pick.click(); };
  pick.onchange = () => send(pick.files);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); send(e.dataTransfer.files); };

  freshControl($("#fresh"));
  const fx = await cachedApi("/api/fixtures");
  const byFile = Object.fromEntries(fx.files.map((m) => [m.file, m]));
  const demo = $("#demo");
  for (const d of fx.demo) {
    const m = byFile[d.files[0]];
    const [tag, rest] = d.label.includes(": ") ? d.label.split(": ") : [d.label, ""];
    const head = rest ? rest[0].toUpperCase() + rest.slice(1) : m.title, blurb = DEMO_BLURB[tag] || m.title;
    const card = h(`<button class="card demo"><span class="go">${I.arrow.replace("<svg", '<svg width="18" height="18"')}</span>
      <span class="tag">${esc(tag.replace(/^EC(\d)/, "Edge case $1"))}</span><b>${esc(head)}</b><span class="muted">${esc(blurb)}</span>
      <span>${decChip(m.expected.alone.decision, m.expected.alone.reasons[0])}</span></button>`).firstElementChild;
    card.onclick = () => { const f = new FormData(); f.append("fixture", d.files[0]); startBatch(f).catch((e) => toast(el, e.message)); };
    demo.append(card);
  }
  const cls = { APPROVE: "a", HOLD: "h", REJECT: "r" };
  const all = h(`<button class="card demo big">
    <div class="mini-tiles" aria-hidden="true">${fx.files.map((m) => `<i class="${cls[m.expected.in_batch.decision] || ""}"></i>`).join("")}</div>
    <div><span class="tag">Batch</span><br><b>Full inbox: ${fx.files.length} invoices</b><br>
    <span class="muted">Every scenario at once: digital, scanned, faxed, photographed and handwritten. Read in parallel, decided in order.</span></div>
    <span class="go">${I.arrow.replace("<svg", '<svg width="22" height="22"')}</span></button>`).firstElementChild;
  all.onclick = () => { const f = new FormData(); f.append("fixture_set", "all"); startBatch(f).catch((e) => toast(el, e.message)); };
  demo.append(all);
  $("#any").innerHTML = fx.files.map((m) => `<option value="${esc(m.file)}">${String(m.id).padStart(2, "0")} · ${esc(m.title)} (${esc(m.kind.replace(/_/g, " "))})</option>`).join("");
  $("#runAny").onclick = () => { const f = new FormData(); f.append("fixture", $("#any").value); startBatch(f).catch((e) => toast(el, e.message)); };
};

// Start fresh: forgets every processed invoice. Vendors, POs, goods received and the policy stay.
function freshControl(box, done) {
  const idle = () => {
    box.innerHTML = `<div class="fresh"><button class="btn danger" data-act="ask">Start fresh</button>
      <span class="muted">Clear every processed invoice so the same files can be run again.</span></div>`;
    box.querySelector("[data-act=ask]").onclick = ask;
  };
  const ask = () => {
    box.innerHTML = `<div class="card fresh-confirm"><b>Clear all processed invoices?</b>
      <p class="muted">Every run and batch is removed, and the ledger entries they made are taken back off the POs. Vendors, purchase orders, goods received and the policy stay as they are.</p>
      <div class="row"><button class="btn danger-solid" data-act="go">Clear invoices</button><button class="btn" data-act="cancel">Cancel</button><span class="muted" data-act="msg"></span></div></div>`;
    box.querySelector("[data-act=cancel]").onclick = idle;
    box.querySelector("[data-act=go]").onclick = async () => {
      try {
        await api("/api/invoices/clear", { method: "POST" });
        delete CACHE["/api/runs"]; delete CACHE["/api/reference"];
        box.innerHTML = `<p class="badge ok">${I.check.replace("<svg", '<svg width="15" height="15"')}Cleared. Ready for new invoices.</p>`;
        setTimeout(idle, 4000);
        if (done) done();
      } catch (e) { box.querySelector("[data-act=msg]").textContent = e.message; }
    };
  };
  idle();
}

// ---------- Batch ----------
const TILE_PHASE = { queued: "Queued", reading: "Reading", waiting: "Waiting its turn", deciding: "Checking", writing: "Writing" };
VIEWS.batch = (el, id) => {
  el.append(h(`
    <div class="crumbs"><a href="#/new">New run</a> / <b>Batch</b></div>
    <header class="page-head"><div><h1 id="bTitle">Batch</h1><p class="muted" id="bSub">Starting...</p></div><a class="btn" href="#/dashboard">Dashboard</a></header>
    <section class="mission">
      <div class="card ring-card">
        <div class="ring"><svg viewBox="0 0 128 128"><defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f46e5"/><stop offset="1" stop-color="#7c3aed"/></linearGradient></defs>
          <circle class="bg" cx="64" cy="64" r="52"/><circle class="fg" id="ringFg" cx="64" cy="64" r="52" stroke-dasharray="326.7" stroke-dashoffset="326.7"/></svg>
          <div class="lbl"><b id="ringN">0</b><small id="ringOf">of 0 decided</small></div></div>
        <div class="clock"><div><small>Elapsed</small><b class="big" id="elapsed">0s</b></div>
          <div class="row" style="gap:26px"><div><small>Same work by hand</small><b id="manual">—</b></div><div><small>Throughput</small><b id="tput">—</b></div></div></div>
      </div>
      <div class="card mix"><div class="stack" id="stack"></div><div class="counters" id="counters"></div>
        <div class="mix-foot">${I.info.replace("<svg", '<svg width="15" height="15"')}Reading runs in parallel. Deciding runs one at a time in upload order, so two invoices on one PO never see the same balance.</div></div>
    </section>
    <div class="tiles" id="tiles"></div>`));
  const tiles = new Map(), tileHtml = new Map();
  const render = (s) => {
    $("#bTitle").textContent = s.label || "Batch";
    $("#bSub").textContent = s.finished ? `Done: ${s.total} invoices decided and explained.` : `${s.decided} of ${s.total} decided.`;
    $("#elapsed").textContent = `${s.elapsed_s}s`;
    $("#manual").textContent = `${(s.manual_minutes / 60).toFixed(1)} h`;
    $("#tput").textContent = `${s.per_minute}/min`;
    $("#ringN").textContent = s.decided;
    $("#ringOf").textContent = `of ${s.total} decided`;
    $("#ringFg").setAttribute("stroke-dashoffset", (326.7 * (1 - (s.total ? s.decided / s.total : 0))).toFixed(1));
    const c = s.counts, tot = s.total || 1;
    $("#stack").innerHTML = [[c.approved, DEC_COLOR.APPROVE], [c.held, DEC_COLOR.HOLD], [c.rejected, DEC_COLOR.REJECT]]
      .map(([v, col]) => `<span style="width:${(v / tot) * 100}%;background:${col}"></span>`).join("");
    $("#counters").innerHTML = [["Reading", c.queued + c.reading, "#4f46e5"], ["Waiting to decide", c.waiting + c.deciding, "#9aa1ae"],
      ["Approved", c.approved, DEC_COLOR.APPROVE], ["On hold", c.held, DEC_COLOR.HOLD], ["Rejected", c.rejected, DEC_COLOR.REJECT]]
      .map(([k, v, col]) => `<div class="counter"><small><i style="background:${col}"></i>${k}</small><b>${v}</b></div>`).join("");
    // Tiles are created once and only changed tiles are touched: rebuilding all of them every snapshot would
    // replay their fade-in and make the page blink.
    for (const r of s.runs) {
      let a = tiles.get(r.id);
      if (!a) { a = document.createElement("a"); a.href = `#/run/${r.id}`; $("#tiles").append(a); tiles.set(r.id, a); }
      const cls = `card tile ${r.decision ? "t-" + r.decision : "t-busy"}`;
      if (a.className !== cls) a.className = cls;
      const word = r.decision ? DECISION_WORD[r.decision] : TILE_PHASE[r.phase] || "Working";
      const why = r.decision ? r.title || "All checks passed" : "";
      const inner = `<span class="t-head">${avatar(r.vendor || r.filename)}<span class="t-id"><span class="vend">${esc(r.vendor || (r.decision ? "—" : "Reading..."))}</span>
      <span class="name" title="${esc(r.filename)}">${esc(r.filename)}</span></span>
      <span class="t-state s-${r.decision || "busy"}">${r.decision ? DEC_ICON[r.decision] : `<span class="spin"></span>`}</span></span>${segs(r.statuses)}
      <span class="t-foot"><span class="amt">${r.total != null ? money(r.total) : "—"}</span><span class="t-word">${word}</span></span>
      <span class="t-why" title="${esc(why)}">${esc(why) || "&nbsp;"}</span>`;
      if (tileHtml.get(r.id) !== inner) { a.innerHTML = inner; tileHtml.set(r.id, inner); }
    }
  };
  cleanup.push(stream(`/api/batches/${id}/events`, render, () => { el.innerHTML = GONE_HTML; }));
};

// ---------- Live run ----------
const FIELD_ROWS = [["vendor_name", "Vendor"], ["vendor_tax_id", "Tax ID"], ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"], ["due_date", "Due date"], ["po_number", "PO number (printed)"],
  ["po_number_handwritten", "PO number (handwritten)"], ["bill_to_name", "Billed to"], ["currency", "Currency"],
  ["service_period", "Service period"], ["subtotal", "Subtotal"], ["tax_amount", "Tax"], ["total", "Total"],
  ["remit_bank_account", "Bank account"], ["remit_bank_routing", "Routing number"]];
const MONEY_KEYS = /^(subtotal|tax|tax_amount|total|line_sum|po_total|billed_before|this_invoice|after|amount)$/;
const PHASE_TEXT = { queued: "Waiting to start", reading: "Reading the document", waiting: "Waiting for earlier invoices in this batch to be decided",
  deciding: "Running the checks", writing: "Writing the explanation", done: "Done" };
const fmtVal = (k, v) => (typeof v === "number" && MONEY_KEYS.test(k) ? money(v) : typeof v === "boolean" ? (v ? "yes" : "no") : v ?? "—");
const sevClass = (sev) => (sev === "reject" ? "dec-REJECT" : sev === "hold" ? "dec-HOLD" : "");

function reasonsList(rs) {
  if (!rs.length) return "";
  return `<ul class="reasons">${rs.map((x) => `<li><span class="code ${sevClass(x.severity) || "dec-WORK"}">${esc(x.code)}</span>${esc(x.message)}
    ${x.action ? `<span class="next-line">Next: ${esc(x.action)}</span>` : ""}</li>`).join("")}</ul>`;
}
function extractionTable(x, det) {
  const rows = FIELD_ROWS.map(([k, label]) => {
    const f = x.fields[k] || {};
    if (f.value == null && k === "po_number_handwritten") return "";
    const v = f.value == null ? `<span class="muted">not printed</span>` : esc(/subtotal|tax_amount|total/.test(k) ? money(f.value) : f.value);
    return `<tr data-key="${k}"><td class="muted">${label}</td><td><b style="font-weight:600">${v}</b></td><td><span class="pill plain conf-${f.confidence}">${f.confidence || "—"}</span></td><td class="mono muted">${esc(f.source_text || "")}</td></tr>`;
  }).join("");
  const unv = det.unverified && det.unverified.length ? `<p class="badge warn">Not found in the PDF text, so treated as unreliable: ${esc(det.unverified.join(", "))}</p>` : "";
  const stamps = x.stamps && x.stamps.length ? `<p class="notes-row">Stamps seen (ignored; payment status comes from the ledger): ${esc(x.stamps.join(", "))}</p>` : "";
  return `${unv}<table class="grid tight"><thead><tr><th>Field</th><th>Value</th><th>Confidence</th><th>Read as</th></tr></thead><tbody>${rows}</tbody></table>${stamps}`;
}
function lineItemsTable(x) {
  const lines = x.line_items.map((li, i) => `<tr data-key="line:${i}"><td>${esc(li.description)}${li.sku ? `<br><span class="mono muted">${esc(li.sku)}</span>` : ""}</td>
    <td class="num">${li.qty ?? "—"}</td><td class="num">${li.unit_price ?? "—"}</td><td class="num"><b style="font-weight:600">${money(li.amount)}</b></td>
    <td><span class="pill plain conf-${li.confidence}">${li.confidence}</span></td></tr>`).join("");
  return `<table class="grid tight"><thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit price</th><th class="num">Amount</th><th>Confidence</th></tr></thead>
    <tbody>${lines || `<tr><td colspan="5" class="muted">No line items</td></tr>`}</tbody></table>`;
}
function linesTable(det) {
  const cap = Math.max(det.po_total || 0, det.after || 0) || 1, over = det.after > det.po_total;
  const meter = `<div class="po-meter"><div class="row between"><b>${esc(det.po_number)}</b><span class="muted">${money(det.after)} of ${money(det.po_total)} after this invoice</span></div>
    <div class="meter"><div class="stack"><span style="width:${(det.billed_before / cap) * 100}%;background:#9aa1ae"></span><span style="width:${(det.this_invoice / cap) * 100}%;background:${over ? DEC_COLOR.REJECT : DEC_COLOR.APPROVE}"></span></div>
      <i class="limit" style="left:${(det.po_total / cap) * 100}%" title="PO limit"></i></div>
    <div class="legend2"><span><i class="sw" style="background:#9aa1ae"></i>Billed before ${money(det.billed_before)}</span>
      <span><i class="sw" style="background:${over ? DEC_COLOR.REJECT : DEC_COLOR.APPROVE}"></i>This invoice ${money(det.this_invoice)}</span>
      <span>PO total ${money(det.po_total)}</span></div>
    ${det.billed_by ? `<ul class="billed">${det.billed_by.map((b) => `<li><span>${b.invoice_number ? `<span class="mono">${esc(b.invoice_number)}</span>` : "Opening balance"}
      ${b.filename ? ` · <a class="mono" href="#/run/${esc(b.run_id)}">${esc(b.filename)}</a>` : b.invoice_number ? ` · <span class="muted">opening ledger</span>` : ""}
      <span class="muted"> · ${esc(String(b.status).replace(/_/g, " "))}</span></span><b>${money(b.amount)}</b></li>`).join("")}
      <li class="now ${over ? "" : "ok"}"><span>This invoice${over ? `, ${money(det.after - det.po_total)} over the PO` : ""}</span><b>${money(det.this_invoice)}</b></li></ul>` : ""}</div>`;
  if (!det.lines || !det.lines.length) return meter;
  return meter + `<table class="grid tight"><thead><tr><th>Invoice line</th><th class="num">Qty</th><th class="num">Price</th><th>PO line</th><th class="num">vs PO</th></tr></thead><tbody>
    ${det.lines.map((l) => `<tr><td>${esc(l.description)}</td><td class="num">${l.qty ?? "—"}</td><td class="num">${l.unit_price ?? "—"}</td>
    <td class="mono">${l.po_sku ? esc(l.po_sku) : `<span class="pill plain dec-HOLD">not on PO</span>`}</td>
    <td class="num">${l.price_diff_pct == null ? "—" : (l.price_diff_pct > 0 ? "+" : "") + l.price_diff_pct + "%"}</td></tr>`).join("")}</tbody></table>`;
}
function originalLine(o) {
  const file = o.filename ? `<a href="#/run/${esc(o.run_id)}" class="mono">${esc(o.filename)}</a>` : `<span class="mono">${esc(o.invoice_number)}.pdf</span> (opening ledger)`;
  return `<b class="mono">${esc(o.invoice_number)}</b> · ${file} · ${esc(String(o.status || "").replace(/_/g, " "))}${o.processed_at ? ` · processed ${ago(o.processed_at)}` : ""}`;
}
function stageDetails(r, s, st) {
  if (s === "extract" && r.extraction) {
    const det = st.details || {}, x = r.extraction;
    const unv = det.unverified && det.unverified.length ? `<p class="badge warn">Not found in the PDF text, so treated as unreliable: ${esc(det.unverified.join(", "))}</p>` : "";
    return `${unv}<button class="btn" data-tab="fields">See all ${Object.values(x.fields).filter((f) => f && f.value != null).length} fields read</button>
      <button class="btn" data-tab="lines">See ${x.line_items.length} line items</button>`;
  }
  if (s === "three_way" && st.details && st.details.po_number) return linesTable(st.details);
  if (s === "duplicates" && st.details && st.details.original) return `<p class="origbox"><small>Original</small>${originalLine(st.details.original)}</p>`;
  const d = st.details || {};
  const keys = Object.keys(d).filter((k) => d[k] === null || typeof d[k] !== "object");
  return keys.length ? `<dl class="kv">${keys.map((k) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(fmtVal(k, d[k]))}</dd>`).join("")}</dl>` : "";
}
function stageItem(r, s, isOpen) {
  const st = r.stages[s];
  const ms = st.status === "pending" ? "" : st.status === "skip" ? "skipped" : st.status === "running" ? "running" : `${st.ms} ms`;
  const body = isOpen ? `${reasonsList(st.reasons)}${stageDetails(r, s, st)}` : "";
  return `<li class="stage s-${st.status} ${isOpen ? "open" : ""}"><button class="stage-head" data-stage="${s}" aria-expanded="${isOpen}">
      <span class="dot st-${st.status}">${STATUS_ICON[st.status] || ""}</span>
      <span><span class="s-title">${esc(st.title || STAGE_LABELS[s])}</span><span class="s-sum">${esc(st.summary || (st.status === "pending" ? "Waiting" : ""))}</span></span>
      <span class="s-ms">${ms}</span><span class="chev">${I.chev.replace("<svg", '<svg width="14" height="14"')}</span></button>
    ${body.trim() ? `<div class="stage-body">${body}</div>` : ""}</li>`;
}
function stepper(r) {
  return STAGES.map((s) => {
    const st = r.stages[s] || { status: "pending" };
    let cls = st.status, icon = STATUS_ICON[st.status] || "", sub = st.status === "pending" ? "" : st.status === "skip" ? "skipped" : st.status === "running" ? "running" : `${st.ms} ms`;
    if (s === "decision" && r.decision) { cls = r.decision.decision; icon = DEC_ICON[cls]; sub = DECISION_WORD[cls]; }
    const done = ["pass", "warn", "fail", "skip"].includes(st.status);
    return `<button class="step ${done ? "done" : ""}" data-step="${s}"><span class="node n-${cls}">${icon}</span><span class="lbl">${STEP_LABELS[s]}</span><span class="ms">${sub}</span></button>`;
  }).join("");
}
function verdictCard(r) {
  const d = r.decision, p = d.primary, dec = d.decision;
  const others = d.reasons.filter((x) => x !== d.reasons[0] && (!p || x.code !== p.code));
  const decidedIn = r.decided_at ? `${(r.decided_at - r.created).toFixed(1)} s` : "—";
  const amountFact = d.amount_at_risk ? ["Money stopped", money(d.amount_at_risk)] : [dec === "APPROVE" ? "Amount to pay" : "Invoice total", money(r.money && r.money.total)];
  const flagged = Object.values((r.evidence || {}).flags || {}).some((f) => f === "hold" || f === "reject");
  const orig = (r.stages.duplicates.details || {}).original;
  return `<div class="card verdict v-${dec}">
    <div class="v-row"><span class="v-word dec-${dec}">${DEC_ICON[dec]}${DECISION_WORD[dec]}</span>${p ? `<span class="pill plain mono ${sevClass(p.severity)}">${esc(p.code)}</span>` : ""}</div>
    <div class="v-title">${esc(p ? p.title : "Every check passed")}</div>
    ${r.summary ? `<p class="v-text">${esc(r.summary)}</p>` : `<div class="skel-lines" style="margin-bottom:16px"><div class="skel"></div><div class="skel" style="width:70%"></div></div>`}
    ${orig ? `<p class="origbox"><small>Original</small>${originalLine(orig)}</p>` : ""}
    <div class="facts"><div><small>Owner</small><b>${esc(d.owner || "None, pays automatically")}</b></div><div><small>${amountFact[0]}</small><b>${amountFact[1]}</b></div><div><small>Decided in</small><b>${decidedIn}</b></div></div>
    <div class="next n2-${dec}">${dec === "APPROVE" ? I.check : I.arrow}<div><b>Next step.</b> ${esc(d.next_action)}</div></div>
    ${others.length ? `<ul class="also">${others.map((x) => `<li class="${x.severity}">${esc(x.severity === "note" ? x.message : x.title)}</li>`).join("")}</ul>` : ""}
    <div class="actions">
      ${r.email ? `<button class="btn primary" id="copyEmail">${I.copy}Copy email to ${esc(r.email.to)}</button>` : ""}
      ${p && (p.code === "DUPLICATE" || p.code === "PROBABLE_DUPLICATE") ? `<button class="btn" id="cmpOrig">${I.cols}Compare with the original</button>` : ""}
      ${flagged ? `<button class="btn" id="showOnPage">${I.eye}Show on page</button>` : ""}
    </div></div>`;
}
function workingCard(r) {
  return `<div class="card verdict v-WORK"><div class="v-row"><span class="v-word dec-WORK"><span class="spin"></span>Working</span></div>
    <div class="working">${esc(PHASE_TEXT[r.phase] || "")}...</div>
    <div class="skel-lines"><div class="skel"></div><div class="skel" style="width:80%"></div><div class="skel" style="width:55%"></div></div></div>`;
}
function emailTab(r) {
  if (!r.email) return `<p class="empty">${r.decision && r.phase === "done" ? "No email needed. Approved invoices go straight to payment." : "The email is written once the decision is made."}</p>`;
  return `<div class="email-box"><div class="hdr"><span>To</span><b>${esc(r.email.to)}</b><span>Subject</span><b>${esc(r.email.subject)}</b></div>
    <pre>${esc(r.email.body)}</pre><button class="btn primary" id="copyEmail2">${I.copy}Copy email</button></div>`;
}
const ledgerPill = (s) => `<span class="pill plain ${s === "paid" || s === "approved" ? "dec-APPROVE" : s === "rejected" ? "dec-REJECT" : "dec-HOLD"}">${esc(String(s).replace(/_/g, " "))}</span>`;
function ledgerRow(e, showPo) {
  const where = e.filename ? `<a class="mono" href="#/run/${esc(e.run_id)}">${esc(e.filename)}</a>` : `<span class="muted">opening ledger</span>`;
  const tag = e.position === "this" ? `<span class="pos this">this invoice</span>` : e.position ? `<span class="pos">${e.position}</span>` : "";
  return `<li class="${e.position === "this" ? "this" : ""}"><span><span class="mono">${esc(e.invoice_number || "—")}</span> · ${where}${showPo && e.po_number ? ` · <span class="mono muted">${esc(e.po_number)}</span>` : ""}</span>
    <span class="rel-right">${tag}${ledgerPill(e.status)}<b>${money(e.subtotal ?? e.total)}</b></span></li>`;
}
function relatedTab(rel, r) {
  if (!r.decision) return `<p class="empty">Links appear once the invoice is decided.</p>`;
  if (!rel) return `<p class="empty"><span class="spin" style="display:inline-block;vertical-align:-2px;margin-right:8px"></span>Looking up related records...</p>`;
  const v = rel.vendor, po = rel.po, out = [];
  out.push(`<section class="rel-sec"><h4>Vendor</h4>${v ? `<div class="who" style="margin-bottom:10px">${avatar(v.name)}<b>${esc(v.name)}</b>${ledgerPill(v.status)}</div>
    <dl class="kv plain"><dt>Matched by</dt><dd>${esc(v.matched_by || "—")}</dd><dt>Tax ID</dt><dd class="mono">${esc(v.tax_id)}</dd><dt>Phone on file</dt><dd>${esc(v.phone)}</dd>
    <dt>Bank on file</dt><dd class="mono">...${esc(v.bank_on_file_last4)}</dd><dt>Bank on invoice</dt><dd>${v.bank_on_invoice_last4 ? `<span class="mono">...${esc(v.bank_on_invoice_last4)}</span>
      ${v.bank_matches ? `<span class="pill plain dec-APPROVE">matches</span>` : `<span class="pill plain dec-REJECT">differs</span>`}` : `<span class="muted">not printed</span>`}</dd></dl>`
    : `<p class="muted">Not in the vendor master, so nothing else can be linked to it.</p>`}</section>`);
  if (rel.original) out.push(`<section class="rel-sec"><h4>Duplicate of</h4><p class="origbox">${originalLine(rel.original)}</p></section>`);
  if (po) {
    const pct = Math.min(100, (po.billed_now / po.total) * 100), full = po.billed_now > po.total;
    out.push(`<section class="rel-sec"><h4>Purchase order ${esc(po.po_number)} <span class="muted" style="font-weight:400">· ${esc(po.type || "standard")} · ${esc(po.status)}</span></h4>
      <div class="row between" style="font-size:13px"><span class="muted">Billed now (approved and paid)</span><b>${money(po.billed_now)} of ${money(po.total)}</b></div>
      <span class="bar-track" style="margin:8px 0 4px"><span style="width:${pct}%" class="${full ? "full" : ""}"></span></span>
      <ul class="billed">${po.invoices.map((e) => ledgerRow(e)).join("") || `<li><span class="muted">No invoices on this PO yet</span></li>`}</ul>
      <h4 style="margin-top:16px">Ordered${po.received ? " and received" : ""}</h4>
      <ul class="billed">${po.lines.map((l) => `<li><span><span class="mono muted">${esc(l.sku)}</span> ${esc(l.desc)}</span><span class="rel-right">${l.qty} × ${money(l.unit_price)}
        ${po.received ? `<span class="pill plain ${(po.received[l.sku] || 0) >= l.qty ? "dec-APPROVE" : "dec-HOLD"}">received ${po.received[l.sku] || 0}</span>` : ""}</span></li>`).join("")}</ul></section>`);
  } else out.push(`<section class="rel-sec"><h4>Purchase order</h4><p class="muted">No PO linked: none was printed and none could be inferred from the lines.</p></section>`);
  if (v) {
    const others = rel.vendor_invoices.filter((e) => !po || e.po_number !== po.po_number);
    out.push(`<section class="rel-sec"><h4>Other invoices from ${esc(v.name)}${po ? " on other POs" : ""}</h4>
      ${others.length ? `<ul class="billed">${others.map((e) => ledgerRow(e, true)).join("")}</ul>` : `<p class="muted">None in the ledger.</p>`}</section>`);
  }
  return out.join("");
}
VIEWS.run = (el, id) => {
  el.append(h(`
    <div class="crumbs" id="rCrumbs"><a href="#/new">New run</a></div>
    <header class="runhead" id="rHead"><span class="avatar lg skel" style="background:none"></span><div><h1 id="rTitle">Loading...</h1><div class="meta" id="rMeta"></div></div></header>
    <nav class="card stepper" id="stepper" aria-label="Checks"></nav>
    <div class="runwrap"><section class="card preview"><div class="doc-tools" id="docTools"></div><div class="stage-area" id="preview"><div class="empty">Loading document...</div></div></section>
      <section class="side"><div id="verdict"></div>
        <div class="card"><div class="tabs" id="tabs" role="tablist"></div><div class="tabbody" id="timeline"></div></div></section></div>`));
  const open = new Set(["decision"]);
  let last = null, lastDoc = "", tab = "checks", autoOpened = false, rel = null, relPhase = "";
  const goStage = (s) => { tab = "checks"; open.add(s); render(last); el.querySelector(`[data-stage="${s}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }); };
  const render = (r) => {
    last = r;
    if (r.decision && !autoOpened) { autoOpened = true; STAGES.forEach((s) => r.stages[s].status === "fail" && open.add(s)); }
    const x = r.extraction, inv = x && (x.fields.invoice_number || {}).value, cur = (r.money || {}).currency;
    $("#rCrumbs").innerHTML = `<a href="#/new">New run</a> / <a href="#/batch/${r.batch_id}">Batch</a> / <b>${esc(r.filename)}</b>`;
    $("#rHead").innerHTML = `${avatar(r.vendor || r.filename, "lg")}<div><h1>${esc(r.vendor || r.filename)}</h1><div class="meta">
        ${inv ? `<span class="chip mono">${esc(inv)}</span>` : ""}${r.money && r.money.invoice_date ? `<span class="chip">${esc(day(r.money.invoice_date))}</span>` : ""}
        ${r.po_number ? `<span class="chip mono">${esc(r.po_number)}</span>` : ""}
        ${r.path ? `<span class="chip">${r.path === "digital" ? "Digital PDF, read from its text" : "Scan or photo, read by AI vision"}</span>` : ""}
        ${r.cached ? `<span class="chip">Cached read</span>` : ""}</div></div>
      <div class="amount"><small>Invoice total</small><b>${r.money && r.money.total != null ? money(r.money.total) + (cur && cur !== "USD" ? ` <span class="muted" style="font-size:16px">${esc(cur)}</span>` : "") : "—"}</b></div>`;
    $("#stepper").innerHTML = stepper(r);
    const ev = r.evidence || { pages: [], boxes: [] };
    $("#docTools").innerHTML = `<b>${r.path === "scanned" ? "Scan or photo" : r.path === "digital" ? "Digital PDF" : "Document"}</b>
      <span class="muted">${ev.pages.length ? `${ev.pages.length} page${ev.pages.length > 1 ? "s" : ""}` : ""}${ev.boxes.length ? ` · ${ev.boxes.length} values located` : ""}</span>
      <span class="legend"><span><i class="sw ok"></i>Verified</span><span><i class="sw warn"></i>Note</span><span><i class="sw bad"></i>Reason for hold</span></span>`;
    // Only redraw the document when it changed, so page images never flicker between snapshots.
    const doc = r.mime ? docViewer(r, { callout: r.decision && r.decision.primary && r.decision.primary.title }) : `<div class="empty">Loading document...</div>`;
    if (doc !== lastDoc) { lastDoc = doc; $("#preview").innerHTML = doc; }
    $("#verdict").innerHTML = r.decision ? verdictCard(r) : workingCard(r);
    const tabs = [["checks", "Checks", STAGES.length], ["fields", "Fields", x ? Object.values(x.fields).filter((f) => f && f.value != null).length : null],
      ["lines", "Line items", x ? x.line_items.length : null], ["related", "Related", null], ["email", "Email", null]];
    $("#tabs").innerHTML = tabs.map(([k, l, n]) => `<button class="tab ${k === tab ? "active" : ""}" role="tab" aria-selected="${k === tab}" data-tab="${k}">${l}${n != null ? `<span class="count">${n}</span>` : ""}</button>`).join("");
    const waitX = `<p class="empty"><span class="spin" style="display:inline-block;vertical-align:-2px;margin-right:8px"></span>Reading the document...</p>`;
    $("#timeline").innerHTML = tab === "checks" ? `<ol class="timeline">${STAGES.map((s) => stageItem(r, s, open.has(s))).join("")}</ol>`
      : tab === "fields" ? (x ? extractionTable(x, (r.stages.extract || {}).details || {}) : waitX)
      : tab === "lines" ? (x ? lineItemsTable(x) + (r.stages.three_way.details && r.stages.three_way.details.po_number ? `<div style="padding:14px 10px 4px">${linesTable(r.stages.three_way.details)}</div>` : "") : waitX)
      : tab === "related" ? relatedTab(rel, r)
      : emailTab(r);
    // Related records are looked up once the invoice is decided (and again when it finishes), not on every snapshot.
    if (tab === "related" && r.decision && relPhase !== r.phase) {
      relPhase = r.phase;
      api(`/api/runs/${r.id}/related`).then((d) => { rel = d; if (tab === "related") render(last); }).catch(() => {});
    }
    wireEvidence(el, (key) => goStage(stageFor(key)));
    el.querySelectorAll(".stage-head").forEach((b) => (b.onclick = () => {
      const s = b.dataset.stage; open.has(s) ? open.delete(s) : open.add(s); render(last);
    }));
    el.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => goStage(b.dataset.step)));
    el.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; render(last); }));
    for (const cid of ["copyEmail", "copyEmail2"]) {
      const copy = $("#" + cid);
      if (copy) copy.onclick = () => navigator.clipboard.writeText(`Subject: ${r.email.subject}\n\n${r.email.body}`).then(() => (copy.textContent = "Copied"));
    }
    const cmp = $("#cmpOrig"); if (cmp) cmp.onclick = () => compareOriginal(r);
    const show = $("#showOnPage");
    if (show) show.onclick = () => {
      const bad = $("#preview .ev.bad"); if (!bad) return;
      bad.scrollIntoView({ behavior: "smooth", block: "center" });
      el.querySelectorAll(`#preview [data-key="${CSS.escape(bad.dataset.key)}"]`).forEach((n) => { n.classList.add("focus"); setTimeout(() => n.classList.remove("focus"), 1600); });
    };
  };
  cleanup.push(stream(`/api/runs/${id}/events`, render, () => { el.innerHTML = GONE_HTML; }));
};

// ---------- Dashboard ----------
VIEWS.dashboard = async (el) => {
  el.append(h(`
    <header class="page-head"><div><h1>Dashboard</h1><p class="muted">Every invoice processed, its decision and why. Click a row to replay it.</p></div>
      <div class="seg-ctl" id="filters"></div></header>
    <div class="kpis" id="kpis"></div><div class="charts" id="charts"></div><div class="card"><table class="grid rows" id="table"></table></div>`));
  let filter = "ALL", lastJson = "", data = null;
  const draw = () => {
    const d = data, k = d.kpis, runs = d.runs.filter((r) => r.decision).slice().sort((a, b) => a.created - b.created);
    let cnt = 0, appr = 0, stop = 0;
    const cum = runs.map((r) => { cnt++; if (r.decision === "APPROVE") appr++; stop += r.at_risk || 0; return { cnt, appr, stop, rate: appr / cnt, secs: r.seconds || 0 }; });
    const tail = cum.slice(-40);
    $("#kpis").innerHTML = `
      <div class="card kpi hero"><small>Money stopped</small><b>${money(k.dollars_stopped)}</b><div class="d">duplicates, overruns and suspected fraud</div>${spark(tail.map((p) => p.stop), "#ffffff")}</div>
      <div class="card kpi"><small>Invoices processed</small><b>${k.runs}</b><div class="d">${k.approved} approved, ${k.held} on hold, ${k.rejected} rejected</div>${spark(tail.map((p) => p.cnt), "#4f46e5")}</div>
      <div class="card kpi"><small>Touchless approvals</small><b>${Math.round(k.touchless_rate * 100)}%</b><div class="d">approved with no human touch</div>${spark(tail.map((p) => p.rate), "#0e9f6e")}</div>
      <div class="card kpi"><small>Clerk hours saved</small><b>${k.hours_saved} h</b><div class="d">approved invoices nobody had to key in</div>${spark(tail.map((p) => p.appr), "#7c3aed")}</div>
      <div class="card kpi"><small>Average time per invoice</small><b>${k.avg_seconds}s</b><div class="d">upload to decision, queue included</div>${spark(tail.map((p) => p.secs), "#9aa1ae")}</div>`;
    const total = k.runs || 0, C = 2 * Math.PI * 15.9;
    let off = 0;
    const arcs = total ? [["APPROVE", k.approved], ["HOLD", k.held], ["REJECT", k.rejected]].filter(([, v]) => v).map(([dd, v]) => {
      const len = (v / total) * C, s = `<circle cx="21" cy="21" r="15.9" fill="none" stroke="${DEC_COLOR[dd]}" stroke-width="5" stroke-dasharray="${Math.max(len - 0.6, 0.1)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 21 21)"/>`;
      off += len; return s; }).join("") : "";
    const by = (key, val) => { const m = new Map(); d.runs.filter((r) => r.decision && r.decision !== "APPROVE" && r.title).forEach((r) => m.set(r[key], (m.get(r[key]) || 0) + val(r)));
      return [...m].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 6); };
    $("#charts").innerHTML = `
      <div class="card chart"><h3>Decision mix</h3><div class="donut"><svg viewBox="0 0 42 42"><circle cx="21" cy="21" r="15.9" fill="none" stroke="#f0efea" stroke-width="5"/>${arcs}
        <text x="21" y="22" text-anchor="middle" font-size="8" font-weight="700" fill="#0b0f19" font-family="Geist">${total}</text><text x="21" y="27.5" text-anchor="middle" font-size="3.2" fill="#6b7280" font-family="Geist">invoices</text></svg>
        <ul>${[["APPROVE", k.approved], ["HOLD", k.held], ["REJECT", k.rejected]].map(([dd, v]) => `<li>${decChip(dd)}<b>${v}</b></li>`).join("")}</ul></div></div>
      <div class="card chart"><h3>Why invoices were stopped <small>· top reasons</small></h3>${hbars(by("title", () => 1), "#d97706", (v) => v)}</div>
      <div class="card chart"><h3>Money stopped <small>· by reason</small></h3>${hbars(by("title", (r) => r.at_risk || 0), "#4f46e5", money0)}</div>`;
    const counts = { ALL: k.runs, APPROVE: k.approved, HOLD: k.held, REJECT: k.rejected };
    $("#filters").innerHTML = Object.keys(counts).map((f) => `<button class="${f === filter ? "on" : ""}" data-f="${f}">${f === "ALL" ? "All" : DECISION_WORD[f]} ${counts[f]}</button>`).join("");
    el.querySelectorAll("[data-f]").forEach((b) => (b.onclick = () => { filter = b.dataset.f; draw(); }));
    const rows = d.runs.filter((r) => filter === "ALL" || r.decision === filter);
    $("#table").innerHTML = `<thead><tr><th>When</th><th>Vendor</th><th>Invoice</th><th class="num">Amount</th><th>Decision</th><th>Reason</th><th class="num">Time</th></tr></thead><tbody>
      ${rows.map((r) => `<tr data-id="${r.id}" tabindex="0"><td class="muted">${ago(r.created)}</td><td><span class="who">${avatar(r.vendor || r.filename)}${esc(r.vendor || "—")}</span></td>
        <td class="mono">${esc(r.invoice_number || r.filename)}</td><td class="num"><b style="font-weight:600">${money(r.total)}</b></td><td>${decChip(r.decision)}</td>
        <td class="muted">${esc(r.title || (r.decision === "APPROVE" ? "Every check passed" : ""))}</td><td class="num muted">${r.seconds == null ? "—" : r.seconds + "s"}</td></tr>`).join("")
      || `<tr><td colspan="7" class="empty">No invoices yet. Start one from <a href="#/new">New run</a>.</td></tr>`}</tbody>`;
    el.querySelectorAll("tr[data-id]").forEach((tr) => (tr.onclick = tr.onkeydown = (e) => {
      if (e.type === "click" || e.key === "Enter") location.hash = `#/run/${tr.dataset.id}`;
    }));
  };
  const load = async () => {
    const d = await api("/api/runs"), js = JSON.stringify(d);
    CACHE["/api/runs"] = d;
    if (js === lastJson) return; // nothing new: keep the page still
    lastJson = js; data = d; draw();
  };
  if (CACHE["/api/runs"]) { data = CACHE["/api/runs"]; lastJson = JSON.stringify(data); draw(); }  // instant, then refreshed
  await load();
  const t = setInterval(() => load().catch(() => {}), 3000);
  cleanup.push(() => clearInterval(t));
};

// ---------- Procurement data ----------
const POLICY_LABELS = { price_tolerance_pct: "Price tolerance per line (%)", total_tolerance_pct: "PO overbilling allowance (% of PO)",
  total_tolerance_abs: "PO overbilling and unplanned-charge allowance ($)", duplicate_window_days: "Duplicate look-back window (days)",
  fuzzy_dup_amount_pct: "Duplicate amount match (%)", fuzzy_dup_line_similarity: "Duplicate line similarity (0 to 1)",
  po_infer_min_score: "PO inference minimum score (0 to 1)", po_infer_margin: "PO inference winning margin (0 to 1)",
  clerk_minutes_per_invoice: "Clerk minutes per invoice (for hours saved)" };
const table = (head, rows) => `<div class="card"><table class="grid"><thead><tr>${head.map((x) => `<th${x.startsWith("#") ? ' class="num"' : ""}>${esc(x.replace("#", ""))}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const statusPill = (s) => `<span class="pill ${s === "blocked" || s === "closed" ? "dec-REJECT" : s === "open" || s === "approved" ? "dec-APPROVE" : "dec-HOLD"}">${esc(s)}</span>`;
const DATA_TABS = {
  "Purchase orders": (el, ref) => { el.innerHTML = table(["PO", "Vendor", "Type", "Status", "#Total", "#Billed", "#Remaining", "Used"], ref.pos.map((p) => {
    const pct = p.total ? Math.min(100, Math.round((p.billed / p.total) * 100)) : 0;
    return `<tr><td class="mono">${esc(p.po_number)}</td><td><span class="who">${avatar(p.vendor_name)}${esc(p.vendor_name)}</span></td><td class="muted">${esc(p.type)}</td><td>${statusPill(p.status)}</td>
      <td class="num">${money(p.total)}</td><td class="num">${money(p.billed)}</td><td class="num"><b style="font-weight:600">${money(p.remaining)}</b></td>
      <td><span class="bar-track"><span style="width:${pct}%" class="${pct >= 100 ? "full" : ""}"></span></span></td></tr>`; })); },
  Vendors: (el, ref) => { el.innerHTML = table(["ID", "Vendor", "Tax ID", "Bank on file", "Phone on file", "Status"], ref.vendors.map((v) =>
    `<tr><td class="mono muted">${v.id}</td><td><span class="who">${avatar(v.name)}<span>${esc(v.name)}<br><span class="muted" style="font-size:12.5px">${esc(v.aliases.join(", "))}</span></span></span></td><td class="mono">${esc(v.tax_id)}</td>
      <td>${esc(v.bank.bank)}<br><span class="mono muted">acct ...${esc(v.bank.account.slice(-4))}</span></td><td>${esc(v.phone)}</td><td>${statusPill(v.status)}</td></tr>`)); },
  "Goods received": (el, ref) => { el.innerHTML = table(["PO", "SKU", "#Quantity received"], ref.receipts.map((r) =>
    `<tr><td class="mono">${esc(r.po_number)}</td><td class="mono">${esc(r.sku)}</td><td class="num">${r.qty_received}</td></tr>`)); },
  Ledger: (el, ref) => { el.innerHTML = table(["Vendor", "Invoice", "Date", "PO", "#Total", "Status"], ref.ledger.slice().reverse().map((e) =>
    `<tr><td class="mono muted">${esc(e.vendor_id)}</td><td class="mono">${esc(e.invoice_number || "—")}</td><td>${esc(e.invoice_date || "")}</td>
      <td class="mono">${esc(e.po_number || "—")}</td><td class="num">${money(e.total)}</td><td>${statusPill(e.status)}</td></tr>`)); },
  Policy: (el, ref) => {
    el.innerHTML = `<form class="card policy" id="policy">${Object.entries(ref.policy).map(([k, v]) =>
      `<label><span>${esc(POLICY_LABELS[k] || k)}</span><input type="number" step="any" min="0" name="${k}" value="${v}"></label>`).join("")}
      <div class="row"><button class="btn primary">Save policy</button><span id="pmsg" class="muted"></span></div></form>`;
    $("#policy").onsubmit = async (e) => {
      e.preventDefault();
      const body = Object.fromEntries([...new FormData(e.target)].map(([k, v]) => [k, Number(v)]));
      try { await api("/api/policy", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); delete CACHE["/api/reference"]; $("#pmsg").textContent = "Saved. New invoices use these values."; }
      catch (err) { $("#pmsg").textContent = err.message; }
    };
  },
};
VIEWS.data = async (el) => {
  el.append(h(`
    <header class="page-head"><div><h1>Procurement data</h1><p class="muted">What every invoice is checked against: vendors, purchase orders, goods received, what has been billed, and the tolerances.</p></div>
      <div id="reset"></div></header>
    <div class="seg-ctl" id="tabs" style="display:inline-flex;margin-bottom:16px"></div><div id="tab"></div>`));
  let ref = await cachedApi("/api/reference", (d) => { if (el.isConnected) { ref = d; show(); } });
  let cur = "Purchase orders";
  const show = () => {
    $("#tabs").innerHTML = Object.keys(DATA_TABS).map((t) => `<button class="${t === cur ? "on" : ""}" data-t="${t}">${t}</button>`).join("");
    el.querySelectorAll("[data-t]").forEach((b) => (b.onclick = () => { cur = b.dataset.t; show(); }));
    DATA_TABS[cur]($("#tab"), ref);
  };
  show();
  freshControl($("#reset"), () => setTimeout(route, 1200));
};

// ---------- Test suite ----------
VIEWS.tests = async (el) => {
  el.append(h(`
    <header class="page-head"><div><h1>Test suite</h1><p class="muted">Every test invoice is run on its own against fresh data, then all of them together as one batch, and compared with the expected decision.</p></div>
      <button class="btn primary" id="runTests">Run all tests</button></header><div id="report"></div>`));
  let timer = null;
  const render = (rep) => {
    const box = $("#report");
    if (rep.status === "never") { box.innerHTML = `<div class="card empty">No test run yet. Click <b>Run all tests</b>.</div>`; return; }
    if (rep.status === "running") { box.innerHTML = `<p class="badge"><span class="spin"></span>Running: each invoice alone, then the whole set as one batch...</p>`; return; }
    if (rep.status === "error") { box.innerHTML = `<p class="badge bad">Test run failed: ${esc(rep.error)}</p>`; return; }
    const pct = (x) => `${Math.round(x.rate * 100)}%`;
    const avg = Object.values(rep.fields).reduce((a, f) => a + f.rate, 0) / Object.keys(rep.fields).length;
    const allPass = rep.alone.passed === rep.alone.total && rep.batch.passed === rep.batch.total;
    box.innerHTML = `
      <div class="kpis"><div class="card kpi ${allPass ? "hero" : ""}"><small>Correct decisions, run alone</small><b>${rep.alone.passed}/${rep.alone.total}</b><div class="d">${allPass ? "every scenario passes" : "see failures below"}</div></div>
        <div class="card kpi"><small>Correct decisions, as one batch</small><b>${rep.batch.passed}/${rep.batch.total}</b><div class="d">order-dependent traps included</div></div>
        <div class="card kpi"><small>Field accuracy (average)</small><b>${pct({ rate: avg })}</b><div class="d">against the answer key</div></div>
        <div class="card kpi"><small>Time</small><b>${rep.elapsed_s}s</b><div class="d">both passes</div></div>
        <div class="card kpi"><small>Reader</small><b class="small">${esc(rep.model)}</b><div class="d" style="color:var(--muted)">default thinking</div></div></div>
      <h2>Field-level extraction accuracy</h2>
      <div class="card fields">${Object.entries(rep.fields).map(([k, f]) => `<div class="frow"><span>${esc(k.replace(/_/g, " ").replace(/^po/, "PO").replace(/^./, (c) => c.toUpperCase()))}</span>
        <span class="bar-track"><span style="width:${Math.round(f.rate * 100)}%;background:${f.rate === 1 ? DEC_COLOR.APPROVE : DEC_COLOR.HOLD}"></span></span><span class="num">${pct(f)} (${f.correct}/${f.total})</span></div>`).join("")}</div>
      <h2>Every scenario</h2>
      ${table(["#", "Scenario", "Input", "Expected", "Alone", "In batch"], rep.rows.map((r) => {
        const cell = (ok, a) => `<span class="pill plain ${ok ? "dec-APPROVE" : "dec-REJECT"}">${ok ? "pass" : "fail"}</span> <span class="muted">${esc(a.decision)}</span>`;
        return `<tr><td class="muted">${r.id}</td><td>${esc(r.title)}<br><span class="mono muted">${esc(r.file)}</span></td><td class="muted">${esc(r.kind.replace(/_/g, " "))}${r.cached ? " · cached" : ""}</td>
          <td>${decChip(r.expected_alone.decision, r.expected_alone.reasons[0])}</td><td>${cell(r.pass_alone, r.actual_alone)}</td><td>${cell(r.pass_batch, r.actual_batch)}</td></tr>`;
      }))}`;
  };
  const tick = async () => {
    const rep = await api("/api/tests/latest");
    render(rep);
    if (rep.status === "running") timer = setTimeout(tick, 1500);
  };
  cleanup.push(() => clearTimeout(timer));
  $("#runTests").onclick = async () => { try { await api("/api/tests/run", { method: "POST" }); } catch (e) { toast(el, e.message); } tick(); };
  tick();
};

// ---------- Assumptions ----------
VIEWS.assumptions = async (el) => {
  const list = await cachedApi("/api/assumptions");
  el.append(h(`
    <header class="page-head"><div><h1>Assumptions and design choices</h1><p class="muted">The judgment calls behind every decision.</p></div></header>
    <div class="card principle"><b>AI reads, code decides.</b>
      <p>The AI model only reads the document and writes the plain-English explanation. Every check and every decision is made by fixed rules that are tested on their own. On digital PDFs, every amount the AI reads is double-checked against the PDF's own text.</p></div>
    <h2>How an invoice is decided</h2>
    <ol class="how">${[["Intake", "Fingerprint the file. Digital PDFs are read from their text, scans and photos by AI vision."],
      ["Read", "AI extracts every field with a confidence level and the exact text it read."],
      ["Validate", "Arithmetic, tax, dates, currency, addressee, document type and missing fields."],
      ["Vendor", "Matched on tax ID or name. Blocked vendors and changed bank details are caught."],
      ["PO match", "The printed or handwritten PO must exist, be open and belong to this vendor. Otherwise it is inferred from the lines."],
      ["Three-way match", "Price against the PO, quantity against goods received, running PO balance, unplanned charges."],
      ["Duplicates", "The same number, or the same amount, lines and dates under a new number."],
      ["Decision", "REJECT beats HOLD beats APPROVE. The most important reason names the owner and the next step."]]
      .map(([t, s]) => `<li class="card"><b>${t}</b>${esc(s)}</li>`).join("")}</ol>
    <h2>Assumptions</h2><div class="card"><ul class="assume">${list.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>`));
};

// ---------- Evidence on the document ----------
const STAGE_OF = { vendor_name: "vendor", vendor_tax_id: "vendor", remit_bank_account: "vendor", remit_bank_routing: "vendor",
  invoice_number: "duplicates", invoice_date: "validate", bill_to_name: "validate", subtotal: "validate", tax_amount: "validate",
  total: "validate", po_number: "po_match", po_number_handwritten: "po_match", line: "three_way", stamp: "validate", document_type: "validate" };
const stageFor = (key) => STAGE_OF[key] || STAGE_OF[key.split(":")[0]] || "decision";
const evClass = (sev) => (sev === "reject" || sev === "hold" ? "bad" : sev === "note" ? "warn" : "ok");

function docViewer(r, opts = {}) {
  const ev = r.evidence || { status: "pending", pages: [], boxes: [], flags: {} };
  const reading = ["queued", "reading"].includes(r.phase);
  const pages = ev.pages.length ? ev.pages
    : (r.mime || "").startsWith("image/") ? [{ n: 1, url: `/api/runs/${r.id}/file` }] : [];
  if (!pages.length)
    return `<div class="empty">${r.phase === "done" ? "This file cannot be previewed." : `<span class="spin" style="display:inline-block;vertical-align:-2px;margin-right:8px"></span>Opening the document...`}</div>`;
  let order = 0;
  const bad = ev.boxes.filter((b) => evClass(ev.flags[b.key]) === "bad"), top = bad.sort((a, b) => a.page - b.page || a.box[0] - b.box[0])[0];
  return pages.map((pg) => {
    let callout = "";
    const rects = ev.boxes.filter((b) => b.page === pg.n).map((b) => {
      const st = (r.stages[stageFor(b.key)] || {}).status;
      if (!opts.all && (!st || st === "pending" || st === "running")) return "";
      const [y0, x0, y1, x1] = b.box, pad = 6, cls = evClass(ev.flags[b.key]);
      if (b === top && opts.callout) {
        // keep the label inside the page: right-anchored on the right half, below the box near the top edge
        const side = x0 > 450 ? `right:${100 - x1 / 10}%` : `left:${x0 / 10}%`, below = y0 < 60;
        callout = `<span class="callout ${x0 > 450 ? "r" : ""} ${below ? "below" : ""}" style="${side};top:${(below ? y1 + 8 : y0) / 10}%">${esc(opts.callout)}</span>`;
      }
      return `<rect class="ev ${cls}" data-key="${esc(b.key)}" style="animation-delay:${(order++) * 60}ms"
        x="${x0 - pad}" y="${y0 - pad}" width="${x1 - x0 + 2 * pad}" height="${y1 - y0 + 2 * pad}" rx="6"><title>${esc(b.label)}</title></rect>`;
    }).join("");
    const img = pg.url ? `<img alt="Invoice page ${pg.n}" src="${pg.url}">` : `<div class="empty">Rendering page...</div>`;
    return `<div class="page ${reading ? "scanning" : ""}">${img}
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>${callout}</div>`;
  }).join("") + (ev.status === "locating" ? `<p class="locating"><span class="spin"></span>Locating values on the page...</p>` : "");
}

function wireEvidence(root, onPick) {
  // Elements are re-created on re-render; mark wired ones so listeners are attached once.
  const sel = (k) => root.querySelectorAll(`[data-key="${CSS.escape(k)}"]`);
  root.querySelectorAll("[data-key]").forEach((el) => {
    if (el.dataset.wired) return;
    el.dataset.wired = "1";
    el.addEventListener("mouseenter", () => sel(el.dataset.key).forEach((n) => n.classList.add("focus")));
    el.addEventListener("mouseleave", () => sel(el.dataset.key).forEach((n) => n.classList.remove("focus")));
    if (el.tagName === "rect") el.addEventListener("click", () => onPick && onPick(el.dataset.key));
  });
}

async function compareOriginal(r) {
  const orig = r.decision.primary && r.stages.duplicates.details && r.stages.duplicates.details.original;
  if (!orig) return;
  let left;
  if (orig.run_id) {
    const o = await api(`/api/runs/${orig.run_id}`);
    left = `<h3>Original: ${esc(orig.invoice_number)} <span class="pill plain ${orig.status === "paid" || orig.status === "approved" ? "dec-APPROVE" : "dec-HOLD"}">${esc(orig.status.replace(/_/g, " "))}</span></h3>
      <p class="mono muted cmp-file">${esc(o.filename)}${orig.processed_at ? ` · processed ${ago(orig.processed_at)}` : ""}</p>${docViewer({ ...o, phase: "done" }, { all: true })}`;
  } else {
    const o = await api(`/api/originals/${encodeURIComponent(orig.invoice_number)}`);
    left = `<h3>Original: ${esc(orig.invoice_number)} <span class="pill plain ${orig.status === "paid" || orig.status === "approved" ? "dec-APPROVE" : "dec-HOLD"}">${esc(orig.status.replace(/_/g, " "))}</span></h3>
      <p class="mono muted cmp-file">${esc(orig.invoice_number)}.pdf · opening ledger</p>` + docViewer({ id: "orig", phase: "done", mime: "image/png",
      stages: {}, evidence: { status: "ready", pages: [{ n: 1, url: o.url }], boxes: o.boxes,
        flags: Object.fromEntries(o.boxes.map((b) => [b.key, "hold"])) } }, { all: true });
  }
  const right = `<h3>This invoice: ${esc((r.extraction.fields.invoice_number || {}).value || r.filename)} <span class="pill plain dec-${r.decision.decision}">${DECISION_WORD[r.decision.decision].toLowerCase()}</span></h3>
    <p class="mono muted cmp-file">${esc(r.filename)}</p>${docViewer(r, { all: true })}`;
  const modal = h(`<div class="modal" role="dialog" aria-label="Compare with original"><div class="modal-card">
    <div class="row between"><div><b style="font-size:17px">${esc(r.decision.primary.title)}</b><p class="muted" style="margin:4px 0 0">${esc(r.decision.primary.message)}</p></div>
    <button class="btn" data-close>Close</button></div>
    <div class="compare"><section>${left}</section><section>${right}</section></div></div></div>`).firstElementChild;
  modal.querySelector("[data-close]").onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
  document.body.append(modal);
  wireEvidence(modal);
}
