/* KG-RAG Legal Assistant — premium SPA */
const API = "/api/v1";
const state = { token: localStorage.getItem("kgl_token") || "", tier: "free", isAdmin: false, currentTab: "chat" };

// ---------- helpers ----------
function authHeaders(extra = {}) {
  const h = { "Content-Type": "application/json", ...extra };
  if (state.token) h["Authorization"] = "Bearer " + state.token;
  return h;
}
async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: authHeaders(opts.headers), ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}
const el = (sel) => document.querySelector(sel);
const host = () => el("#panelHost");
function esc(s) { return (s || "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function pill(level, kind = "") { return `<span class="pill pill-${level}${kind}">${level}</span>`; }

// ---------- bootstrap ----------
window.addEventListener("DOMContentLoaded", async () => {
  bindChrome();
  await refreshStatus();
  await refreshAccount();
  switchTab("chat");
});

function bindChrome() {
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.addEventListener("click", () => switchTab(b.dataset.tab)));
  el("#newChatBtn").addEventListener("click", () => switchTab("chat"));
  el("#authBtn").addEventListener("click", () => {
    if (state.token) { logout(); } else { el("#authModal").classList.remove("hidden"); el("#authModal").classList.add("flex"); }
  });
  el("#authClose").addEventListener("click", closeAuth);
  el("#loginSubmit").addEventListener("click", () => doAuth("login"));
  el("#signupSubmit").addEventListener("click", () => doAuth("signup"));
  el("#upgradeBtn").addEventListener("click", () => switchTab("billing"));
}
function closeAuth() { el("#authModal").classList.add("hidden"); el("#authModal").classList.remove("flex"); }

async function refreshStatus() {
  try {
    const r = await fetch("/ready").then(x => x.json());
    const p = r.providers || {};
    el("#providerBadge").textContent =
      `LLM:${p.llm} · graph:${p.graph} · vec:${p.vectors} · rerank:${p.rerank}`;
    el("#providerBadge").classList.remove("hidden");
  } catch (_) {}
}

async function refreshAccount() {
  const btn = el("#authBtn"), usage = el("#usageBadge");
  if (!state.token) { btn.textContent = "Sign in"; usage.textContent = ""; return; }
  try {
    const me = await api("/auth/me");
    state.tier = me.tier; state.isAdmin = me.is_admin;
    btn.textContent = "Sign out";
    usage.textContent = `${me.tier.toUpperCase()} · ${me.usage_today}/${me.daily_quota} today`;
    loadHistory();
  } catch (_) { logout(); }
}

async function doAuth(kind) {
  const email = el("#authEmail").value.trim(), password = el("#authPassword").value;
  try {
    const r = await api("/auth/" + kind, { method: "POST", body: JSON.stringify({ email, password }) });
    state.token = r.access_token; localStorage.setItem("kgl_token", state.token);
    closeAuth(); await refreshAccount(); switchTab(state.currentTab);
  } catch (e) { alert(kind + " failed: " + e.message); }
}
function logout() { state.token = ""; localStorage.removeItem("kgl_token"); state.isAdmin = false; refreshAccount(); }

async function loadHistory() {
  const box = el("#historyBox"); if (!box || !state.token) return;
  try {
    const convs = await api("/chat/conversations");
    box.innerHTML = `<div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">History</div>` +
      convs.slice(0, 12).map(c => `<button class="block w-full text-left truncate hover:text-goldsoft" data-cid="${c.id}">• ${esc(c.title)}</button>`).join("");
    box.querySelectorAll("[data-cid]").forEach(b => b.addEventListener("click", () => openConversation(b.dataset.cid)));
  } catch (_) {}
}
async function openConversation(cid) {
  switchTab("chat");
  const msgs = await api("/chat/conversations/" + cid);
  const log = el("#chatLog"); log.innerHTML = "";
  msgs.forEach(m => m.role === "user" ? renderUserMsg(m.content) : renderAnswer({ answer: m.content, confidence: m.confidence, citations: m.citations || [], kg_nodes_traversed: m.kg_nodes || [], trace: [] }));
}

// ---------- tab routing ----------
function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  const r = { chat: renderChat, contradiction: renderContradiction, timeline: renderTimeline,
    outcome: renderOutcome, clause: renderClause, jurisdiction: renderJurisdiction,
    drafter: renderDrafter, hindi: renderHindi, admin: renderAdmin, billing: renderBilling };
  (r[tab] || renderChat)();
}

// ---------- CHAT ----------
function renderChat() {
  host().innerHTML = `
    <div class="max-w-5xl mx-auto">
      <div id="chatLog" class="space-y-4 mb-6"></div>
      <div class="card p-3 sticky bottom-0">
        <div class="flex gap-2">
          <input id="chatInput" class="lux-input" placeholder="Ask any Indian-law question — e.g. Can anticipatory bail be granted for Section 302 IPC?" />
          <button id="chatSend" class="glow-btn px-6">Ask</button>
        </div>
        <div class="flex gap-2 mt-2 flex-wrap text-[11px] text-slate-400">
          ${["What is the punishment under Section 302 IPC?","Can anticipatory bail be granted for Section 302?","What changed in CrPC Section 41 after 2009?","Is a 12-month non-compete clause enforceable in India?"]
            .map(q => `<button class="suggest px-2 py-1 rounded border border-edge hover:border-gold/50">${q}</button>`).join("")}
        </div>
      </div>
    </div>`;
  el("#chatSend").addEventListener("click", sendChat);
  el("#chatInput").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });
  document.querySelectorAll(".suggest").forEach(b => b.addEventListener("click", () => { el("#chatInput").value = b.textContent; sendChat(); }));
}
function renderUserMsg(text) {
  const log = el("#chatLog");
  log.insertAdjacentHTML("beforeend", `<div class="fade-in flex justify-end"><div class="card px-4 py-2 max-w-2xl bg-edge/40">${esc(text)}</div></div>`);
  log.scrollIntoView({ block: "end" });
}

async function sendChat() {
  const input = el("#chatInput"); const q = input.value.trim(); if (!q) return;
  input.value = ""; renderUserMsg(q);
  const log = el("#chatLog");
  const id = "a" + Date.now();
  log.insertAdjacentHTML("beforeend", `
    <div id="${id}" class="fade-in card p-4">
      <div id="${id}-trace" class="space-y-0.5 mb-2"></div>
      <div id="${id}-body"></div>
    </div>`);
  const traceBox = el(`#${id}-trace`);

  try {
    const res = await fetch(API + "/chat/stream", { method: "POST", headers: authHeaders(), body: JSON.stringify({ query: q }) });
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "", final = null, evt = null;
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop();
      for (const line of lines) {
        if (line.startsWith("event:")) evt = line.slice(6).trim();
        else if (line.startsWith("data:")) {
          const data = line.slice(5).trim(); if (!data) continue;
          if (evt === "progress") {
            const d = JSON.parse(data);
            traceBox.insertAdjacentHTML("beforeend", `<div class="trace-step"><span class="dot"></span><span>${esc(d.message)}</span></div>`);
          } else if (evt === "result") { final = JSON.parse(data); }
        }
      }
    }
    if (final) { el(`#${id}-body`).innerHTML = answerHtml(final); mountGraph(`${id}`, final.kg_nodes_traversed); }
    loadHistory();
  } catch (e) {
    el(`#${id}-body`).innerHTML = `<div class="text-red-400 text-sm">Error: ${esc(e.message)}</div>`;
  }
}

function renderAnswer(final) {
  const log = el("#chatLog"); const id = "a" + Date.now();
  log.insertAdjacentHTML("beforeend", `<div id="${id}" class="fade-in card p-4"><div id="${id}-body"></div></div>`);
  el(`#${id}-body`).innerHTML = answerHtml(final); mountGraph(id, final.kg_nodes_traversed);
}
function answerHtml(f) {
  const conf = f.confidence || "LOW";
  const cites = (f.citations || []).map(c => `<div class="text-xs flex gap-2 items-center">${c.verified ? "✅" : "⚠️"} <span>${esc(c.display)}</span> <code class="text-slate-500">${esc(c.kg_node || "")}</code></div>`).join("") || `<div class="text-xs text-slate-500">No verified citations</div>`;
  return `
    <div class="flex items-center gap-3 mb-2 text-xs">
      ${pill(conf)} <span class="text-slate-400">hallucination: ${(f.hallucination_score ?? 0).toFixed(2)}</span>
      ${f.cache_hit ? '<span class="pill">cached</span>' : ""}
    </div>
    <div class="markdown text-sm">${marked.parse(f.answer || "")}</div>
    <div class="grid md:grid-cols-2 gap-4 mt-4">
      <div><div class="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Citations</div>${cites}</div>
      <div><div class="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Knowledge-graph traversal</div><div id="GRAPH" class="h-56 rounded-lg border border-edge bg-ink/40"></div></div>
    </div>`;
}
function mountGraph(scope, nodeIds) {
  // find the latest GRAPH placeholder inside this scope
  const container = el(`#${scope}`)?.querySelector("#GRAPH"); if (!container || !window.vis) return;
  const nodes = (nodeIds || []).map(id => ({ id, label: id.replace(/^node_|^case_|^concept_/, ""), shape: "dot", size: 14 }));
  const edges = [];
  for (let i = 1; i < nodes.length; i++) edges.push({ from: nodes[0].id, to: nodes[i].id });
  new vis.Network(container, { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, {
    nodes: { color: { background: "#d4af6a", border: "#e8d6a8" }, font: { color: "#cdd6f4", size: 11 } },
    edges: { color: "#3a4straight" .replace("straight","663"), smooth: true },
    physics: { stabilization: true }, interaction: { hover: true }
  });
}

// ---------- generic feature panel helper ----------
function panel(title, subtitle, inner) {
  host().innerHTML = `<div class="max-w-4xl mx-auto fade-in">
    <h2 class="font-display text-2xl text-goldsoft mb-1">${title}</h2>
    <p class="text-sm text-slate-400 mb-5">${subtitle}</p>
    <div class="card p-5">${inner}</div>
    <div id="result" class="mt-5"></div></div>`;
}
function loading() { el("#result").innerHTML = `<div class="text-sm text-slate-400 animate-pulse">Analyzing…</div>`; }
function showJSONerr(e) { el("#result").innerHTML = `<div class="text-red-400 text-sm">Error: ${esc(e.message)}</div>`; }

// ---------- CONTRADICTION ----------
function renderContradiction() {
  panel("⚔️ Legal Contradiction Detector", "Upload/paste a contract clause-set; we flag conflicts against Indian statutes (PRD §7.1).",
    `<textarea id="docA" class="lux-input mb-2" placeholder="Document A (e.g. employment contract clauses)…">The employee agrees to a 12-month non-compete after termination. The employee waives all statutory gratuity rights.</textarea>
     <textarea id="docB" class="lux-input mb-3" placeholder="Document B (optional — statute text). Leave blank to match against the knowledge graph."></textarea>
     <button id="run" class="glow-btn px-5 py-2">Detect Conflicts</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/contradiction", { method: "POST", body: JSON.stringify({ document_a: el("#docA").value, document_b: el("#docB").value }) });
      el("#result").innerHTML = `<div class="card p-4"><div class="text-sm mb-3">Analyzed <b>${r.clauses_analyzed}</b> clauses · <b class="text-gold">${r.conflicts_found}</b> conflict(s)</div>` +
        (r.conflicts.map(c => `<div class="border-t border-edge pt-3 mt-3">
          <div class="text-xs mb-1">${pill((c.conflict_type||"none").toUpperCase())} <span class="text-slate-400">confidence ${c.confidence}</span></div>
          <div class="text-sm"><b class="text-goldsoft">Clause:</b> ${esc(c.clause_a)}</div>
          <div class="text-sm mt-1"><b class="text-accent">Conflicts with:</b> ${esc(c.provision_b)}</div>
          <div class="text-sm mt-1 text-slate-300"><b>Remedy:</b> ${esc(c.remedy||"-")}</div></div>`).join("") || `<div class="text-sm text-green-300">No conflicts detected.</div>`) + `</div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- TIMELINE ----------
function renderTimeline() {
  panel("🕰️ Temporal Legal Timeline", "Amendment history + 'law as of date X' (PRD §7.2).",
    `<div class="flex gap-2 mb-3"><input id="sec" class="lux-input" placeholder="Section number (e.g. 41 or 66A)" value="41" />
     <input id="asof" class="lux-input" placeholder="As of date (YYYY-MM-DD, optional)" value="2008-01-01" /></div>
     <button id="run" class="glow-btn px-5 py-2">Build Timeline</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/timeline", { method: "POST", body: JSON.stringify({ section_number: el("#sec").value, as_of_date: el("#asof").value || null }) });
      if (!r.found) { el("#result").innerHTML = `<div class="text-sm text-slate-400">Section not found in graph.</div>`; return; }
      el("#result").innerHTML = `<div class="card p-4">
        <div class="font-display text-lg text-goldsoft">Section ${esc(r.section)} — ${esc(r.title||"")}</div>
        <div class="text-sm mt-2"><b>Current text:</b> ${esc(r.current_text||"")}</div>
        ${r.as_of_date ? `<div class="text-sm mt-2 text-accent"><b>As of ${esc(r.as_of_date)}:</b> ${esc(r.applicable_text_as_of_date||"")}</div>` : ""}
        <div class="mt-4 space-y-3">${r.events.map(ev => `<div class="border-l-2 border-gold pl-3"><div class="text-xs text-gold">${esc(ev.effective_date||ev.year||"")}</div>
          <div class="text-sm">${esc(ev.trigger_event||ev.change_type||"")}</div>
          <div class="text-xs text-slate-400">${esc(ev.new_text||"")}</div></div>`).join("") || `<div class="text-sm text-slate-400">No amendments recorded.</div>`}</div></div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- OUTCOME ----------
function renderOutcome() {
  panel("📊 Case Outcome Predictor", "Precedent-strength analysis from similar historical cases (PRD §7.3). Probabilistic & educational — not legal advice.",
    `<textarea id="facts" class="lux-input mb-2" placeholder="Describe the case facts…">Accused charged under Section 302 in a sudden fight with grave provocation and no premeditation.</textarea>
     <div class="flex gap-2 mb-3"><input id="sec" class="lux-input" placeholder="Offence section (optional)" value="302" />
     <input id="desired" class="lux-input" placeholder="Desired outcome (optional)" value="acquittal" /></div>
     <button id="run" class="glow-btn px-5 py-2">Analyze Precedent Strength</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/outcome", { method: "POST", body: JSON.stringify({ facts: el("#facts").value, offence_section: el("#sec").value || null, desired_outcome: el("#desired").value || null }) });
      if (!r.outcome_distribution) { el("#result").innerHTML = `<div class="text-sm text-slate-400">${esc(r.message||"No comparable cases.")}</div>`; return; }
      const dist = Object.entries(r.outcome_distribution).map(([k, v]) => `<div class="flex items-center gap-2 text-sm"><div class="w-28 text-slate-400">${esc(k)}</div><div class="flex-1 bg-edge rounded h-2"><div class="h-2 rounded bg-gradient-to-r from-gold to-goldsoft" style="width:${v*100}%"></div></div><div class="w-10 text-right">${Math.round(v*100)}%</div></div>`).join("");
      el("#result").innerHTML = `<div class="card p-4">
        <div class="flex items-center gap-3 mb-3"><span class="text-3xl font-display text-gold">${Math.round(r.precedent_strength_score*100)}%</span>${pill(r.strength_label)}
        <span class="text-sm text-slate-400">strength for "${esc(r.desired_outcome)}" · ${r.similar_cases_found} similar cases</span></div>
        <div class="space-y-1 mb-4">${dist}</div>
        <div class="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Closest precedents</div>
        ${r.top_cases.map(c => `<div class="text-sm border-t border-edge pt-2 mt-2">${esc(c.title)} (${c.year}) — ${pill((c.outcome||"").toUpperCase().replace(/ /g,"_").slice(0,8))} <span class="text-slate-500">${(c.factors||[]).join(", ")}</span></div>`).join("")}
        <div class="text-[11px] text-slate-500 mt-3">${esc(r.disclaimer)}</div></div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- CLAUSE RISK ----------
function renderClause() {
  panel("🛡️ Clause Risk Scorer", "Per-clause litigation risk (LOW/MED/HIGH) against the knowledge base (PRD §4.2).",
    `<textarea id="ct" class="lux-input mb-3" placeholder="Paste contract text…">The employee shall not compete for 24 months post termination.
The company bears unlimited liability for all losses.
Confidential information shall remain secret.
This agreement may be terminated by either party.</textarea>
     <button id="run" class="glow-btn px-5 py-2">Score Clauses</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/clause-risk", { method: "POST", body: JSON.stringify({ contract_text: el("#ct").value }) });
      el("#result").innerHTML = `<div class="card p-4"><div class="text-sm mb-3">Overall risk: ${pill(r.overall_risk)} · ${r.clauses_scored} clauses (H:${r.distribution.HIGH} M:${r.distribution.MEDIUM} L:${r.distribution.LOW})</div>` +
        r.clauses.map(c => `<div class="border-t border-edge pt-2 mt-2 text-sm">${pill(c.risk_level)} ${esc(c.clause)}<div class="text-xs text-slate-400 mt-0.5">${esc(c.rationale)}</div></div>`).join("") + `</div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- JURISDICTION ----------
function renderJurisdiction() {
  panel("🗺️ Jurisdiction Mapper", "Central vs State competence + precedent level (PRD §4.2).",
    `<input id="q" class="lux-input mb-3" placeholder="Legal query…" value="Is a shops and establishment registration mandatory?" />
     <button id="run" class="glow-btn px-5 py-2">Map Jurisdiction</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/jurisdiction", { method: "POST", body: JSON.stringify({ query: el("#q").value }) });
      el("#result").innerHTML = `<div class="card p-4 text-sm space-y-2">
        <div>${pill(r.legislative_competence)} ${esc(r.legislative_note)}</div>
        <div><b class="text-goldsoft">Precedent:</b> ${esc(r.precedent_note)}</div>
        ${r.state_specific_variations.length ? `<div><b>Watch:</b> ${r.state_specific_variations.map(esc).join("; ")}</div>` : ""}
      </div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- DRAFTER ----------
function renderDrafter() {
  panel("✍️ Smart Contract Drafter", "RAG-backed draft with legal basis + per-clause risk (PRD §4.2).",
    `<div class="flex gap-2 mb-2"><select id="ctype" class="lux-input"><option value="employment">Employment</option><option value="nda">NDA</option><option value="service">Service</option></select>
     <input id="parties" class="lux-input" placeholder="Parties (comma separated)" value="Acme Pvt Ltd, Mr. Sharma" /></div>
     <input id="terms" class="lux-input mb-3" placeholder="Key terms (optional)" value="6-month probation, Bengaluru jurisdiction" />
     <button id="run" class="glow-btn px-5 py-2">Generate Draft</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/draft", { method: "POST", body: JSON.stringify({ contract_type: el("#ctype").value, parties: el("#parties").value.split(",").map(s => s.trim()), key_terms: el("#terms").value }) });
      el("#result").innerHTML = `<div class="card p-4"><div class="markdown text-sm">${marked.parse(r.draft_markdown)}</div>
        <div class="text-[11px] uppercase tracking-wider text-slate-500 mt-4 mb-1">Clause legal basis & risk</div>
        ${r.clauses.map(c => `<div class="text-xs border-t border-edge pt-2 mt-2">${pill(c.risk_level)} <b>${esc(c.heading)}</b> — basis: <code class="text-slate-500">${esc(c.legal_basis_node||"n/a")}</code></div>`).join("")}
        <div class="text-[11px] text-slate-500 mt-3">${esc(r.disclaimer)}</div></div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- HINDI ----------
function renderHindi() {
  panel("🇮🇳 Hindi Legal Query Bridge", "Ask in Hindi; we translate via legal glossary and answer with citations (PRD §7.4).",
    `<input id="q" class="lux-input mb-3" placeholder="हिंदी में प्रश्न…" value="dhara 302 ki saja kya hai" />
     <button id="run" class="glow-btn px-5 py-2">Translate & Answer</button>`);
  el("#run").addEventListener("click", async () => {
    loading();
    try {
      const r = await api("/features/hindi", { method: "POST", body: JSON.stringify({ query_hi: el("#q").value }) });
      el("#result").innerHTML = `<div class="card p-4"><div class="text-xs text-slate-400 mb-2">Translated: <span class="text-goldsoft">${esc(r.translated_en)}</span></div>
        <div class="markdown text-sm">${marked.parse(r.answer.answer||"")}</div></div>`;
    } catch (e) { showJSONerr(e); }
  });
}

// ---------- ADMIN ----------
async function renderAdmin() {
  if (!state.isAdmin) { panel("📈 Admin Analytics", "Sign in as an admin to view.", `<div class="text-sm text-slate-400">Admin access required (demo: admin@kg-legal.ai / admin).</div>`); return; }
  panel("📈 Admin Analytics", "Live query volume, latency, confidence & quality (PRD §8.3).",
    `<div class="grid sm:grid-cols-4 gap-3" id="kpis"></div>
     <div class="grid md:grid-cols-2 gap-4 mt-4"><div class="card p-3"><canvas id="volChart" height="160"></canvas></div><div class="card p-3"><canvas id="confChart" height="160"></canvas></div></div>
     <div id="evalBox" class="mt-4"></div>`);
  el("#result").innerHTML = "";
  try {
    const m = await api("/admin/metrics");
    const kpi = (label, val) => `<div class="card p-3"><div class="text-2xl font-display text-gold">${val}</div><div class="text-xs text-slate-400">${label}</div></div>`;
    el("#kpis").innerHTML = kpi("Total queries", m.total_queries) + kpi("p50 latency", m.latency_ms.p50 + "ms") +
      kpi("p95 latency", m.latency_ms.p95 + "ms") + kpi("Cache hit", Math.round(m.cache_hit_rate*100) + "%");
    const days = Object.keys(m.queries_by_day), vals = Object.values(m.queries_by_day);
    new Chart(el("#volChart"), { type: "line", data: { labels: days, datasets: [{ label: "Queries/day", data: vals, borderColor: "#d4af6a", backgroundColor: "rgba(212,175,106,.15)", fill: true, tension: .3 }] }, options: chartOpts() });
    const cd = m.confidence_distribution || {};
    new Chart(el("#confChart"), { type: "doughnut", data: { labels: Object.keys(cd), datasets: [{ data: Object.values(cd), backgroundColor: ["#7ee2a8","#e8d6a8","#f1a3a3"] }] }, options: chartOpts() });
    const ev = await api("/admin/eval");
    el("#evalBox").innerHTML = `<div class="card p-4 text-sm">Golden-set eval — recall: <b class="text-gold">${ev.retrieval_recall}</b> · citation grounding: <b class="text-gold">${ev.avg_citation_grounding}</b> (targets ${ev.targets.retrieval_recall} / ${ev.targets.citation_grounding})</div>`;
  } catch (e) { showJSONerr(e); }
}
function chartOpts() { return { plugins: { legend: { labels: { color: "#9fb0d0" } } }, scales: { x: { ticks: { color: "#7f8db0" }, grid: { color: "#1e2740" } }, y: { ticks: { color: "#7f8db0" }, grid: { color: "#1e2740" } } } }; }

// ---------- BILLING ----------
async function renderBilling() {
  panel("💎 Plans & Billing", "Upgrade your tier (demo stub — no card charged).", `<div id="plans" class="grid sm:grid-cols-3 gap-4"></div>`);
  el("#result").innerHTML = "";
  const plans = await api("/billing/plans");
  el("#plans").innerHTML = plans.map(p => `<div class="card p-5 text-center">
    <div class="font-display text-xl text-goldsoft">${p.label}</div>
    <div class="text-3xl my-2">₹${p.price_inr_month}<span class="text-sm text-slate-400">/mo</span></div>
    <div class="text-xs text-slate-400 mb-3">${p.daily_quota} queries/day</div>
    <button class="glow-btn w-full py-2 upgrade" data-tier="${p.tier}">Choose ${p.label}</button></div>`).join("");
  document.querySelectorAll(".upgrade").forEach(b => b.addEventListener("click", async () => {
    if (!state.token) { alert("Sign in first."); return; }
    try { const r = await api("/billing/checkout", { method: "POST", body: JSON.stringify({ tier: b.dataset.tier }) }); alert(r.message); refreshAccount(); }
    catch (e) { alert(e.message); }
  }));
}
