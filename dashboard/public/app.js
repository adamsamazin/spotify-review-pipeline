// Dashboard front end: everything comes from the backend API, which reads the Postgres database.
const fmt = (n, d = 0) => (n === null || n === undefined) ? "–" : Number(n).toLocaleString(undefined,
  { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
let claims = {};

function openDrawer(html) { document.getElementById("drawer-body").innerHTML = html; document.getElementById("drawer").classList.add("open"); }
function closeDrawer() { document.getElementById("drawer").classList.remove("open"); }
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

async function showIssue(id) {
  openDrawer("<p class='muted'>Loading…</p>");
  const i = await api(`/api/issues/${encodeURIComponent(id)}`);
  const sev = i.severity_breakdown.map(s => `sev ${s.severity}: ${fmt(s.n)}`).join(" · ");
  openDrawer(`<h3>${esc(i.name)}</h3><p><code>${esc(i.issue_id)}</code> · topic <b>${esc(i.topic)}</b>
    ${i.rank ? `· rank <b>${i.rank}</b>` : ""}</p><p>${esc(i.definition)}</p>
    <table><tr><th>Complaints</th><th>Severity sum</th><th>Mean severity</th><th>Priority</th></tr>
    <tr><td class="num">${fmt(i.complaint_count)}</td><td class="num">${fmt(i.severity_sum)}</td>
    <td class="num">${fmt(i.mean_severity, 6)}</td><td class="num">${fmt(i.priority_score)}</td></tr></table>
    <p class="muted">${sev}</p><h4>Highest-severity member reviews (directly labelled)</h4>
    ${i.reviews.map(r => `<div class="quote">${esc(r.evidence_quote)}<br><span class="muted">
      <code class="rid" onclick="showReview('${esc(r.review_id)}')">${esc(r.review_id)}</code> · severity ${r.severity}
      · ${esc(r.intent)} · ${esc((r.review_timestamp || "").slice(0, 10))}</span></div>`).join("")}`);
}

async function showReview(id) {
  openDrawer("<p class='muted'>Loading…</p>");
  const r = await api(`/api/reviews/${encodeURIComponent(id)}`);
  openDrawer(`<h3>Review <code>${esc(r.review_id)}</code></h3><div class="quote">${esc(r.evidence_quote || "(no text)")}</div>
    <table>${[["status", r.status + (r.reason ? ` (${r.reason})` : "")], ["topic", r.topic], ["intent", r.intent],
      ["severity", r.severity], ["sentiment", r.sentiment], ["needs review", r.needs_review],
      ["entities", (r.entities || []).join(", ")], ["stars (metadata only)", r.review_rating],
      ["date", r.review_timestamp], ["label config", r.label_config],
      ["reused result from", r.cache_source_id || "—"]].map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`).join("")}</table>
    <h4>Issue membership</h4>${r.issues.length ? r.issues.map(i => `<button class="chip" onclick="showIssue('${esc(i.issue_id)}')">${esc(i.issue_id)}</button>`).join(" ")
      : "<p class='muted'>Not a complaint/cancellation, so not in any issue.</p>"}`);
}

function showClaim(cid) {
  const c = claims[cid];
  if (c) showIssue(c.issue_id);
}

async function load() {
  const [s, rank, topics, trend, memo, ev] = await Promise.all([
    api("/api/summary"), api("/api/ranking?limit=30"), api("/api/topics"), api("/api/trend"), api("/api/memo"), api("/api/evals")]);

  const st = s.statuses || {};
  document.getElementById("subtitle").textContent =
    `${fmt(s.total_records)} Google Play reviews (May 2022 – Nov 2023), run "${s.run}". All numbers below are read from the database the pipeline loaded.`;
  const cost = (s.calls_by_role || []).reduce((a, r) => a + (r.cost_usd || 0), 0);
  const kpi = [
    [fmt(s.total_records), "source reviews accounted for"],
    [fmt(st.completed), "classified (completed)"],
    [fmt(st.quarantined || 0), "quarantined (with reason)"],
    [fmt(s.distinct_texts), "distinct texts sent to the model"],
    [fmt(s.cache_reuse), "duplicates reused from cache"],
    [fmt((s.intents.complaint || 0) + (s.intents.cancellation || 0)), "complaints + cancellations"],
    [fmt(s.needs_review), "flagged needs_review"],
    ["$" + fmt(cost, 2), "API spend for this run"]];
  document.getElementById("kpis").innerHTML = kpi.map(([b, t]) => `<div class="kpi"><b>${b}</b><span>${t}</span></div>`).join("");

  // memo with clickable claim tags and review IDs
  claims = Object.fromEntries((memo.claims || []).map(c => [c.claim_id, c]));
  let html = marked.parse(memo.markdown || "_No memo saved._");
  html = html.replace(/\[(C\d+)\]/g, (m, c) => `<button class="chip" title="${esc(claims[c] ? claims[c].issue_id + " " + claims[c].metric + " = " + claims[c].value : "")}" onclick="showClaim('${c}')">${c}</button>`);
  html = html.replace(/<code>([0-9a-f]{8}-[0-9a-f-]{27})<\/code>/g, (m, id) => `<code class="rid" onclick="showReview('${id}')">${id}</code>`);
  html = html.replace(/<code>([a-z]+\.[a-z0-9_]+)<\/code>/g, (m, id) => `<code class="rid" onclick="showIssue('${id}')">${id}</code>`);
  document.getElementById("memo").innerHTML = html;
  document.getElementById("memo-meta").innerHTML = `Written by <code>${esc(memo.label_config)}</code> from saved aggregates only;
    validation: <b class="${memo.status === "valid" ? "" : "warn"}">${esc(memo.status)}</b>; ${(memo.claims || []).length} claims checked against the ranking.`;

  // ranking table
  document.getElementById("ranking").innerHTML = `<tr><th class="num">#</th><th>Issue</th><th>Topic</th>
    <th class="num">Complaints</th><th class="num">Severity sum</th><th class="num">Mean severity</th><th class="num">Priority</th></tr>` +
    rank.map(r => `<tr class="clickable" onclick="showIssue('${esc(r.issue_id)}')"><td class="num">${r.rank}</td>
      <td><b>${esc(r.name)}</b><br><code class="muted">${esc(r.issue_id)}</code></td><td>${esc(r.topic)}</td>
      <td class="num">${fmt(r.complaint_count)}</td><td class="num">${fmt(r.severity_sum)}</td>
      <td class="num">${fmt(r.mean_severity, 6)}</td><td class="num"><b>${fmt(r.priority_score)}</b></td></tr>`).join("");

  // charts
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--line");
  new Chart(document.getElementById("topicChart"), {
    type: "bar",
    data: { labels: topics.map(t => t.topic), datasets: [
      { label: "Severity sum (priority)", data: topics.map(t => t.severity_sum), backgroundColor: css("--accent") },
      { label: "Complaints", data: topics.map(t => t.complaint_count), backgroundColor: css("--muted") }] },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } } });
  const months = [...new Set(trend.map(r => r.month))].sort();
  const tnames = [...new Set(trend.map(r => r.topic))];
  const palette = ["#1db954", "#4c78a8", "#f58518", "#e45756", "#72b7b2", "#b279a2", "#9d755d", "#bab0ac"];
  new Chart(document.getElementById("trendChart"), {
    type: "line",
    data: { labels: months, datasets: tnames.map((t, k) => ({ label: t, borderColor: palette[k % 8], backgroundColor: palette[k % 8],
      data: months.map(m => { const r = trend.find(x => x.month === m && x.topic === t); return r ? +(100 * r.negative / r.completed).toFixed(2) : 0; }) })) },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" } },
      scales: { y: { ticks: { callback: v => v + "%" } } } } });

  // quality checks
  const g = ev.golden || {}, v = ev.verify || {}, inj = ev.injection || {}, ctl = ev.controls || {};
  const ga = g.agreement || {};
  const passed = Object.values(ctl).filter(x => x.pass).length;
  document.getElementById("evals").innerHTML = `<table>
    <tr><th>Golden 50 (human labels)</th><td>topic ${fmt(100 * (ga.topic || 0))}% · intent ${fmt(100 * (ga.intent || 0))}% ·
      severity exact ${fmt(100 * (ga.severity_exact || 0))}% (MAE ${g.severity_mae ?? "–"}) · sentiment ±0.5 ${fmt(100 * (ga.sentiment_within_tol || 0))}%
      · ${g.ambiguous_cases ?? "–"} ambiguous</td></tr>
    <tr><th>Independent verifier</th><td>${fmt(v.verified)} sampled reviews re-labelled by a separate prompt;
      ${fmt(100 * (v.any_field_disagreement_rate || 0), 1)}% disagree on some field; planted wrong labels caught:
      ${v.planted_test ? v.planted_test.summary : "–"}</td></tr>
    <tr><th>Prompt-injection test</th><td>${inj.injection_resisted ? "Resisted" : "Not resisted"}: ${esc(inj.injection_note || "")}</td></tr>
    <tr><th>Control tests (offline)</th><td>${passed}/${Object.keys(ctl).length} pass: retry, quarantine, missing IDs,
      interrupt/resume, budget stop, parallel workers, memo number check</td></tr></table>`;

  // pipeline + calls
  document.getElementById("pipeline").innerHTML = [
    ["1 Ingest", "code: read all rows, hash every source row, find exact duplicate texts, queue pending work"],
    ["2 Enrich", "Jev: topic, intent, severity, sentiment; ≤50 reviews per request; parallel workers; cache reuse"],
    ["3 Verify", "Jev with separate wording re-labels a seeded sample without seeing the first answer"],
    ["4 Group", "Claude Haiku names issues once from bounded examples; Jev assigns each complaint"],
    ["5 Rank", "code: severity sum per issue, ties by issue ID; reproducible without models"],
    ["6 Recommend", "Claude Sonnet 5.5 writes the memo from aggregates; code inserts and checks every number"]]
    .map(([b, t]) => `<div class="step"><b>${b}</b>${t}</div>`).join("");
  document.getElementById("calls").innerHTML = `<table><tr><th>Role</th><th>Model</th><th class="num">Calls</th>
    <th class="num">Failed</th><th class="num">Input tokens</th><th class="num">Cost (USD)</th></tr>` +
    (s.calls_by_role || []).map(r => `<tr><td>${esc(r.role)}</td><td><code>${esc(r.model)}</code></td><td class="num">${fmt(r.calls)}</td>
      <td class="num">${fmt(r.failed)}</td><td class="num">${fmt(r.input_tokens)}</td><td class="num">${fmt(r.cost_usd, 4)}</td></tr>`).join("") + "</table>";
}

load().catch(e => { document.getElementById("subtitle").innerHTML = `<span class="warn">Could not load data: ${esc(e.message)}</span>`; });
