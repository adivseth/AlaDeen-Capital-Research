/* AlaDeen Capital Research — dashboard */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (v, d = 2) => (v == null || isNaN(v) ? "—" : "₹" + Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%");
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

let ROSTER = null;
let active = { runId: null, stop: true };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* not json */ }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("on"), ms);
}

function ratingPill(r, q) {
  if (!r) return "";
  return `<span class="pill ${esc(r)}">${esc(r)}${q ? " · " + esc(q) : ""}</span>`;
}
function statusPill(s, demo) {
  const label = { running: "Researching", done: "Published", error: "Failed", queued: "Queued" }[s] || s;
  return `<span class="pill ${esc(s)}">${s === "running" ? '<i class="spin"></i>' : ""}${esc(label)}</span>${demo ? ' <span class="pill demo">Demo</span>' : ""}`;
}

/* ------------------------------------------------------------------ router */
async function route() {
  active.stop = true;
  const h = location.hash.replace(/^#/, "") || "/";
  const [, page, id] = h.split("/");
  $$(".sidebar nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === (page || "home") || (page === "run" && a.dataset.nav === "office")));
  try {
    if (!ROSTER) ROSTER = await api("/api/roster");
    refreshModelChip();
    if (!page) return await renderHome();
    if (page === "run" && id) return await renderRun(id);
    if (page === "office") {
      const runs = await api("/api/runs");
      const live = runs.find((r) => r.status === "running") || runs[0];
      if (live) { location.hash = "#/run/" + live.id; return; }
      return renderEmptyOffice();
    }
    if (page === "history") return await renderHistory();
    if (page === "calls") return await renderCalls();
    if (page === "settings") return await renderSettings();
    await renderHome();
  } catch (e) {
    view.innerHTML = `<div class="card"><h3>Something went wrong</h3><p class="muted">${esc(e.message)}</p></div>`;
  }
}
window.addEventListener("hashchange", route);

async function refreshModelChip() {
  try {
    const s = await api("/api/settings");
    const p = s.providers.find((x) => x.id === s.values.llm_provider);
    $("#model-chip").innerHTML = `<b>${esc(p ? p.label : s.values.llm_provider)}</b><br><span class="tiny">CIO: ${esc(s.values.deep_think_llm)}<br>Analysts: ${esc(s.values.quick_think_llm)}</span>`;
  } catch (_) { /* ignore */ }
}

/* ------------------------------------------------------------------ home */
async function renderHome() {
  const runs = await api("/api/runs");
  const done = runs.filter((r) => r.status === "done" && !r.demo);
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  view.innerHTML = `
  <div class="hero">
    <div class="deco">🧭</div>
    <h1>What should the firm research today?</h1>
    <p>Name an NSE or BSE company. The CIO will brief the research desks, review their work, run the bull-vs-bear debate and the risk office, and sign an institutional-grade report. You can watch every step in the live office.</p>
    <form id="newform">
      <input class="big" id="ticker" placeholder="Ticker or BSE code — e.g. TCS, RELIANCE, 532540" autocomplete="off" autofocus>
      <input id="asof" type="date" value="${today}" max="${today}" title="Analysis date">
      <button class="btn primary" type="submit">Start research →</button>
      <button class="btn" type="button" id="demo">Try the demo</button>
    </form>
  </div>
  <div class="grid g4" style="margin:18px 0">
    <div class="card stat"><div class="l">Researches</div><div class="n">${runs.filter((r) => !r.demo).length}</div></div>
    <div class="card stat"><div class="l">BUY calls</div><div class="n" style="color:var(--green)">${done.filter((r) => r.rating === "BUY").length}</div></div>
    <div class="card stat"><div class="l">HOLD calls</div><div class="n" style="color:var(--amber)">${done.filter((r) => r.rating === "HOLD").length}</div></div>
    <div class="card stat"><div class="l">SELL calls</div><div class="n" style="color:var(--red)">${done.filter((r) => r.rating === "SELL").length}</div></div>
  </div>
  <div class="page-head"><div><h1 style="font-size:18px">Recent research</h1></div><a href="#/history" class="btn ghost">Open archive →</a></div>
  ${runs.length ? `<div class="rcards">${runs.slice(0, 8).map(rcard).join("")}</div>` :
    `<div class="card empty"><div class="e">🗂️</div>No research yet. Start one above, or try the demo to see the office at work.</div>`}`;
  $("#newform").onsubmit = (e) => { e.preventDefault(); startResearch($("#ticker").value, $("#asof").value); };
  $("#demo").onclick = () => startResearch("DEMO", null, true);
  $$(".rcard").forEach((c) => (c.onclick = () => (location.hash = "#/run/" + c.dataset.id)));
}

function rcard(r) {
  return `<div class="rcard" data-id="${esc(r.id)}">
    <div class="row">${statusPill(r.status, r.demo)}${ratingPill(r.rating, r.qualifier)}</div>
    <div class="t">${esc(r.company || r.ticker)}</div>
    <div class="muted small">${esc(r.ticker)} · as of ${esc(r.as_of)}</div>
    ${r.status === "done" ? `<div class="row small" style="margin-top:10px"><span>Target <b>${inr(r.target_price, 0)}</b></span><span>${pct(r.upside)}</span></div>` : ""}
    ${r.status === "error" ? `<div class="small" style="color:var(--red);margin-top:8px">${esc((r.error || "").slice(0, 90))}</div>` : ""}
  </div>`;
}

async function startResearch(ticker, asOf, demo = false) {
  ticker = (ticker || "").trim();
  if (!ticker && !demo) return toast("Enter a ticker first");
  try {
    const r = await api("/api/research", { method: "POST", body: JSON.stringify({ ticker, as_of: asOf || null, demo }) });
    location.hash = "#/run/" + r.id;
  } catch (e) { toast(e.message, 4000); }
}

function renderEmptyOffice() {
  view.innerHTML = `<div class="page-head"><div><h1>Live office</h1><p>Start a research to see the team at work.</p></div></div>
  ${officeHTML()}<div class="card empty" style="margin-top:16px"><div class="e">🏢</div>The office is quiet. <a href="#/">Start a research</a> or try the demo.</div>`;
}

/* ------------------------------------------------------------------ office */
function officeHTML() {
  const rooms = ROSTER.rooms.map((room) => {
    const desks = ROSTER.agents.filter((a) => a.room === room.id).map((a) => `
      <div class="desk" id="desk-${a.id}" title="${esc(a.role)}" style="color:${a.color}">
        <span class="st"></span>
        <div class="av" style="background:${a.color}1a">${a.icon}</div>
        <div class="nm" style="color:var(--ink)">${esc(a.short)}</div>
        <div class="ti">${esc(a.title)}</div>
        <div class="screen"><i></i></div>
        <div class="task" style="color:var(--ink2)">Idle</div>
      </div>`).join("");
    return `<div class="room ${room.id}"><div class="rlabel">${esc(room.title)}</div><div class="desks">${desks}</div></div>`;
  }).join("");
  return `<div class="office" id="office">${rooms}</div>`;
}

function phasesHTML() {
  return `<div class="phases" id="phases">${ROSTER.phases.map((p, i) => `<div class="phase" id="ph-${p.id}"><span class="dot"></span>${i + 1}. ${esc(p.title)}</div>`).join("")}</div>`;
}

function agentMeta(id) { return ROSTER.agents.find((a) => a.id === id) || { icon: "•", title: id, short: id, color: "#64748b" }; }

function setDesk(id, status, task) {
  const d = $("#desk-" + id);
  if (!d) return;
  d.classList.remove("working", "waiting", "done", "error", "idle");
  d.classList.add(status);
  const label = task || { done: "Done", waiting: "Waiting", working: "Working" }[status] || "";
  $(".task", d).innerHTML = esc(label) + (status === "working" ? '<span class="typing"><i></i><i></i><i></i></span>' : "");
}

function flyEnvelope(from, to) {
  const office = $("#office");
  const a = $("#desk-" + from), b = $("#desk-" + to);
  if (!office || !a || !b) return;
  const ob = office.getBoundingClientRect(), ab = a.getBoundingClientRect(), bb = b.getBoundingClientRect();
  const env = document.createElement("div");
  env.className = "envelope";
  env.textContent = "✉️";
  env.style.left = ab.left - ob.left + ab.width / 2 - 10 + "px";
  env.style.top = ab.top - ob.top + 18 + "px";
  office.appendChild(env);
  requestAnimationFrame(() => {
    env.style.transform = `translate(${bb.left - ab.left}px, ${bb.top - ab.top}px)`;
  });
  setTimeout(() => { env.style.opacity = "0"; }, 1100);
  setTimeout(() => env.remove(), 1500);
}

function feedItem(e) {
  const m = agentMeta(e.agent);
  if (e.type === "message") {
    const t = agentMeta(e.to);
    return `<li class="msg"><div class="ic">${m.icon}</div><div><div class="who">${esc(m.short)} <span class="to">→ ${esc(t.title)}</span></div><div class="tx">${esc(e.text)}</div><div class="tm">${clock(e.ts)}</div></div></li>`;
  }
  if (e.type === "log") {
    return `<li><div class="ic">${m.icon}</div><div><div class="who">${esc(m.title)}</div><div class="tx">${esc(e.text)}</div>${e.detail ? `<details><summary>Show detail</summary><div>${esc(e.detail)}</div></details>` : ""}<div class="tm">${clock(e.ts)}</div></div></li>`;
  }
  if (e.type === "error") {
    return `<li class="err"><div class="ic">⚠️</div><div><div class="who">Research stopped</div><div class="tx">${esc(e.text)}</div><div class="tm">${clock(e.ts)}</div></div></li>`;
  }
  if (e.type === "done") {
    return `<li><div class="ic">🏁</div><div><div class="who">Report published</div><div class="tx">${esc(e.rating)}${e.qualifier ? " (" + esc(e.qualifier) + ")" : ""} · target ${inr(e.target_price)} · ${pct(e.upside)} · ${esc(e.seconds)}s · ${esc(e.llm_calls)} AI calls</div><div class="tm">${clock(e.ts)}</div></div></li>`;
  }
  return "";
}

/* ------------------------------------------------------------------ run page */
async function renderRun(id) {
  const rec = await api("/api/runs/" + id);
  active = { runId: id, stop: false };
  view.innerHTML = `
  <div class="runhead">
    <div class="logo" id="rlogo">🏢</div>
    <div><h1 id="rname">${esc(rec.company || rec.ticker)}</h1><div class="meta"><span id="rticker">${esc(rec.ticker)}</span> · as of ${esc(rec.as_of)} · started ${when(rec.created_at)}</div></div>
    <div class="right"><span id="rstatus">${statusPill(rec.status, rec.demo)}</span><span class="muted small" id="elapsed"></span></div>
  </div>
  <div id="banner"></div>
  <div class="tabs" id="tabs">
    <button data-tab="office" class="on">🏢 Live office</button>
    <button data-tab="report">📄 Report</button>
    <button data-tab="file">🗒️ Research file</button>
    <button data-tab="downloads">⬇️ Downloads</button>
  </div>
  <div id="tab-office">${phasesHTML()}
    <div class="officewrap">${officeHTML()}
      <div class="card feed"><h3><span>Activity</span><span class="muted small" id="fcount"></span></h3><ul id="feed"></ul></div>
    </div>
  </div>
  <div id="tab-report" hidden></div>
  <div id="tab-file" hidden></div>
  <div id="tab-downloads" hidden></div>`;
  $$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab, rec)));
  if (rec.status === "done") showBanner(rec);
  if (rec.status === "error") showError(rec.error);
  followEvents(id, rec);
}

function showTab(tab, rec) {
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  ["office", "report", "file", "downloads"].forEach((t) => ($("#tab-" + t).hidden = t !== tab));
  const id = encodeURIComponent(rec.id);
  if (tab === "report") {
    $("#tab-report").innerHTML = rec.status === "done" || $("#banner").dataset.done
      ? `<iframe class="reportframe" src="/api/runs/${id}/report"></iframe>`
      : `<div class="card empty"><div class="e">✍️</div>The report will appear here when the CIO signs off.</div>`;
  }
  if (tab === "file") loadTranscript(id);
  if (tab === "downloads") {
    $("#tab-downloads").innerHTML = `<div class="grid g3">
      ${dl("📄", "Report (HTML)", "Self-contained web page with all charts", `/api/runs/${id}/report?download=1`)}
      ${dl("🖨️", "Report (PDF)", "Opens the print dialog — choose “Save as PDF”", `/api/runs/${id}/report?print=1`, true)}
      ${dl("🗒️", "Research file (Markdown)", "CIO mandate, memos, debate, decisions", `/api/runs/${id}/file/transcript.md`)}
      ${dl("🧾", "Research data (JSON)", "Every agent output and the valuation", `/api/runs/${id}/file/research.json`)}
      ${dl("🗄️", "Fact pack (JSON)", "All data the team worked from", `/api/runs/${id}/file/factpack.json`)}
      ${dl("📜", "Event log (JSON)", "Timeline of the office", `/api/runs/${id}/file/events.json`)}
    </div>`;
  }
}

function dl(icon, title, sub, href, newTab = false) {
  return `<a class="card" href="${href}" ${newTab ? 'target="_blank" rel="noopener"' : ""} style="display:flex;gap:14px;align-items:center;color:inherit">
    <div style="font-size:28px">${icon}</div><div><b>${title}</b><div class="muted small">${sub}</div></div></a>`;
}

async function loadTranscript(id) {
  const box = $("#tab-file");
  try {
    const md = await api(`/api/runs/${id}/transcript`);
    box.innerHTML = `<div class="md">${renderMarkdown(md)}</div>`;
  } catch (_) {
    box.innerHTML = `<div class="card empty"><div class="e">🗒️</div>The research file is written when the report is published.</div>`;
  }
}

function showBanner(rec) {
  const b = $("#banner");
  const id = encodeURIComponent(rec.id);
  b.dataset.done = "1";
  b.innerHTML = `<div class="banner">
    <div><div class="k">Rating</div><div class="big">${ratingPill(rec.rating, rec.qualifier)}</div></div>
    <div><div class="k">Target price</div><div class="big">${inr(rec.target_price)}</div></div>
    <div><div class="k">CMP</div><div class="big">${inr(rec.cmp)}</div></div>
    <div><div class="k">Upside</div><div class="big" style="color:${rec.upside >= 0 ? "var(--green)" : "var(--red)"}">${pct(rec.upside)}</div></div>
    ${rec.council_verdict ? `<div><div class="k">Council</div><div class="big" style="font-size:16px">${esc(rec.council_verdict)}</div></div>` : ""}
    <div class="actions">
      <button class="btn primary" id="viewrep">View report</button>
      <a class="btn" href="/api/runs/${id}/report?print=1" target="_blank" rel="noopener">PDF</a>
      <a class="btn" href="/api/runs/${id}/report?download=1">HTML</a>
    </div></div>
    ${rec.headline ? `<p class="muted" style="margin:-6px 0 14px">${esc(rec.headline)}</p>` : ""}`;
  $("#viewrep").onclick = () => showTab("report", { ...rec, status: "done" });
}

function showError(msg) {
  $("#banner").innerHTML = `<div class="banner err"><div><div class="k">Research stopped</div><div>${esc(msg || "Unknown error")}</div></div>
    <div class="actions"><a class="btn" href="#/settings">Check settings</a></div></div>`;
}

async function followEvents(id, rec) {
  let since = 0, first = null, count = 0;
  const live = rec.status === "running";
  const tick = setInterval(() => {
    if (active.runId !== id || active.stop) return clearInterval(tick);
    if (first && live) $("#elapsed").textContent = Math.round(Date.now() / 1000 - first) + "s";
  }, 1000);
  while (active.runId === id && !active.stop) {
    let res;
    try { res = await api(`/api/runs/${encodeURIComponent(id)}/events?since=${since}&wait=10`); }
    catch (e) { await new Promise((r) => setTimeout(r, 2000)); continue; }
    for (const e of res.events) {
      if (active.runId !== id || active.stop) return;
      since = e.seq + 1;
      first = first || e.ts;
      apply(e, live && !res.closed);
      if (["message", "log", "error", "done"].includes(e.type)) {
        const f = $("#feed");
        if (f) { f.insertAdjacentHTML("afterbegin", feedItem(e)); count++; $("#fcount").textContent = count + " updates"; }
      }
    }
    if (res.closed) {
      let fresh = await api("/api/runs/" + encodeURIComponent(id));
      for (let i = 0; i < 20 && fresh.status === "running"; i++) {
        await new Promise((r) => setTimeout(r, 500));
        fresh = await api("/api/runs/" + encodeURIComponent(id));
      }
      if (active.runId !== id) return;
      $("#rstatus").innerHTML = statusPill(fresh.status, fresh.demo);
      if (fresh.seconds) $("#elapsed").textContent = fresh.seconds + "s";
      if (fresh.status === "done" && !$("#banner").dataset.done) { showBanner(fresh); if (live) { toast("Report published"); showTab("report", fresh); } }
      if (fresh.status === "error") showError(fresh.error);
      break;
    }
  }
  clearInterval(tick);
}

function apply(e, animate) {
  if (e.type === "phase") {
    const p = $("#ph-" + e.phase);
    if (p) { p.classList.remove("active", "done"); p.classList.add(e.status === "done" ? "done" : "active"); }
  } else if (e.type === "agent") {
    setDesk(e.agent, e.status, e.task);
  } else if (e.type === "message") {
    if (animate) flyEnvelope(e.agent, e.to);
    const t = $("#desk-" + e.to);
    if (t && !t.classList.contains("working")) setDesk(e.to, "waiting", "📩 " + e.text);
  } else if (e.type === "company") {
    if (e.name) $("#rname").textContent = e.name;
    if (e.logo && /^(data:image\/|https?:\/\/)/.test(e.logo)) {
      const img = document.createElement("img");
      img.src = e.logo; img.alt = "";
      img.onerror = () => { $("#rlogo").textContent = "🏢"; };
      $("#rlogo").replaceChildren(img);
    }
    if (e.ticker) $("#rticker").textContent = (e.exchange ? e.exchange + ": " : "") + e.ticker;
  } else if (e.type === "error") {
    $$(".desk.working").forEach((d) => setDesk(d.id.slice(5), "error", "Stopped"));
    showError(e.text);
  }
}

/* ------------------------------------------------------------------ archive */
async function renderHistory() {
  const runs = await api("/api/runs");
  view.innerHTML = `<div class="page-head"><div><h1>Research archive</h1><p>Every research your firm has run on this computer.</p></div>
    <div style="display:flex;gap:10px"><input id="q" placeholder="Search company or ticker" style="width:240px">
    <select id="rf" style="width:140px"><option value="">All ratings</option><option>BUY</option><option>HOLD</option><option>SELL</option></select></div></div>
    <div class="card" style="padding:6px 8px"><table class="t"><thead><tr><th>Company</th><th>As of</th><th>Status</th><th>Rating</th><th class="num">Target</th><th class="num">CMP</th><th class="num">Upside</th><th>Council</th><th>Run on</th><th></th></tr></thead><tbody id="rows"></tbody></table>
    <div id="none" class="empty" hidden><div class="e">🗂️</div>Nothing here yet.</div></div>`;
  const draw = () => {
    const q = $("#q").value.toLowerCase(), rf = $("#rf").value;
    const list = runs.filter((r) => (!q || ((r.company || "") + r.ticker).toLowerCase().includes(q)) && (!rf || r.rating === rf));
    $("#none").hidden = list.length > 0;
    $("#rows").innerHTML = list.map((r) => `<tr data-id="${esc(r.id)}" style="cursor:pointer">
      <td><b>${esc(r.company || r.ticker)}</b><div class="muted small">${esc(r.ticker)}</div></td><td>${esc(r.as_of)}</td>
      <td>${statusPill(r.status, r.demo)}</td><td>${ratingPill(r.rating, r.qualifier)}</td>
      <td class="num">${inr(r.target_price, 0)}</td><td class="num">${inr(r.cmp, 0)}</td><td class="num">${r.status === "done" ? pct(r.upside) : "—"}</td>
      <td>${esc(r.council_verdict || "—")}</td><td class="small muted">${when(r.created_at)}</td>
      <td><button class="btn ghost danger" data-del="${esc(r.id)}" title="Delete">🗑</button></td></tr>`).join("");
    $$("#rows tr").forEach((tr) => (tr.onclick = (ev) => { if (!ev.target.closest("[data-del]")) location.hash = "#/run/" + tr.dataset.id; }));
    $$("[data-del]").forEach((b) => (b.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm("Delete this research and its files?")) return;
      try {
        await api("/api/runs/" + encodeURIComponent(b.dataset.del), { method: "DELETE" });
        runs.splice(runs.findIndex((x) => x.id === b.dataset.del), 1); draw(); toast("Deleted");
      } catch (e) { toast(e.message); }
    }));
  };
  $("#q").oninput = draw; $("#rf").onchange = draw; draw();
}

/* ------------------------------------------------------------------ call log */
async function renderCalls() {
  const data = await api("/api/calls");
  const s = data.summary || {};
  view.innerHTML = `<div class="page-head"><div><h1>Call log</h1><p>Every published rating, scored against the Nifty 50 after 12 months.</p></div>
    <button class="btn primary" id="score">🎯 Score my calls</button></div>
    <div class="grid g4" style="margin-bottom:18px">
      <div class="card stat"><div class="l">Calls</div><div class="n">${s.calls ?? 0}</div></div>
      <div class="card stat"><div class="l">Matured (12m+)</div><div class="n">${s.matured_12m ?? 0}</div></div>
      <div class="card stat"><div class="l">Hit rate</div><div class="n">${s.hit_rate == null ? "—" : Math.round(s.hit_rate * 100) + "%"}</div></div>
      <div class="card stat"><div class="l">Avg alpha</div><div class="n">${s.avg_alpha_all == null ? "—" : pct(s.avg_alpha_all)}</div></div>
    </div>
    <div class="card" style="padding:6px 8px">${data.rows.length ? `<table class="t"><thead><tr><th>ID</th><th>Date</th><th>Company</th><th>Rating</th><th class="num">Target</th><th class="num">Price then</th><th>Reviewed</th><th class="num">Return</th><th class="num">Alpha</th><th>Verdict</th></tr></thead><tbody>
      ${data.rows.map((r) => `<tr><td>${esc(r.call_id)}</td><td>${esc(r.call_date)}</td><td><b>${esc(r.company)}</b><div class="muted small">${esc(r.ticker)}</div></td>
      <td>${ratingPill((r.rating || "").split(" ")[0])}</td><td class="num">${esc(r.target_price)}</td><td class="num">${esc(r.close_on_call_date)}</td>
      <td>${esc(r.review_date || "—")}</td><td class="num">${r.stock_return ? pct(+r.stock_return) : "—"}</td><td class="num">${r.alpha ? pct(+r.alpha) : "—"}</td><td>${esc(r.verdict || "Not scored")}</td></tr>`).join("")}
    </tbody></table>` : `<div class="empty"><div class="e">🎯</div>No calls yet. Each published research adds one.</div>`}</div>`;
  $("#score").onclick = async () => {
    const b = $("#score"); b.disabled = true; b.textContent = "Scoring…";
    try { await api("/api/calls/score", { method: "POST" }); toast("Calls scored"); renderCalls(); }
    catch (e) { toast(e.message, 4000); b.disabled = false; b.textContent = "🎯 Score my calls"; }
  };
}

/* ------------------------------------------------------------------ settings */
async function renderSettings() {
  const s = await api("/api/settings");
  const v = s.values;
  const P = (x) => (x == null ? "" : +(x * 100).toFixed(3));
  const provOpts = s.providers.map((p) => `<option value="${p.id}" ${p.id === v.llm_provider ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  const tierOpts = (cur) => `<option value="">Same as main provider</option>` + s.providers.map((p) => `<option value="${p.id}" ${p.id === cur ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  const keyRows = s.providers.filter((p) => p.key).map((p) => {
    const k = s.keys[p.id] || {};
    return `<div class="keyrow"><b>${esc(p.label)}</b><input type="password" data-key="${p.id}" placeholder="${k.set ? "Saved — leave blank to keep" : "Paste API key"}" autocomplete="off">
      <span class="state">${k.set ? `<span class="pill done">${esc(k.masked)}</span> <span class="muted tiny">${esc(k.source)}</span> ${k.source === "dashboard" ? `<button class="btn ghost danger" data-clear="${p.id}" type="button">Remove</button>` : ""}` : '<span class="pill demo">Not set</span>'}</span></div>`;
  }).join("");
  const desks = s.desks.map((d) => { const a = agentMeta(d); return `<label><input type="checkbox" data-desk="${d}" ${v.desks.includes(d) ? "checked" : ""}> ${a.icon} ${esc(a.title)}</label>`; }).join("");
  view.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Saved on this computer in <code>${esc(s.paths.settings)}</code>. API keys never leave your machine except to call the provider you choose.</p></div></div>
  <div class="settings"><div class="toc"><a href="#s-models" data-jump>🧠 AI models</a><a href="#s-keys" data-jump>🔑 API keys</a><a href="#s-team" data-jump>👥 Research team</a><a href="#s-data" data-jump>🗄️ Data</a><a href="#s-val" data-jump>🧮 Valuation</a><a href="#s-brand" data-jump>🏷️ Report &amp; dashboard</a><a href="#s-store" data-jump>📁 Storage</a></div>
  <form id="sform">
  <section class="card" id="s-models"><h3>🧠 AI models</h3>
    <div class="row2"><div class="field"><label class="f">Provider</label><select id="llm_provider">${provOpts}</select><div class="hint">Claude, OpenAI, Gemini, Grok, OpenRouter, a local Ollama model or any OpenAI-compatible server.</div></div>
    <div class="field" id="burl"><label class="f">Server URL</label><input id="backend_url" value="${esc(v.backend_url || "")}" placeholder="http://localhost:11434/v1"><div class="hint">Only for Ollama or OpenAI-compatible servers.</div></div></div>
    <div class="row2"><div class="field"><label class="f">Senior model — CIO, Valuation, Chief Risk Officer</label><input id="deep_think_llm" value="${esc(v.deep_think_llm)}" list="models"></div>
    <div class="field"><label class="f">Analyst model — research desks, advocates, council</label><input id="quick_think_llm" value="${esc(v.quick_think_llm)}" list="models"></div></div>
    <datalist id="models">${s.providers.flatMap((p) => [p.deep, p.quick]).filter(Boolean).map((m) => `<option value="${esc(m)}">`).join("")}</datalist>
    <div class="row2"><div class="field"><label class="f">Senior tier provider (optional)</label><select id="deep_provider">${tierOpts(v.deep_provider)}</select></div>
    <div class="field"><label class="f">Analyst tier provider (optional)</label><select id="quick_provider">${tierOpts(v.quick_provider)}</select></div></div>
    <div class="row3"><div class="field"><label class="f">Temperature</label><input id="temperature" type="number" step="0.05" min="0" max="1" value="${v.temperature}"></div>
    <div class="field"><label class="f">Max tokens per answer</label><input id="max_tokens" type="number" min="1000" step="500" value="${v.max_tokens}"></div>
    <div class="field"><label class="f">Report language</label><input id="output_language" value="${esc(v.output_language)}"></div></div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn" type="button" data-test="deep">Test senior model</button><button class="btn" type="button" data-test="quick">Test analyst model</button><span class="small muted" id="testout">Save first, then test.</span></div>
  </section>
  <section class="card" id="s-keys"><h3>🔑 API keys</h3>${keyRows}<div class="hint">Keys entered here are stored in your settings file (readable only by you). Keys in your environment or <code>.env</code> also work.</div></section>
  <section class="card" id="s-team"><h3>👥 Research team</h3>
    <label class="f">Research desks the CIO can brief</label><div class="desk-check" style="margin-bottom:14px">${desks}</div>
    <div class="row3"><div class="field"><label class="f">CIO revision rounds</label><input id="cio_revision_rounds" type="number" min="0" max="3" value="${v.cio_revision_rounds}"><div class="hint">How many times the CIO may send memos back.</div></div>
    <div class="field"><label class="f">Debate rebuttal rounds</label><input id="max_debate_rounds" type="number" min="0" max="4" value="${v.max_debate_rounds}"></div>
    <div class="field"><label class="f">&nbsp;</label><label class="switch"><input type="checkbox" id="run_council" ${v.run_council ? "checked" : ""}> Independent council review</label><label class="switch" style="margin-top:8px"><input type="checkbox" id="log_calls" ${v.log_calls ? "checked" : ""}> Add calls to the call log</label></div></div>
  </section>
  <section class="card" id="s-data"><h3>🗄️ Data</h3>
    <div class="row3"><div class="field"><label class="switch"><input type="checkbox" id="fetch_documents" ${v.fetch_documents ? "checked" : ""}> Read annual reports &amp; concall transcripts</label></div>
    <div class="field"><label class="f">Reading depth</label><select id="document_mode"><option value="focused" ${v.document_mode === "focused" ? "selected" : ""}>Focused (key sections)</option><option value="full" ${v.document_mode === "full" ? "selected" : ""}>Every page (slow, costly)</option></select></div>
    <div class="field"><label class="f">News look-back (days)</label><input id="news_lookback_days" type="number" min="7" max="365" value="${v.news_lookback_days}"></div></div>
    <div class="row3"><div class="field"><label class="f">Annual reports to read</label><input id="max_annual_reports" type="number" min="0" max="10" value="${v.max_annual_reports}"></div>
    <div class="field"><label class="f">Concall transcripts to read</label><input id="max_concall_transcripts" type="number" min="0" max="8" value="${v.max_concall_transcripts}"></div></div>
  </section>
  <section class="card" id="s-val"><h3>🧮 Valuation</h3>
    <div class="row3"><div class="field"><label class="f">Risk-free rate (10Y G-Sec, %)</label><input data-pct id="risk_free_rate" type="number" step="0.01" value="${P(v.risk_free_rate)}"></div>
    <div class="field"><label class="f">India equity risk premium (%)</label><input data-pct id="equity_risk_premium" type="number" step="0.01" value="${P(v.equity_risk_premium)}"></div>
    <div class="field"><label class="f">Tax rate (%)</label><input data-pct id="tax_rate" type="number" step="0.01" value="${P(v.tax_rate)}"></div></div>
    <div class="row3"><div class="field"><label class="f">Terminal growth cap (%)</label><input data-pct id="terminal_growth_cap" type="number" step="0.1" value="${P(v.terminal_growth_cap)}"></div>
    <div class="field"><label class="f">Weight of intrinsic value (%)</label><input data-pct id="dcf_weight" type="number" step="5" value="${P(v.dcf_weight)}"><div class="hint">The rest is the peer-multiple value.</div></div>
    <div class="field"><label class="f">Margin of safety (%)</label><input data-pct id="margin_of_safety" type="number" step="1" value="${P(v.margin_of_safety)}"></div></div>
    <label class="f">Scenario probabilities (%) — bear / base / bull</label>
    <div class="row3"><input data-prob="bear" type="number" value="${P(v.scenario_probabilities.bear)}"><input data-prob="base" type="number" value="${P(v.scenario_probabilities.base)}"><input data-prob="bull" type="number" value="${P(v.scenario_probabilities.bull)}"></div>
    <div class="row2" style="margin-top:14px"><div class="field"><label class="f">BUY if expected 12-month return is above (%)</label><input data-band="buy" type="number" value="${P(v.rating_bands.buy)}"></div>
    <div class="field"><label class="f">SELL if expected 12-month return is below (%)</label><input data-band="sell" type="number" value="${P(v.rating_bands.sell)}"></div></div>
  </section>
  <section class="card" id="s-brand"><h3>🏷️ Report &amp; dashboard</h3>
    <div class="row2"><div class="field"><label class="f">Firm name on reports</label><input id="firm_name" value="${esc(v.firm_name)}"></div>
    <div class="field"><label class="f">Analyst credit on reports</label><input id="analyst_name" value="${esc(v.analyst_name)}"></div></div>
    <div class="row2"><div class="field"><label class="f">Dashboard port</label><input id="port" type="number" value="${v.port}"><div class="hint">Takes effect next time you start the app.</div></div>
    <div class="field"><label class="f">&nbsp;</label><label class="switch"><input type="checkbox" id="open_browser" ${v.open_browser ? "checked" : ""}> Open the browser automatically</label></div></div>
  </section>
  <section class="card" id="s-store"><h3>📁 Storage</h3><div class="small">Research archive: <code>${esc(s.paths.research)}</code><br>Call log: <code>${esc(s.paths.call_log)}</code><br>App folder: <code>${esc(s.paths.home)}</code></div></section>
  <div class="savebar"><button class="btn" type="button" id="reset">Discard changes</button><button class="btn primary" type="submit">Save settings</button></div>
  </form></div>`;
  const syncUrl = () => ($("#burl").style.opacity = ["ollama", "openai_compatible"].includes($("#llm_provider").value) ? "1" : ".45");
  $("#llm_provider").onchange = () => {
    const p = s.providers.find((x) => x.id === $("#llm_provider").value);
    if (p && p.deep) { $("#deep_think_llm").value = p.deep; $("#quick_think_llm").value = p.quick; }
    else { $("#deep_think_llm").value = ""; $("#quick_think_llm").value = ""; toast("Enter this provider's model names"); }
    syncUrl();
  };
  syncUrl();
  $$("[data-jump]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); $(a.getAttribute("href")).scrollIntoView({ behavior: "smooth" }); }));
  $("#reset").onclick = () => renderSettings();
  $$("[data-clear]").forEach((b) => (b.onclick = async () => {
    try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ clear_keys: [b.dataset.clear] }) }); toast("Key removed"); renderSettings(); }
    catch (e) { toast(e.message, 4000); }
  }));
  $$("[data-test]").forEach((b) => (b.onclick = async () => {
    $("#testout").textContent = "Calling the model…";
    try {
      const r = await api("/api/settings/test", { method: "POST", body: JSON.stringify({ tier: b.dataset.test }) });
      $("#testout").innerHTML = r.ok ? `<span style="color:var(--green)">✓ Connected — model replied “${esc((r.reply || "").slice(0, 40))}”</span>` : `<span style="color:var(--red)">✗ ${esc(r.error)}</span>`;
    } catch (e) { $("#testout").innerHTML = `<span style="color:var(--red)">✗ ${esc(e.message)}</span>`; }
  }));
  $("#sform").onsubmit = async (e) => {
    e.preventDefault();
    const num = (id) => +$("#" + id).value;
    const values = {
      llm_provider: $("#llm_provider").value, backend_url: $("#backend_url").value || null,
      deep_think_llm: $("#deep_think_llm").value.trim(), quick_think_llm: $("#quick_think_llm").value.trim(),
      deep_provider: $("#deep_provider").value || null, quick_provider: $("#quick_provider").value || null,
      temperature: num("temperature"), max_tokens: num("max_tokens"), output_language: $("#output_language").value,
      desks: $$("[data-desk]").filter((c) => c.checked).map((c) => c.dataset.desk),
      cio_revision_rounds: num("cio_revision_rounds"), max_debate_rounds: num("max_debate_rounds"),
      run_council: $("#run_council").checked, log_calls: $("#log_calls").checked,
      fetch_documents: $("#fetch_documents").checked, document_mode: $("#document_mode").value,
      news_lookback_days: num("news_lookback_days"), max_annual_reports: num("max_annual_reports"), max_concall_transcripts: num("max_concall_transcripts"),
      firm_name: $("#firm_name").value, analyst_name: $("#analyst_name").value, port: num("port"), open_browser: $("#open_browser").checked,
      scenario_probabilities: Object.fromEntries($$("[data-prob]").map((i) => [i.dataset.prob, +i.value / 100])),
      rating_bands: Object.fromEntries($$("[data-band]").map((i) => [i.dataset.band, +i.value / 100])),
    };
    $$("[data-pct]").forEach((i) => (values[i.id] = +i.value / 100));
    if (!values.deep_think_llm || !values.quick_think_llm) return toast("Enter both model names");
    if (!values.desks.length) return toast("Pick at least one research desk");
    const api_keys = Object.fromEntries($$("[data-key]").filter((i) => i.value.trim()).map((i) => [i.dataset.key, i.value.trim()]));
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify({ values, api_keys }) });
      toast("Settings saved"); refreshModelChip(); renderSettings();
    } catch (err) { toast(err.message, 5000); }
  };
}

/* ------------------------------------------------------------------ tiny markdown renderer */
function renderMarkdown(md) {
  const out = [];
  let inCode = false, list = null, code = [], table = null;
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,;:])/g, "$1<i>$2</i>");
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  const closeTable = () => {
    if (!table) return;
    const rows = table.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
    const cells = (r) => r.replace(/^\s*\||\|\s*$/g, "").split("|").map((c) => inline(c.trim()));
    out.push(`<table class="t"><thead><tr>${cells(rows[0]).map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    table = null;
  };
  for (const line of md.split("\n")) {
    if (line.startsWith("```")) { if (inCode) { out.push(`<pre>${esc(code.join("\n"))}</pre>`); code = []; } else { closeList(); closeTable(); } inCode = !inCode; continue; }
    if (inCode) { code.push(line); continue; }
    if (/^\s*\|/.test(line)) { closeList(); (table = table || []).push(line); continue; }
    closeTable();
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^\s*>/.test(line)) { closeList(); out.push(`<blockquote>${inline(line.replace(/^\s*>\s?/, ""))}</blockquote>`); continue; }
    const li = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (li) { const t = /^\s*\d+\./.test(line) ? "ol" : "ul"; if (list !== t) { closeList(); out.push(`<${t}>`); list = t; } out.push(`<li>${inline(li[1])}</li>`); continue; }
    closeList();
    if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  closeList(); closeTable();
  return out.join("\n");
}

route();
