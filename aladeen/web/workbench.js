"use strict";

function wbTable(headers, rows) {
  if (!rows.length) return "<p>No observations for this selection.</p>";
  return (
    '<div class="sheet" style="overflow-x:auto"><table class="t"><thead><tr>' +
    headers.map((h) => "<th>" + esc(h) + "</th>").join("") +
    "</tr></thead><tbody>" +
    rows.map((row) => "<tr>" + row.map((v) => "<td>" + esc(v ?? "—") + "</td>").join("") + "</tr>").join("") +
    "</tbody></table></div>"
  );
}
function wbLink(url, label) {
  return /^https?:\/\//i.test(url || "")
    ? '<a rel="noreferrer" target="_blank" href="' + esc(url) + '">' + esc(label) + "</a>"
    : esc(label);
}
function wbAction(selector, action) {
  const el = $(selector);
  if (!el) return;
  el.onclick = async () => {
    el.disabled = true;
    try {
      await action();
    } catch (err) {
      toast(err.message, 6000);
    } finally {
      el.disabled = false;
    }
  };
}
async function renderWorkbench(id, snapshot = "", compare = "") {
  const routeHash = location.hash;
  const root = "/api/workbench";
  const [all, holdings, watch] = await Promise.all([
    api("/api/runs"),
    api(root + "/positions"),
    api(root + "/watchlist"),
  ]);
  const pins = watch.map(row => row.run);
  if (location.hash !== routeHash) return;
  const runs = all.filter((r) => r.status === "done");
  const selected = runs.find((r) => r.id === id) || runs.find((r) => pins.includes(r.id)) || runs[0];
  if (!selected) {
    view.innerHTML = "<h1>Research monitor</h1><p>Publish a research run or run the demo to open its evidence.</p>";
    return;
  }
  const path = root + "/" + encodeURIComponent(selected.id);
  const query = new URLSearchParams({ snapshot, compare });
  const d = await api(path + "/evidence?" + query);
  if (location.hash !== routeHash) return;
  const option = (v, title, chosen) =>
    '<option value="' + esc(v) + '"' + (v === chosen ? " selected" : "") + ">" + esc(title) + "</option>";
  const runTitle = (r) => (pins.includes(r.id) ? "★ " : "") + r.company + " · " + r.as_of + (r.demo ? " · demo" : "");
  const opts = runs.map((r) => option(r.id, runTitle(r), selected.id)).join("");
  const events = (list) =>
    list.length
      ? "<ul>" +
        list
          .map(
            (e) =>
              "<li>" +
              wbLink(e.url, e.title) +
              " · " +
              esc(e.date || "Undated") +
              (e.new ? " · New" : "") +
              "<br>" +
              esc(e.signals.join(" · ")) +
              "</li>",
          )
          .join("") +
        "</ul>"
      : "<p>No matching filings in this snapshot.</p>";
  const tabs = ["Monitor", "Earnings", "Evidence", "Valuation", "Governance", "Portfolio"];
  const sections = [];
  sections.push(
    "<h2>Watchlist</h2>" +
      wbTable(
        ["Company", "Call", "Kill fact", "Latest filing", "Governance signals", "Status"],
        watch.map((w) => [w.company, w.rating, w.kill_fact, w.latest, w.governance, w.status]),
      ) +
      "<h2>" +
      esc(d.assessment?.reason || (d.review ? "Review needed" : d.selected === "archive" ? "Original report" : "No changes detected")) +
      "</h2><p><b>Thesis invalidation condition</b> · " +
      esc(d.kill_fact || "Unavailable") +
      "</p><p>Published call · " +
      esc(selected.rating) +
      " · " +
      inr(selected.target_price) +
      "</p>" +
      events(d.events.filter((e) => e.new)) +
      '<button class="btn" id="refresh">Refresh filings and results</button> <button class="btn" id="review">Start targeted research review</button>',
  );
  sections.push(
    '<h2>Earnings and report changes</h2><label>Compare with <select id="compare"><option value="">Signed baseline</option>' +
      runs
        .filter((r) => r.id !== selected.id && r.ticker === selected.ticker && r.as_of <= selected.as_of)
        .map((r) => option(r.id, runTitle(r), compare))
        .join("") +
      "</select></label><p>Prior target " +
      inr(d.previous_target) +
      " · Published target " +
      inr(d.target) +
      "</p>" +
      wbTable(
        ["Statement", "Metric", "Period", "Previously reported", "Latest actual"],
        d.changes.map((r) => [r.statement, r.metric, r.period, r.previous, r.actual]),
      ) +
      "<h3>Quarterly expectations</h3>" +
      wbTable(
        ["Period", "Metric", "Forecast", "Actual", "Variance"],
        d.quarter_review.map((r) => [r.period, r.metric, r.forecast, r.actual, r.variance]),
      ) +
      '<label>Quarter end <input id="forecastPeriod" placeholder="Mar 2027"></label> <label>Metric <select id="forecastMetric">' +
      Object.keys(d.tables.quarters?.rows || {})
        .map((k) => option(k, k, ""))
        .join("") +
      '</select></label> <label>Expected value (statement units) <input type="number" id="forecastValue"></label> <button class="btn" id="saveForecast">Record forecast</button>' +
      "<h3>Prior forecast versus reported revenue (₹ crore)</h3>" +
      wbTable(
        ["Fiscal period", "Forecast", "Actual", "Variance"],
        d.forecast_review.map((r) => [r.period, r.forecast, r.actual, r.variance]),
      ) +
      "<h3>Changed valuation assumptions</h3>" +
      wbTable(
        ["Assumption", "Prior", "Published"],
        Object.keys(d.assumptions || {})
          .filter((k) => JSON.stringify(d.assumptions[k]) !== JSON.stringify((d.previous_assumptions || {})[k]))
          .map((k) => [k, JSON.stringify(d.previous_assumptions?.[k]), JSON.stringify(d.assumptions[k])]),
      ),
  );
  sections.push(
    '<h2>Evidence explorer</h2><label>Snapshot <select id="snapshot">' +
      option("archive", "Original FactPack", d.selected) +
      d.dates.map((s) => option(s, s, d.selected)).join("") +
      "</select></label> " +
      wbLink(d.source, "Open statement source") +
      Object.entries(d.tables)
        .filter(([, t]) => t.rows)
        .map(
          ([key, t]) =>
            "<details><summary>" +
            esc(key.replaceAll("_", " ")) +
            "</summary>" +
            wbTable(
              ["Metric", ...t.columns],
              Object.entries(t.rows).map(([metric, values]) => [metric, ...values]),
            ) +
            "</details>",
        )
        .join(""),
  );
  const peerHeaders = [...new Set(d.peers.flatMap(Object.keys))].filter((k) => k !== "url");
  sections.push(
    '<h2>Sector peers and valuation</h2><label>Filter peers <input id="peerFilter" placeholder="Company name"></label><div id="peers"></div>' +
      '<h3>Screen archived companies</h3><button class="btn" id="loadSectors">Load sector metrics</button><div id="sectorScreen"></div><h3>Valuation scenario</h3><label>Company-specific cost of equity premium (%) <input type="number" min="0" max="20" step=".1" id="premium" value="' +
      esc((d.assumptions?.cost_of_equity_premium || 0) * 100) +
      '"></label> <button class="btn" id="value">Recalculate</button><p id="scenario"></p>',
  );
  sections.push(
    "<h2>Governance radar</h2><p>Filing titles and summaries matching governance terms. Open the disclosure to verify each signal.</p>" +
      events(d.events.filter((e) => e.signals.some((s) => s !== "Results"))) +
      "<h3>Cash conversion</h3>" +
      wbTable(
        ["Year", "Operating cash flow (₹ crore)", "Profit (₹ crore)", "CFO below profit"],
        d.cash_conversion.map((r) => [r.period, r.cash, r.profit, r.cash < r.profit ? "Yes" : "No"]),
      ),
  );
  const holding = holdings.find((p) => p.run === selected.id);
  sections.push(
    "<h2>Paper portfolio</h2>" +
      (selected.call_id
        ? '<label>Allocation (₹) <input id="amount" type="number" min="0" value="' +
          esc(holding?.amount ?? 100000) +
          '"></label> <label>Benchmark symbol <input id="benchmark" value="' +
          esc(holding?.benchmark ?? "^NSEI") +
          '"></label> <button id="allocate" class="btn">Save allocation</button> <small>Set zero to remove.</small>'
        : "<p>Select a filed call to allocate paper capital.</p>") +
      wbTable(
        ["Holding", "Sector", "Allocation (₹)", "Benchmark", "Call published"],
        holdings.map((p) => [p.ticker, p.sector, p.amount, p.benchmark, p.available]),
      ) +
      '<p><label>From <input type="date" id="start"></label> <label>Through <input type="date" id="end"></label> <button id="performance" class="btn">Measure performance</button></p><div id="attribution"></div>',
  );
  view.innerHTML =
    '<h1>Research monitor</h1><label>Research <select id="wbRun">' +
    opts +
    '</select></label> <button class="btn" id="pin">' +
    (pins.includes(selected.id) ? "Unpin" : "Pin to watchlist") +
    "</button><p>" +
    pins
      .map((i) => runs.find((r) => r.id === i))
      .filter(Boolean)
      .map((r) => '<a href="#/monitor/' + encodeURIComponent(r.id) + '">' + esc(r.company) + "</a>")
      .join(" · ") +
    '</p><div class="actions">' +
    tabs.map((t, i) => '<button class="btn" data-wtab="' + i + '">' + t + "</button>").join(" ") +
    "</div>" +
    sections.map((s, i) => '<section class="panel" data-wpanel="' + i + '">' + s + "</section>").join("");
  const show = (idx) => {
    $$("[data-wpanel]").forEach((p, i) => (p.hidden = i !== idx));
    $$("[data-wtab]").forEach((b, i) => (b.disabled = i === idx));
  };
  $$("[data-wtab]").forEach((b, i) => (b.onclick = () => show(i)));
  show(compare ? 1 : snapshot ? 2 : 0);
  $("#wbRun").onchange = (e) => (location.hash = "#/monitor/" + encodeURIComponent(e.target.value));
  $("#compare").onchange = (e) =>
    renderWorkbench(selected.id, snapshot, e.target.value).catch((err) => toast(err.message));
  $("#snapshot").onchange = (e) =>
    renderWorkbench(selected.id, e.target.value, compare).catch((err) => toast(err.message));
  wbAction("#saveForecast", async () => {
    await api(
      path +
        "/forecast?" +
        new URLSearchParams({
          period: $("#forecastPeriod").value,
          metric: $("#forecastMetric").value,
          value: $("#forecastValue").value,
        }),
      { method: "PUT" },
    );
    await renderWorkbench(selected.id);
    $('[data-wtab="1"]').click();
  });
  wbAction("#pin", async () => {
    await api(path + "/pin?enabled=" + !pins.includes(selected.id), { method: "PUT" });
    await renderWorkbench(selected.id);
  });
  wbAction("#refresh", async () => {
    await api(path + "/refresh", { method: "POST" });
    await renderWorkbench(selected.id);
  });
  $("#review").disabled = !d.dates.length || d.selected !== d.dates[0] || !!compare;
  wbAction("#review", async () => {
    const r = await api(path + "/review", { method: "POST" });
    if (r.id) location.hash = "#/run/" + r.id;
    else {
      await renderWorkbench(selected.id);
      toast(r.reason, 6000);
    }
  });
  const showPeers = () => {
    const term = $("#peerFilter").value.toLowerCase();
    $("#peers").innerHTML = wbTable(
      peerHeaders,
      d.peers.filter((p) => String(p.Company).toLowerCase().includes(term)).map((p) => peerHeaders.map((k) => p[k])),
    );
  };
  $("#peerFilter").oninput = showPeers;
  showPeers();
  wbAction("#loadSectors", async () => {
    const companies = await api(root + "/sectors");
    const sectors = [...new Set(companies.map((c) => c.sector))];
    $("#sectorScreen").innerHTML =
      '<label>Sector <select id="sector">' +
      sectors.map((s) => option(s, s, "")).join("") +
      '</select></label> <label>Metric <select id="metric"></select></label><div id="ranked"></div>';
    const rank = () => {
      const metric = $("#metric").value;
      const rows = companies
        .filter((c) => c.sector === $("#sector").value && typeof c.metrics[metric] === "number")
        .sort((a, b) => b.metrics[metric] - a.metrics[metric]);
      $("#ranked").innerHTML = wbTable(
        ["Company", "Analysis date", metric],
        rows.map((c) => [c.company, c.date, c.metrics[metric]]),
      );
    };
    const metrics = () => {
      const keys = new Set(
        companies.filter((c) => c.sector === $("#sector").value).flatMap((c) => Object.keys(c.metrics)),
      );
      $("#metric").innerHTML = [...keys]
        .sort()
        .map((k) => option(k, k, ""))
        .join("");
      rank();
    };
    $("#sector").onchange = metrics;
    $("#metric").onchange = rank;
    metrics();
  });
  wbAction("#value", async () => {
    const r = await api(path + "/value?premium=" + encodeURIComponent($("#premium").value), { method: "POST" });
    $("#scenario").textContent = r.method + " · Intrinsic " + inr(r.intrinsic) + " · 12-month target " + inr(r.target);
  });
  wbAction("#allocate", async () => {
    await api(
      path + "/position?" + new URLSearchParams({ amount: $("#amount").value, benchmark: $("#benchmark").value }),
      { method: "PUT" },
    );
    await renderWorkbench(selected.id);
    $('[data-wtab="5"]').click();
  });
  wbAction("#performance", async () => {
    const r = await api(
      root + "/performance?" + new URLSearchParams({ start: $("#start").value, end: $("#end").value }),
    );
    $("#attribution").innerHTML =
      "<p>" +
      esc(r.start) +
      " – " +
      esc(r.end) +
      " · Total return " +
      pct(r.total_return) +
      " · Maximum drawdown " +
      pct(r.drawdown) +
      "</p>" +
      wbTable(
        ["Sector", "Portfolio weight"],
        Object.entries(r.sectors).map(([s, w]) => [s, pct(w)]),
      ) +
      wbTable(
        ["Holding", "Sector", "Weight", "Market value", "Gain", "Return contribution", "Benchmark return"],
        r.rows.map((p) => [
          p.ticker,
          p.sector,
          pct(p.weight),
          inr(p.value),
          inr(p.gain),
          pct(p.contribution),
          pct(p.benchmark_return),
        ]),
      );
  });
}
