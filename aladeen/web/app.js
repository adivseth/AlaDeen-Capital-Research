/* AlaDeen Capital Research — dashboard ("The Research Desk") */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $("#view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (v, d = 2) => (v == null || isNaN(v) ? "—" : "₹" + Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v == null || isNaN(v) ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%");
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—");
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString("en-IN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

// Desk codes (the three letters on every docket) and the numerals on the floor plan.
const CODES = { cio: "CIO", data: "QNT", fundamentals: "FIN", business: "SEC", governance: "GOV", filings: "FLG", news: "INT",
  technical: "TEC", valuation: "VAL", bull: "BUL", bear: "BER", risk: "CRO", compliance: "CMP", council: "CNL", editor: "EDT" };
const code = (id) => CODES[id] || String(id || "").slice(0, 3).toUpperCase();
const ROOM_NO = { executive: "I", floor: "II", lab: "III", debate: "IV", risk: "V", council: "VI", publishing: "VII" };
const STATE_WORD = { idle: "Idle", working: "Working", waiting: "Waiting", done: "Filed", error: "Stopped" };

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

// A rating is a rubber stamp; a status is a lamp and a word.
function ratingPill(r, q, size = "") {
  if (!r) return "";
  return `<span class="stamp ${esc(r)} ${size}">${esc(r)}${q ? " · " + esc(q) : ""}</span>`;
}
function statusPill(s, demo) {
  const label = { running: "Researching", done: "Published", error: "Stopped", queued: "Queued" }[s] || s;
  return `<span class="status ${esc(s)}"><i class="lamp"></i>${esc(label)}</span>${demo ? '<span class="tag">Demo</span>' : ""}`;
}

/* ------------------------------------------------------------------ router */
async function route() {
  active.stop = true;
  const h = location.hash.replace(/^#/, "") || "/";
  const [, page, id] = h.split("/");
  $$(".mainnav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === (page || "home") || (page === "run" && a.dataset.nav === "office")));
  try {
    if (!ROSTER) ROSTER = await api("/api/roster");
    refreshMasthead();
    if (!page) return await renderHome();
    if (page === "run" && id) return await renderRun(id);
    if (page === "office") {
      const runs = await api("/api/runs");
      const live = runs.find((r) => r.status === "running") || runs[0];
      if (live) { location.hash = "#/run/" + live.id; return; }
      return renderEmptyOffice();
    }
    if (page === "history") return await renderHistory();
    if (page === "monitor") return await renderWorkbench(id);
    if (page === "calls") return await renderCalls();
    if (page === "settings") return await renderSettings();
    await renderHome();
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="e">Something went wrong</div>${esc(e.message)}</div>`;
  }
}
window.addEventListener("hashchange", route);

// The dateline, the engine line, and the ticker tape of published calls.
async function refreshMasthead() {
  $("#dateline").textContent = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  try {
    const s = await api("/api/settings");
    const p = s.providers.find((x) => x.id === s.values.llm_provider);
    $("#model-chip").textContent = `Engine · ${p ? p.label : s.values.llm_provider} · CIO ${s.values.deep_think_llm} · Desks ${s.values.quick_think_llm}`;
  } catch (_) { /* ignore */ }
  try {
    const runs = await api("/api/runs");
    const items = runs.filter((r) => r.status === "done" && !r.demo && r.rating).slice(0, 14);
    const one = items.length
      ? items.map((r) => `<span class="ti"><b>${esc(r.ticker)}</b><span class="rt ${esc(r.rating)}">${r.rating === "BUY" ? "▲" : r.rating === "SELL" ? "▼" : "■"} ${esc(r.rating)}</span><span>${inr(r.target_price, 0)}</span><span>${pct(r.upside)}</span></span>`).join("")
      : `<span class="ti">No calls on the tape yet</span><span class="ti">New research begins at the desk</span>`;
    const half = one.repeat(Math.max(1, Math.ceil(8 / Math.max(items.length, 2))));
    $("#tape").innerHTML = half + half;
  } catch (_) { /* ignore */ }
}

/* ------------------------------------------------------------------ home: the desk */
async function renderHome() {
  const runs = await api("/api/runs");
  const real = runs.filter((r) => !r.demo);
  const done = real.filter((r) => r.status === "done");
  const count = (x) => done.filter((r) => r.rating === x).length;
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const issued = now.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  const share = (x) => (done.length ? Math.round((count(x) / done.length) * 100) + "% of published" : "No calls yet");
  view.innerHTML = `
  <section class="hero">
    <div class="hero-copy">
      <div class="kicker">Initiate coverage</div>
      <h1>Independent equity research on <span>India's listed companies</span>.</h1>
      <p>Name an NSE or BSE company. The CIO briefs the research desks, sends weak memos back, stages the bull-versus-bear debate, calls in the risk office and signs the report. Every step is visible on the live floor.</p>
      <form id="newform" class="mandate">
        <div class="mfields">
          <div class="field"><label class="f" for="ticker">Company · NSE ticker or BSE code</label><input class="big" id="ticker" placeholder="TCS, RELIANCE, 532540" autocomplete="off" autofocus></div>
          <div class="field"><label class="f" for="asof">As of</label><input id="asof" type="date" value="${today}" max="${today}"></div>
        </div>
        <div class="mactions"><button class="btn primary lg" type="submit">Start research</button><button class="btn lg" type="button" id="demo">Run the demo</button></div>
        <div class="mfoot"><span class="slipno">Mandate № ${String(real.length + 1).padStart(4, "0")} · ${esc(issued)}</span><span>Rating bands: Buy &gt; 15% · Hold 0–15% · Sell &lt; 0%</span></div>
      </form>
    </div>
    <figure class="hero-art"><img src="/static/banner.jpg" alt="AlaDeen Capital Research — the charging bull over a market chart" width="1600" height="905"></figure>
  </section>
  <section class="kpis" aria-label="Coverage summary">
    <div class="kpi all"><span>Published</span><b>${done.length}</b><small>${real.length} on file</small></div>
    <div class="kpi BUY"><span>Buy</span><b>${count("BUY")}</b><small>${share("BUY")}</small></div>
    <div class="kpi HOLD"><span>Hold</span><b>${count("HOLD")}</b><small>${share("HOLD")}</small></div>
    <div class="kpi SELL"><span>Sell</span><b>${count("SELL")}</b><small>${share("SELL")}</small></div>
    <div class="kpi"><span>Stopped</span><b>${real.filter((r) => r.status === "error").length}</b><small>Can be continued</small></div>
  </section>
  <div class="sect-head"><div><div class="kicker">Latest filings</div><h2>Recent research</h2></div><a href="#/history" class="btn ghost sm">Open the archive →</a></div>
  ${runs.length ? `<div class="ledger">${LHEAD}${runs.slice(0, 8).map(lrow).join("")}</div>` :
    `<div class="ledger"><div class="empty"><div class="e">Nothing filed</div>No research yet. Start one above, or run the demo to watch the floor at work.</div></div>`}`;
  $("#newform").onsubmit = (e) => { e.preventDefault(); startResearch($("#ticker").value, $("#asof").value); };
  $("#demo").onclick = () => startResearch("DEMO", null, true);
  bindRows();
}

// One filing in the ledger. A stopped research carries its reason and a Try again button.
const LHEAD = `<div class="lhead" aria-hidden="true"><span>Ticker</span><span>Company</span><span>Rating</span><span class="r">Target</span><span class="r up">Upside</span><span class="go"></span></div>`;
function lrow(r) {
  const ok = r.status === "done";
  return `<div class="lrow" data-id="${esc(r.id)}" tabindex="0" role="link">
    <div class="tk">${esc(r.ticker)}</div>
    <div class="co"><b>${esc(r.company || r.ticker)}</b><span>as of ${esc(r.as_of)}${r.demo ? " · demo" : ""}</span>${r.status === "error" ? `<em class="why">${esc((r.error || "").slice(0, 110))}</em>` : ""}</div>
    <div>${ok ? ratingPill(r.rating, r.qualifier) : statusPill(r.status, r.demo)}</div>
    <div class="nm">${ok ? inr(r.target_price, 0) : "—"}</div>
    <div class="nm up ${r.upside >= 0 ? "pos" : "neg"}">${ok ? pct(r.upside) : ""}</div>
    <div class="go">${r.status === "error" ? `<button class="btn sm" data-retry="${esc(r.id)}" title="Continue this research where it stopped">↻ Try again</button>` : ""}</div>
  </div>`;
}

function bindRows() {
  $$(".lrow").forEach((row) => {
    row.onclick = (ev) => { if (!ev.target.closest("[data-retry]")) location.hash = "#/run/" + row.dataset.id; };
    row.onkeydown = (ev) => { if (ev.key === "Enter" && !ev.target.closest("[data-retry]")) location.hash = "#/run/" + row.dataset.id; };
  });
  $$("[data-retry]").forEach((b) => (b.onclick = (ev) => { ev.stopPropagation(); retryResearch(b.dataset.retry, b); }));
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
  view.innerHTML = `<div class="page-head"><div><div class="kicker">Live floor</div><h1>The floor is quiet.</h1><p>Start a research and the desks light up as the work moves through the firm.</p></div></div>
  ${officeHTML()}<div class="empty"><div class="e">No research running</div><a href="#/">Go to the overview</a> and start one, or run the demo.</div>`;
}

/* ------------------------------------------------------------------ the floor board */
function officeHTML() {
  const rooms = ROSTER.rooms.map((room, i) => {
    const desks = ROSTER.agents.filter((a) => a.room === room.id).map((a) => `
      <div class="desk ${esc(a.tier)}" id="desk-${a.id}" title="${esc(a.role)}">
        <div class="dk-top"><i class="st"></i><span class="cd">${code(a.id)}</span><span class="sw">${STATE_WORD.idle}</span></div>
        <div class="nm">${esc(a.short)}</div>
        <div class="ti">${esc(a.title)}</div>
        <div class="task">Idle</div>
        <div class="screen"><i></i></div>
      </div>`).join("");
    return `<section class="room ${room.id}"><div class="rlabel">${ROOM_NO[room.id] || i + 1} · ${esc(room.title)}</div><div class="desks">${desks}</div></section>`;
  }).join("");
  return `<div class="office" id="office">${rooms}</div>`;
}

function phasesHTML() {
  return `<div class="rail" id="phases">${ROSTER.phases.map((p, i) => `<div class="phase" id="ph-${p.id}"><span class="n">${String(i + 1).padStart(2, "0")}</span>${esc(p.title)}</div>`).join("")}</div>`;
}

function agentMeta(id) { return ROSTER.agents.find((a) => a.id === id) || { title: id, short: id }; }

function setDesk(id, status, task) {
  const d = $("#desk-" + id);
  if (!d) return;
  d.classList.remove("working", "waiting", "done", "error", "idle");
  d.classList.add(status);
  $(".sw", d).textContent = STATE_WORD[status] || status;
  const label = task || { done: "Filed", waiting: "Waiting", working: "Working" }[status] || "";
  $(".task", d).innerHTML = esc(label) + (status === "working" ? '<span class="cursor"></span>' : "");
}

// A memo between desks travels as a capsule in a pneumatic tube.
function flyCapsule(from, to) {
  const office = $("#office");
  const a = $("#desk-" + from), b = $("#desk-" + to);
  if (!office || !a || !b) return;
  const ob = office.getBoundingClientRect(), ab = a.getBoundingClientRect(), bb = b.getBoundingClientRect();
  const cap = document.createElement("div");
  cap.className = "capsule";
  cap.style.left = ab.left - ob.left + ab.width / 2 - 16 + "px";
  cap.style.top = ab.top - ob.top + 20 + "px";
  office.appendChild(cap);
  requestAnimationFrame(() => {
    cap.style.transform = `translate(${bb.left - ab.left}px, ${bb.top - ab.top}px)`;
  });
  setTimeout(() => { cap.style.opacity = "0"; }, 1100);
  setTimeout(() => cap.remove(), 1500);
}

// The wire: a telegraph tape of what the desks are saying.
function feedItem(e) {
  const tm = `<div class="tm">${clock(e.ts)}</div>`;
  if (e.type === "message") {
    return `<li class="msg">${tm}<div><div class="who">${code(e.agent)} <span class="to">→ ${code(e.to)}</span></div><div class="tx">${esc(e.text)}</div></div></li>`;
  }
  if (e.type === "log") {
    return `<li>${tm}<div><div class="who">${code(e.agent)}</div><div class="tx">${esc(e.text)}</div>${e.detail ? `<details><summary>detail</summary><div>${esc(e.detail)}</div></details>` : ""}</div></li>`;
  }
  if (e.type === "error") {
    return `<li class="err">${tm}<div><div class="who">Stopped</div><div class="tx">${esc(e.text)}</div></div></li>`;
  }
  if (e.type === "done") {
    return `<li class="fin">${tm}<div><div class="who">Published</div><div class="tx">${esc(e.rating)}${e.qualifier ? " (" + esc(e.qualifier) + ")" : ""} · target ${inr(e.target_price)} · ${pct(e.upside)} · ${esc(e.seconds)}s · ${esc(e.llm_calls)} AI calls${e.reused_calls ? ` · ${esc(e.reused_calls)} answers reused from the earlier attempt` : ""}</div></div></li>`;
  }
  return "";
}

/* ------------------------------------------------------------------ run page */
async function renderRun(id) {
  const rec = await api("/api/runs/" + id);
  active = { runId: id, stop: false };
  view.innerHTML = `
  <div class="runhead">
    <div class="logo" id="rlogo">₹</div>
    <div><div class="kicker">Research · ${esc(rec.id)}</div><h1 id="rname">${esc(rec.company || rec.ticker)}</h1><div class="meta"><span id="rticker">${esc(rec.ticker)}</span> · as of ${esc(rec.as_of)} · started ${when(rec.created_at)}</div></div>
    <div class="right"><span id="rstatus">${statusPill(rec.status, rec.demo)}</span><span id="elapsed"></span></div>
  </div>
  <div id="banner"></div>
  <div class="tabs" id="tabs">
    <button data-tab="office" class="on">Floor board</button>
    <button data-tab="report">Report</button>
    <button data-tab="file">Working papers</button>
    <button data-tab="downloads">Exhibits</button>
  </div>
  <div id="tab-office">${phasesHTML()}
    <div class="officewrap">${officeHTML()}
      <div class="wire"><h3><span>The wire</span><span id="fcount"></span></h3><ul id="feed"></ul></div>
    </div>
  </div>
  <div id="tab-report" hidden></div>
  <div id="tab-file" hidden></div>
  <div id="tab-downloads" hidden></div>`;
  $$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab, rec)));
  if (rec.status === "done") showBanner(rec);
  if (rec.status === "error") showError(rec.error, id);
  followEvents(id, rec);
}

function showTab(tab, rec) {
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  ["office", "report", "file", "downloads"].forEach((t) => ($("#tab-" + t).hidden = t !== tab));
  const id = encodeURIComponent(rec.id);
  if (tab === "report") {
    $("#tab-report").innerHTML = rec.status === "done" || $("#banner").dataset.done
      ? `<iframe class="reportframe" src="/api/runs/${id}/report"></iframe>`
      : `<div class="empty"><div class="e">Not yet filed</div>The report appears here when the CIO signs off.</div>`;
  }
  if (tab === "file") loadTranscript(id);
  if (tab === "downloads") {
    $("#tab-downloads").innerHTML = `<div class="exhibits">
      ${exhibit("A", "Report (HTML)", "Self-contained page with every chart", `/api/runs/${id}/report?download=1`)}
      ${exhibit("B", "Report (PDF)", "Opens the print dialog; choose “Save as PDF”", `/api/runs/${id}/report?print=1`, true)}
      ${exhibit("C", "Working papers", "CIO mandate, memos, debate, decisions (Markdown)", `/api/runs/${id}/file/transcript.md`)}
      ${exhibit("D", "Research data", "Every agent output and the valuation (JSON)", `/api/runs/${id}/file/research.json`)}
      ${exhibit("E", "Fact pack", "All the data the team worked from (JSON)", `/api/runs/${id}/file/factpack.json`)}
      ${exhibit("F", "Event log", "Timeline of the floor (JSON)", `/api/runs/${id}/file/events.json`)}
    </div>`;
  }
}

function exhibit(letter, title, sub, href, newTab = false) {
  return `<a class="exhibit" href="${href}" ${newTab ? 'target="_blank" rel="noopener"' : ""}><div class="ex">${letter}</div><div><b>${title}</b><span>${sub}</span></div></a>`;
}

async function loadTranscript(id) {
  const box = $("#tab-file");
  try {
    const md = await api(`/api/runs/${id}/transcript`);
    box.innerHTML = `<div class="md">${renderMarkdown(md)}</div>`;
  } catch (_) {
    box.innerHTML = `<div class="empty"><div class="e">Not yet filed</div>The working papers are written when the report is published.</div>`;
  }
}

// The verdict: the rubber stamp and the figures that matter.
function showBanner(rec) {
  const b = $("#banner");
  const id = encodeURIComponent(rec.id);
  b.dataset.done = "1";
  b.innerHTML = `<div class="verdict">
    <div><div class="vk">Rating</div>${ratingPill(rec.rating, rec.qualifier, "lg")}</div>
    <div><div class="vk">Target price</div><div class="vv">${inr(rec.target_price)}</div></div>
    <div><div class="vk">CMP</div><div class="vv">${inr(rec.cmp)}</div></div>
    <div><div class="vk">Upside</div><div class="vv" style="color:${rec.upside >= 0 ? "var(--green)" : "var(--oxblood)"}">${pct(rec.upside)}</div></div>
    <div><div class="vk">Council</div><div class="vv sm">${esc(rec.council_verdict || "—")}</div></div>
    <div class="acts">
      <button class="btn primary" id="viewrep">Read the report</button>
      <a class="btn" href="/api/runs/${id}/report?print=1" target="_blank" rel="noopener">PDF</a>
      <a class="btn" href="/api/runs/${id}/report?download=1">HTML</a>
    </div></div>
    ${rec.headline ? `<p class="headline">${esc(rec.headline)}</p>` : ""}`;
  $("#viewrep").onclick = () => showTab("report", { ...rec, status: "done" });
}

function showError(msg, id = active.runId) {
  $("#banner").innerHTML = `<div class="verdict err">
    <div><div class="vk">Status</div><span class="stamp lg ERR">Stopped</span></div>
    <div><div class="vk">What happened</div><div class="msg">${esc(msg || "Unknown error")}</div>
      <div class="again">Try again continues this same research. Work already finished is kept, so only what is left is run.</div></div>
    <div class="acts"><button class="btn primary" id="retry">↻ Try again</button><a class="btn" href="#/settings">Check settings</a></div></div>`;
  $("#retry").onclick = (ev) => retryResearch(id, ev.currentTarget);
}

// Continue a failed research under the same id, then show it live again.
async function retryResearch(id, btn) {
  if (btn) btn.disabled = true;
  try {
    await api("/api/runs/" + encodeURIComponent(id) + "/retry", { method: "POST" });
    toast("Continuing the research…");
    if (location.hash === "#/run/" + id) await renderRun(id);
    else location.hash = "#/run/" + id;
  } catch (e) {
    if (btn) btn.disabled = false;
    toast(e.message, 4000);
  }
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
        if (f) { f.insertAdjacentHTML("afterbegin", feedItem(e)); count++; $("#fcount").textContent = count + " entries"; }
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
      if (fresh.status === "done" && !$("#banner").dataset.done) { showBanner(fresh); refreshMasthead(); if (live) { toast("Report published"); showTab("report", fresh); } }
      if (fresh.status === "error") showError(fresh.error, id);
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
    if (animate) flyCapsule(e.agent, e.to);
    const t = $("#desk-" + e.to);
    if (t && !t.classList.contains("working")) setDesk(e.to, "waiting", "Memo: " + e.text);
  } else if (e.type === "company") {
    if (e.name) $("#rname").textContent = e.name;
    if (e.logo && /^(data:image\/|https?:\/\/)/.test(e.logo)) {
      const img = document.createElement("img");
      img.src = e.logo; img.alt = "";
      img.onerror = () => { $("#rlogo").textContent = "₹"; };
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
  view.innerHTML = `<div class="page-head"><div><div class="kicker">Research archive</div><h1>Every research on file.</h1><p>Everything your firm has run on this computer. Open one to read the report or replay the floor.</p></div>
    <div class="toolbar"><input id="q" placeholder="Search company or ticker" aria-label="Search company or ticker">
    <select id="rf" aria-label="Filter by rating"><option value="">All ratings</option><option>BUY</option><option>HOLD</option><option>SELL</option></select></div></div>
    <div class="sheet"><table class="t"><thead><tr><th>Company</th><th>As of</th><th>Status</th><th>Rating</th><th class="num">Target</th><th class="num">CMP</th><th class="num">Upside</th><th>Council</th><th>Run on</th><th></th></tr></thead><tbody id="rows"></tbody></table>
    <div id="none" class="empty" hidden><div class="e">Nothing here</div>No research matches.</div></div>`;
  const draw = () => {
    const q = $("#q").value.toLowerCase(), rf = $("#rf").value;
    const list = runs.filter((r) => (!q || ((r.company || "") + r.ticker).toLowerCase().includes(q)) && (!rf || r.rating === rf));
    $("#none").hidden = list.length > 0;
    $("#rows").innerHTML = list.map((r) => `<tr data-id="${esc(r.id)}" style="cursor:pointer">
      <td><b class="cname">${esc(r.company || r.ticker)}</b><span class="ctick">${esc(r.ticker)}</span></td><td class="mono">${esc(r.as_of)}</td>
      <td>${statusPill(r.status, r.demo)}</td><td>${ratingPill(r.rating, r.qualifier)}</td>
      <td class="num">${inr(r.target_price, 0)}</td><td class="num">${inr(r.cmp, 0)}</td><td class="num">${r.status === "done" ? pct(r.upside) : "—"}</td>
      <td>${esc(r.council_verdict || "—")}</td><td class="small muted">${when(r.created_at)}</td>
      <td style="white-space:nowrap">${r.status === "error" ? `<button class="btn sm" data-retry="${esc(r.id)}" title="Continue this research where it stopped">↻ Try again</button> ` : ""}${r.status === "done" ? `<a class="btn sm" href="#/monitor/${esc(r.id)}">Monitor</a>` : ""}<button class="btn ghost danger sm" data-del="${esc(r.id)}" title="Delete this research">Delete</button></td></tr>`).join("");
    $$("#rows tr").forEach((tr) => (tr.onclick = (ev) => { if (!ev.target.closest("[data-del],[data-retry],a")) location.hash = "#/run/" + tr.dataset.id; }));
    $$("[data-retry]").forEach((b) => (b.onclick = (ev) => { ev.stopPropagation(); retryResearch(b.dataset.retry, b); }));
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

/* ------------------------------------------------------------------ call ledger */
async function renderCalls() {
  const data = await api("/api/calls");
  const s = data.summary || {};
  view.innerHTML = `<div class="page-head"><div><div class="kicker">Call ledger</div><h1>Every call, scored.</h1><p>Each published rating is checked against the Nifty 50 once twelve months have passed.</p></div>
    <button class="btn primary" id="score">Score my calls</button></div>
    <div class="strip">
      <div><span class="l">Calls</span><b>${s.calls ?? 0}</b></div>
      <div><span class="l">Matured (12m+)</span><b>${s.matured_12m ?? 0}</b></div>
      <div><span class="l">Hit rate</span><b>${s.hit_rate == null ? "—" : Math.round(s.hit_rate * 100) + "%"}</b></div>
      <div><span class="l">Avg alpha</span><b>${s.avg_alpha_all == null ? "—" : pct(s.avg_alpha_all)}</b></div>
    </div>
    <div class="sheet">${data.rows.length ? `<table class="t"><thead><tr><th>ID</th><th>Date</th><th>Company</th><th>Rating</th><th class="num">Target</th><th class="num">Price then</th><th>Reviewed</th><th class="num">Return</th><th class="num">Alpha</th><th>Verdict</th></tr></thead><tbody>
      ${data.rows.map((r) => `<tr><td class="mono">${esc(r.call_id)}</td><td class="mono">${esc(r.call_date)}</td><td><b class="cname">${esc(r.company)}</b><span class="ctick">${esc(r.ticker)}</span></td>
      <td>${ratingPill((r.rating || "").split(" ")[0])}</td><td class="num">${esc(r.target_price)}</td><td class="num">${esc(r.close_on_call_date)}</td>
      <td class="mono">${esc(r.review_date || "—")}</td><td class="num">${r.stock_return ? pct(+r.stock_return) : "—"}</td><td class="num">${r.alpha ? pct(+r.alpha) : "—"}</td><td>${esc(r.verdict || "Not scored")}</td></tr>`).join("")}
    </tbody></table>` : `<div class="empty"><div class="e">No calls yet</div>Each published research adds one line to the ledger.</div>`}</div>`;
  if (data.rows.length) {
    view.insertAdjacentHTML("beforeend", '<section class="panel"><h2>Dividend-adjusted comparison</h2><label>Call <select id="returnCall">'+data.rows.map(r=>'<option value="'+esc(r.call_id)+'">'+esc(r.company)+' · '+esc(r.call_date)+'</option>').join("")+'</select></label> <label>Sector benchmark symbol <input id="sectorIndex" placeholder="e.g. ^NSEBANK"></label> <button class="btn" id="returnCompare">Compare returns</button><div id="adjusted"></div></section>');
    wbAction("#returnCompare",async()=>{
      const r=await api("/api/workbench/call-returns?"+new URLSearchParams({call_id:$("#returnCall").value,sector_benchmark:$("#sectorIndex").value}));
      $("#adjusted").innerHTML="<p>"+esc(r.start)+" – "+esc(r.end)+" · Returns use provider-adjusted closes. Index series follow the selected index methodology.</p>"+wbTable(["Symbol","Return"],Object.entries(r.returns).map(([symbol,v])=>[symbol,pct(v)]));
    });
  }
  $("#score").onclick = async () => {
    const b = $("#score"); b.disabled = true; b.textContent = "Scoring…";
    try { await api("/api/calls/score", { method: "POST" }); toast("Calls scored"); renderCalls(); }
    catch (e) { toast(e.message, 4000); b.disabled = false; b.textContent = "Score my calls"; }
  };
}

/* ------------------------------------------------------------------ settings */
async function renderSettings() {
  const s = await api("/api/settings");
  const v = s.values;
  const P = (x) => (x == null ? "" : +(x * 100).toFixed(3));
  const provOpts = s.providers.map((p) => `<option value="${p.id}" ${p.id === v.llm_provider ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  const tierOpts = (cur) => `<option value="">Same as main provider</option>` + s.providers.map((p) => `<option value="${p.id}" ${p.id === cur ? "selected" : ""}>${esc(p.label)}</option>`).join("");
  const keyRow = (p) => {
    const k = s.keys[p.id] || {};
    return `<div class="keyrow"><b>${esc(p.label)}${p.use ? `<div class="hint" style="font-weight:400">${esc(p.use)}</div>` : ""}</b><input type="password" data-key="${p.id}" placeholder="${k.set ? "Saved — leave blank to keep" : "Paste API key"}" autocomplete="off">
      <span class="state">${k.set ? `<span class="pill done">${esc(k.masked)}</span> <span class="muted tiny">${esc(k.source)}</span> ${k.source === "dashboard" ? `<button class="btn ghost danger sm" data-clear="${p.id}" type="button">Remove</button>` : ""}` : '<span class="pill">Not set</span>'}</span></div>`;
  };
  const keyRows = s.providers.filter((p) => p.key).map(keyRow).join("");
  const dataKeyRows = (s.data_sources || []).map(keyRow).join("");
  const desks = s.desks.map((d) => { const a = agentMeta(d); return `<label><input type="checkbox" data-desk="${d}" ${v.desks.includes(d) ? "checked" : ""}> <i>${code(d)}</i> ${esc(a.title)}</label>`; }).join("");
  const sec = (n, title) => `<h3><span class="sn">Section ${String(n).padStart(2, "0")}</span>${title}</h3>`;
  view.innerHTML = `<div class="page-head"><div><div class="kicker">Settings</div><h1>How the firm is run.</h1><p>Saved on this computer in <code>${esc(s.paths.settings)}</code>. API keys never leave your machine except to call the provider you choose.</p></div></div>
  <div class="settings"><div class="toc"><a href="#s-models" data-jump><em>1</em>AI models</a><a href="#s-keys" data-jump><em>2</em>API keys</a><a href="#s-brief" data-jump><em>3</em>Research brief</a><a href="#s-team" data-jump><em>4</em>Research team</a><a href="#s-data" data-jump><em>5</em>Data</a><a href="#s-val" data-jump><em>6</em>Valuation</a><a href="#s-brand" data-jump><em>7</em>Report &amp; dashboard</a><a href="#s-store" data-jump><em>8</em>Storage</a></div>
  <form id="sform">
  <section class="card" id="s-models">${sec(1, "AI models")}
    <div class="row2"><div class="field"><label class="f">Provider</label><select id="llm_provider">${provOpts}</select><div class="hint">Direct: Claude, OpenAI, Gemini, Grok, DeepSeek, Kimi, Qwen, Mistral, GLM, Llama, MiMo. Or OpenRouter, a local Ollama model, or any OpenAI-compatible server.</div></div>
    <div class="field" id="burl"><label class="f">Server URL</label><input id="backend_url" value="${esc(v.backend_url || "")}" placeholder="http://localhost:11434/v1"><div class="hint" id="burlhint"></div></div></div>
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
  <section class="card" id="s-keys">${sec(2, "API keys")}${keyRows}
    <h3 style="margin-top:22px;font-size:20px">Backup data sources <span class="muted small" style="font:400 12px var(--sans)">optional</span></h3>${dataKeyRows}<div class="hint">Keys entered here are stored in your settings file (readable only by you). Keys in your environment or <code>.env</code> also work.</div></section>
  <section class="card" id="s-brief">${sec(3, "Research brief")}
    <label class="f">Your standing instructions — the CIO and every desk follow them on every research</label>
    <textarea id="research_brief" rows="9" style="width:100%;line-height:1.5">${esc(v.research_brief || "")}</textarea>
    <div class="hint">Write it once, the way you would brief a research team. Leave it empty to use the firm's standard process only.</div>
  </section>
  <section class="card" id="s-team">${sec(4, "Research team")}
    <label class="f">Research desks the CIO can brief</label><div class="desk-check" style="margin-bottom:16px">${desks}</div>
    <div class="row3"><div class="field"><label class="f">CIO revision rounds</label><input id="cio_revision_rounds" type="number" min="0" max="3" value="${v.cio_revision_rounds}"><div class="hint">How many times the CIO may send memos back.</div></div>
    <div class="field"><label class="f">Debate rebuttal rounds</label><input id="max_debate_rounds" type="number" min="0" max="4" value="${v.max_debate_rounds}"></div>
    <div class="field"><label class="f">&nbsp;</label><label class="switch"><input type="checkbox" id="run_council" ${v.run_council ? "checked" : ""}> Independent council review</label><label class="switch" style="margin-top:8px"><input type="checkbox" id="council_followup" ${v.council_followup ? "checked" : ""}> Fix the council's gaps before publishing</label><label class="switch" style="margin-top:8px"><input type="checkbox" id="log_calls" ${v.log_calls ? "checked" : ""}> Add calls to the call log</label></div></div>
  </section>
  <section class="card" id="s-data">${sec(5, "Data")}
    <div class="row3"><div class="field"><label class="switch"><input type="checkbox" id="fetch_documents" ${v.fetch_documents ? "checked" : ""}> Read annual reports &amp; concall transcripts</label></div>
    <div class="field"><label class="f">Reading depth</label><select id="document_mode"><option value="focused" ${v.document_mode === "focused" ? "selected" : ""}>Focused (key sections)</option><option value="full" ${v.document_mode === "full" ? "selected" : ""}>Every page (slow, costly)</option></select></div>
    <div class="field"><label class="f">News look-back (days)</label><input id="news_lookback_days" type="number" min="7" max="365" value="${v.news_lookback_days}"></div></div>
    <div class="row3"><div class="field"><label class="f">Annual reports to read</label><input id="max_annual_reports" type="number" min="0" max="10" value="${v.max_annual_reports}"></div>
    <div class="field"><label class="f">Concall transcripts to read</label><input id="max_concall_transcripts" type="number" min="0" max="8" value="${v.max_concall_transcripts}"></div></div>
  </section>
  <section class="card" id="s-val">${sec(6, "Valuation")}
    <div class="row3"><div class="field"><label class="f">Risk-free rate (10Y G-Sec, %)</label><input data-pct id="risk_free_rate" type="number" step="0.01" value="${P(v.risk_free_rate)}"></div>
    <div class="field"><label class="f">India equity risk premium (%)</label><input data-pct id="equity_risk_premium" type="number" step="0.01" value="${P(v.equity_risk_premium)}"></div>
    <div class="field"><label class="f">Tax rate (%)</label><input data-pct id="tax_rate" type="number" step="0.01" value="${P(v.tax_rate)}"></div></div>
    <div class="row3"><div class="field"><label class="f">Terminal growth cap (%)</label><input data-pct id="terminal_growth_cap" type="number" step="0.1" value="${P(v.terminal_growth_cap)}"></div>
    <div class="field"><label class="f">Weight of intrinsic value (%)</label><input data-pct id="dcf_weight" type="number" step="5" value="${P(v.dcf_weight)}"><div class="hint">The rest is the peer-multiple value.</div></div>
    <div class="field"><label class="f">Margin of safety (%)</label><input data-pct id="margin_of_safety" type="number" step="1" value="${P(v.margin_of_safety)}"></div></div>
    <label class="f">Scenario probabilities (%) — bear / base / bull</label>
    <div class="row3"><input data-prob="bear" type="number" value="${P(v.scenario_probabilities.bear)}"><input data-prob="base" type="number" value="${P(v.scenario_probabilities.base)}"><input data-prob="bull" type="number" value="${P(v.scenario_probabilities.bull)}"></div>
    <div class="row2" style="margin-top:16px"><div class="field"><label class="f">BUY if expected 12-month return is above (%)</label><input data-band="buy" type="number" value="${P(v.rating_bands.buy)}"></div>
    <div class="field"><label class="f">SELL if expected 12-month return is below (%)</label><input data-band="sell" type="number" value="${P(v.rating_bands.sell)}"></div></div>
  </section>
  <section class="card" id="s-brand">${sec(7, "Report &amp; dashboard")}
    <div class="row2"><div class="field"><label class="f">Firm name on reports</label><input id="firm_name" value="${esc(v.firm_name)}"></div>
    <div class="field"><label class="f">Analyst credit on reports</label><input id="analyst_name" value="${esc(v.analyst_name)}"></div></div>
    <div class="row2"><div class="field"><label class="f">Dashboard port</label><input id="port" type="number" value="${v.port}"><div class="hint">Takes effect next time you start the app.</div></div>
    <div class="field"><label class="f">&nbsp;</label><label class="switch"><input type="checkbox" id="open_browser" ${v.open_browser ? "checked" : ""}> Open the browser automatically</label></div></div>
  </section>
  <section class="card" id="s-store">${sec(8, "Storage")}<div class="small">Research archive: <code>${esc(s.paths.research)}</code><br>Call log: <code>${esc(s.paths.call_log)}</code><br>App folder: <code>${esc(s.paths.home)}</code></div></section>
  <div class="savebar"><button class="btn" type="button" id="reset">Discard changes</button><button class="btn primary" type="submit">Save settings</button></div>
  </form></div>`;
  const REGIONAL = ["deepseek", "moonshot", "qwen", "mistral", "zai", "meta", "xiaomi"];
  const syncUrl = () => {
    const p = $("#llm_provider").value;
    const needed = ["ollama", "openai_compatible"].includes(p), optional = REGIONAL.includes(p);
    $("#burl").style.opacity = needed || optional ? "1" : ".45";
    $("#burlhint").textContent = needed ? "Required: your server's address."
      : optional ? "Optional. Leave empty for the official global endpoint; set it only for another region (e.g. China)."
      : "Not used for this provider.";
  };
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
      $("#testout").innerHTML = r.ok ? `<span style="color:var(--green)">✓ Connected — model replied “${esc((r.reply || "").slice(0, 40))}”</span>` : `<span style="color:var(--oxblood)">✗ ${esc(r.error)}</span>`;
    } catch (e) { $("#testout").innerHTML = `<span style="color:var(--oxblood)">✗ ${esc(e.message)}</span>`; }
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
      council_followup: $("#council_followup").checked, research_brief: $("#research_brief").value,
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
      toast("Settings saved"); refreshMasthead(); renderSettings();
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
