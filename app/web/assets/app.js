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

// refined scales-of-justice mark (monochrome, inherits currentColor)
const SCALES_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M7 6h10"/><path d="M5 21h14"/><path d="M7 6l-3 6a3 3 0 0 0 6 0Z"/><path d="M17 6l-3 6a3 3 0 0 0 6 0Z"/></svg>`;

// ---------- 3D knowledge-graph engine ----------
// `icon` glyphs are plain text so they honour the type colour in the inspector.
const GTYPE = {
  Act:          { color: "#e0a86b", glow: "#ffcf9a", icon: "¶" },
  Section:      { color: "#7fb0ff", glow: "#bcd6ff", icon: "§"  },
  Case:         { color: "#f1909a", glow: "#ffb3ba", icon: "‡" },
  LegalConcept: { color: "#86e6ad", glow: "#bdf6d4", icon: "◆" },
  Amendment:    { color: "#c9a6ff", glow: "#e0caff", icon: "✦" },
  Unknown:      { color: "#a7b0c4", glow: "#d2d8e4", icon: "•" },
};
const gtype = (t) => GTYPE[t] || GTYPE.Unknown;
const _graphs = new Map();   // container element -> ForceGraph3D instance (for resize/cleanup)

// keep every live 3D canvas matched to its container on viewport changes
window.addEventListener("resize", () => {
  for (const [container, Graph] of _graphs) {
    if (!document.body.contains(container)) { _graphs.delete(container); continue; }
    Graph.width(container.clientWidth).height(container.clientHeight);
  }
});

// Build a luxe 3D force graph inside `container` from {nodes, links}.
function build3DGraph(container, data, opts = {}) {
  if (!window.ForceGraph3D) { container.innerHTML = `<div class="grid place-items-center h-full text-xs text-slate-500">3D engine offline — check your connection.</div>`; return null; }
  if (_graphs.has(container)) { try { _graphs.get(container)._destructor(); } catch (_) {} _graphs.delete(container); }
  const W = container.clientWidth || 600, H = container.clientHeight || 360;
  const Graph = ForceGraph3D({ controlType: "orbit" })(container)
    .backgroundColor("rgba(0,0,0,0)")
    .width(W).height(H)
    .showNavInfo(false)
    .nodeRelSize(opts.nodeRelSize || 4)
    .nodeVal("val")
    .nodeColor(n => n.anchor ? gtype(n.type).glow : gtype(n.type).color)
    .nodeOpacity(0.95)
    .linkColor(() => "rgba(212,175,106,0.35)")
    .linkWidth(l => l.type === "RELATED" ? 0.4 : 0.8)
    .linkDirectionalParticles(opts.particles ?? 2)
    .linkDirectionalParticleWidth(1.6)
    .linkDirectionalParticleSpeed(0.006)
    .linkDirectionalParticleColor(() => "#e8d6a8")
    .nodeThreeObject(n => {
      const g = gtype(n.type);
      const sprite = new SpriteText(n.label);
      sprite.color = n.anchor ? "#fff7e6" : "#dbe4f5";
      sprite.backgroundColor = n.anchor ? "rgba(212,175,106,0.28)" : "rgba(8,12,24,0.55)";
      sprite.padding = 2; sprite.borderRadius = 3;
      sprite.fontFace = "Inter"; sprite.fontWeight = n.anchor ? "700" : "500";
      sprite.textHeight = opts.textHeight || 4;
      sprite.material.depthWrite = false;
      return sprite;
    })
    .nodeThreeObjectExtend(true)
    .onNodeHover(n => { container.style.cursor = n ? "pointer" : "grab"; })
    .onNodeClick(n => {
      // fly camera to the node, then surface its details
      opts._paused = true;   // stop auto-rotate so the fly-to isn't overridden
      const dist = 90, r = Math.hypot(n.x, n.y, n.z) || 1;
      Graph.cameraPosition(
        { x: n.x * (1 + dist / r), y: n.y * (1 + dist / r), z: n.z * (1 + dist / r) },
        n, 900
      );
      if (opts.onSelect) opts.onSelect(n); else showInspector(n);
    })
    .graphData(data);

  // luxury bloom post-processing — only the core three.min.js build ships, so
  // UnrealBloomPass may be absent; glow then falls back to node/sprite styling.
  try {
    if (Graph.postProcessingComposer && window.THREE && THREE.UnrealBloomPass) {
      const bloom = new THREE.UnrealBloomPass(new THREE.Vector2(W, H), 1.1, 0.55, 0.18);
      Graph.postProcessingComposer().addPass(bloom);
    }
  } catch (_) {}

  // gentle charge so clusters breathe; slow auto-rotate for the "luxury" feel
  Graph.d3Force("charge").strength(opts.charge ?? -65);
  if (opts.autoRotate !== false) {
    let angle = 0; const dist0 = opts.camDist || 220;
    Graph.cameraPosition({ z: dist0 });
    const rot = () => {
      if (!_graphs.has(container)) return;
      if (!opts._paused) { angle += 0.0016; Graph.cameraPosition({ x: dist0 * Math.sin(angle), z: dist0 * Math.cos(angle) }); }
      requestAnimationFrame(rot);
    };
    requestAnimationFrame(rot);
    container.addEventListener("mousedown", () => opts._paused = true);
  }
  Graph.__opts = opts;
  _graphs.set(container, Graph);
  return Graph;
}

function showInspector(n) {
  const box = el("#nodeInspector"); if (!box) return;
  const g = gtype(n.type);
  el("#niType").innerHTML = `<span style="color:${g.color}">${g.icon}</span> ${esc(n.type)}`;
  el("#niTitle").textContent = n.title || n.label;
  const p = n.props || {};
  const rows = [];
  const add = (k, v) => v && rows.push(`<div><span class="text-slate-500">${k}:</span> ${esc(String(v))}</div>`);
  add("Number", p.number); add("Year", p.year); add("Court", p.court); add("Outcome", p.outcome);
  add("Definition", p.definition);
  if (p.text) rows.push(`<div class="text-slate-300 leading-relaxed mt-1">${esc(String(p.text).slice(0, 260))}${p.text.length > 260 ? "…" : ""}</div>`);
  if (p.summary) rows.push(`<div class="text-slate-300 leading-relaxed mt-1">${esc(String(p.summary).slice(0, 260))}${p.summary.length > 260 ? "…" : ""}</div>`);
  el("#niBody").innerHTML = rows.join("") || `<div class="text-slate-500">${esc(n.id)}</div>`;
  box.classList.remove("hidden");
}

// ---------- bootstrap ----------
window.addEventListener("DOMContentLoaded", async () => {
  initAmbient3D();
  initAurora();
  bindChrome();
  await refreshStatus();
  await refreshAccount();
  switchTab("chat");
  // lift the cinematic curtain once the interface is live
  setTimeout(() => el("#bootScreen")?.classList.add("hide"), 650);
});

// ---------- live 3D ambient constellation (Three.js) ----------
function initAmbient3D() {
  const canvas = el("#bgfx");
  if (!canvas || !window.THREE) return;
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true }); }
  catch (_) { return; }   // no WebGL → silently keep the CSS background
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 1, 2400);
  camera.position.z = 540;

  // soft round glow sprite so particles read as luminous dust, not squares
  const sprite = (() => {
    const c = document.createElement("canvas"); c.width = c.height = 64;
    const g = c.getContext("2d"); const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(.25, "rgba(255,246,224,.85)"); grd.addColorStop(1, "rgba(255,246,224,0)");
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
    const t = new THREE.Texture(c); t.needsUpdate = true; return t;
  })();

  const N = innerWidth < 760 ? 380 : 820;
  const pos = new Float32Array(N * 3), col = new Float32Array(N * 3);
  // warm, ink-toned dust so the particles read softly on the ivory canvas
  const gold = new THREE.Color("#b89352"), blue = new THREE.Color("#5b6b86"), white = new THREE.Color("#8a8073");
  for (let i = 0; i < N; i++) {
    const r = 300 + Math.random() * 760;
    const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th) * 0.62;
    pos[i * 3 + 2] = r * Math.cos(ph);
    const c = Math.random() < .55 ? gold : (Math.random() < .5 ? blue : white);
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const mat = new THREE.PointsMaterial({
    size: 2.2, map: sprite, vertexColors: true, transparent: true, opacity: .5,
    depthWrite: false, blending: THREE.NormalBlending, sizeAttenuation: true,
  });
  const points = new THREE.Points(geo, mat);
  scene.add(points);

  let tmx = 0, tmy = 0;
  window.addEventListener("pointermove", e => { tmx = e.clientX / innerWidth - .5; tmy = e.clientY / innerHeight - .5; });
  const resize = () => { renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); };
  resize(); window.addEventListener("resize", resize);

  (function loop() {
    points.rotation.y += 0.0006; points.rotation.x += 0.00018;
    camera.position.x += (tmx * 130 - camera.position.x) * 0.03;
    camera.position.y += (-tmy * 90 - camera.position.y) * 0.03;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })();
}

// ---------- cursor-follow aurora ----------
function initAurora() {
  const root = document.documentElement;
  window.addEventListener("pointermove", e => {
    root.style.setProperty("--mx", (e.clientX / innerWidth * 100) + "%");
    root.style.setProperty("--my", (e.clientY / innerHeight * 100) + "%");
  }, { passive: true });
}

function closeNav() { document.body.classList.remove("nav-open"); }
function bindChrome() {
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.addEventListener("click", () => switchTab(b.dataset.tab)));
  el("#newChatBtn").addEventListener("click", () => switchTab("chat"));
  // mobile drawer navigation
  el("#mobileMenuBtn")?.addEventListener("click", () => document.body.classList.toggle("nav-open"));
  el("#navScrim")?.addEventListener("click", closeNav);
  el("#authBtn").addEventListener("click", () => {
    if (state.token) { logout(); } else { el("#authModal").classList.remove("hidden"); el("#authModal").classList.add("flex"); }
  });
  el("#authClose").addEventListener("click", closeAuth);
  el("#loginSubmit").addEventListener("click", () => doAuth("login"));
  el("#signupSubmit").addEventListener("click", () => doAuth("signup"));
  el("#upgradeBtn").addEventListener("click", () => switchTab("billing"));
  el("#niClose")?.addEventListener("click", () => el("#nodeInspector").classList.add("hidden"));
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
    state.tier = me.tier; state.isAdmin = me.is_admin; state.email = me.email || state.email;
    btn.textContent = "Sign out";
    usage.textContent = `${me.tier.toUpperCase()} · ${me.usage_today}/${me.daily_quota} today`;
    loadHistory();
  } catch (_) { logout(); }
}

async function doAuth(kind) {
  const email = el("#authEmail").value.trim(), password = el("#authPassword").value;
  try {
    const r = await api("/auth/" + kind, { method: "POST", body: JSON.stringify({ email, password }) });
    state.email = email;
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
  closeNav();
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  el("#nodeInspector")?.classList.add("hidden");
  const r = { chat: renderChat, explorer: renderExplorer, contradiction: renderContradiction, timeline: renderTimeline,
    outcome: renderOutcome, clause: renderClause, jurisdiction: renderJurisdiction,
    drafter: renderDrafter, hindi: renderHindi, admin: renderAdmin, billing: renderBilling };
  (r[tab] || renderChat)();
}

// ---------- CHAT ----------
function renderChat() {
  host().innerHTML = `
    <div class="max-w-5xl mx-auto">
      <div id="chatHero" class="text-center pt-6 pb-10 fade-in">
        <div class="hero-mark mx-auto">${SCALES_SVG}</div>
        <div class="eyebrow mt-5">Indian Legal Intelligence</div>
        <h1 class="font-display text-3xl sm:text-4xl mt-2 text-ink">Grounded answers, verified citations</h1>
        <p class="text-slate-400 mt-3 max-w-xl mx-auto">Every answer is traced to the knowledge graph with verified citations and a live reasoning map — built to resist hallucination. Ask anything about Indian law.</p>
      </div>
      <div id="chatLog" class="space-y-4 mb-6"></div>
      <div class="card composer p-3 sticky bottom-0">
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
function userInitial() { return ((state.email || "U").trim()[0] || "U").toUpperCase(); }
function renderUserMsg(text) {
  el("#chatHero")?.remove();
  const log = el("#chatLog");
  log.insertAdjacentHTML("beforeend",
    `<div class="msg-row user fade-in">
       <div class="bubble-user">${esc(text)}</div>
       <div class="avatar me">${userInitial()}</div>
     </div>`);
  log.lastElementChild?.scrollIntoView({ block: "end", behavior: "smooth" });
}

async function sendChat() {
  const input = el("#chatInput"); const q = input.value.trim(); if (!q) return;
  input.value = ""; renderUserMsg(q);
  const log = el("#chatLog");
  const id = "a" + Date.now();
  log.insertAdjacentHTML("beforeend", `
    <div class="msg-row fade-in">
      <div class="avatar ai">${SCALES_SVG}</div>
      <div id="${id}" class="card answer-card p-4 flex-1 min-w-0">
        <div id="${id}-trace" class="space-y-0.5 mb-2"></div>
        <div id="${id}-body"></div>
      </div>
    </div>`);
  const traceBox = el(`#${id}-trace`);
  el(`#${id}`)?.scrollIntoView({ block: "end", behavior: "smooth" });

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
  el("#chatHero")?.remove();
  const log = el("#chatLog"); const id = "a" + Date.now();
  log.insertAdjacentHTML("beforeend",
    `<div class="msg-row fade-in">
       <div class="avatar ai">${SCALES_SVG}</div>
       <div id="${id}" class="card answer-card p-4 flex-1 min-w-0"><div id="${id}-body"></div></div>
     </div>`);
  el(`#${id}-body`).innerHTML = answerHtml(final); mountGraph(id, final.kg_nodes_traversed);
}
function answerHtml(f) {
  const conf = f.confidence || "LOW";
  const cites = (f.citations || []).map(c => `<div class="text-xs flex gap-2 items-center">${c.verified ? '<span class="cite-ok" title="Verified against the knowledge graph">✓</span>' : '<span class="cite-warn" title="Unverified">!</span>'} <span>${esc(c.display)}</span> <code class="text-slate-500">${esc(c.kg_node || "")}</code></div>`).join("") || `<div class="text-xs text-slate-500">No verified citations</div>`;
  return `
    <div class="flex items-center gap-3 mb-2 text-xs">
      ${pill(conf)} <span class="text-slate-400">hallucination: ${(f.hallucination_score ?? 0).toFixed(2)}</span>
      ${f.cache_hit ? '<span class="pill">cached</span>' : ""}
    </div>
    <div class="markdown text-sm">${marked.parse(f.answer || "")}</div>
    <div class="grid md:grid-cols-2 gap-4 mt-4">
      <div><div class="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Citations</div>${cites}</div>
      <div>
        <div class="flex items-center justify-between mb-1">
          <div class="text-[11px] uppercase tracking-wider text-slate-500">Knowledge-graph traversal · 3D</div>
          <span class="text-[10px] text-slate-600">drag to orbit · click a node</span>
        </div>
        <div id="GRAPH" class="graph3d h-64 rounded-lg border border-edge bg-ink/40 relative overflow-hidden"></div>
      </div>
    </div>`;
}
// Fetch the real induced subgraph (typed edges + node metadata) and render it in 3D.
async function mountGraph(scope, nodeIds) {
  const container = el(`#${scope}`)?.querySelector("#GRAPH"); if (!container) return;
  container.innerHTML = `<div class="grid place-items-center h-full text-xs text-slate-500 animate-pulse">Rendering knowledge graph…</div>`;
  let data = { nodes: [], links: [] };
  try {
    data = await api("/graph/subgraph", { method: "POST", body: JSON.stringify({ node_ids: nodeIds || [], expand: 1 }) });
  } catch (_) {
    // fallback: star graph from the raw IDs so the panel is never empty
    data = { nodes: (nodeIds || []).map(id => ({ id, label: id.replace(/^node_|^case_|^concept_|^act_/, ""), type: "Unknown", val: 5, anchor: true })), links: [] };
    for (let i = 1; i < data.nodes.length; i++) data.links.push({ source: data.nodes[0].id, target: data.nodes[i].id, type: "RELATED" });
  }
  container.innerHTML = "";
  if (!data.nodes.length) { container.innerHTML = `<div class="grid place-items-center h-full text-xs text-slate-500">No graph nodes traversed.</div>`; return; }
  build3DGraph(container, data, { particles: 2, textHeight: 4, camDist: 180, autoRotate: true });
  container.insertAdjacentHTML("beforeend", graphLegendHtml(true));
}
function graphLegendHtml(compact = false) {
  const items = ["Act", "Section", "Case", "LegalConcept", "Amendment"];
  return `<div class="graph-legend ${compact ? "compact" : ""}">` +
    items.map(t => `<span class="leg"><i style="background:${gtype(t).color}"></i>${t === "LegalConcept" ? "Concept" : t}</span>`).join("") + `</div>`;
}

// ---------- 3D GRAPH EXPLORER (full galaxy) ----------
async function renderExplorer() {
  host().innerHTML = `
    <div class="explorer-wrap fade-in">
      <div class="flex items-end justify-between mb-3 flex-wrap gap-3">
        <div>
          <div class="eyebrow mb-1">Knowledge Graph</div>
          <h2 class="font-display text-2xl text-ink">Graph Explorer</h2>
          <p class="text-sm text-slate-400">The living map of Indian law — statutes, cases, concepts &amp; amendments in 3D. Drag to orbit, scroll to zoom, click any node.</p>
        </div>
        <div class="flex items-center gap-2">
          <input id="gqSearch" class="lux-input !w-56" placeholder="Find a section / case…" />
          <button id="gqReset" class="text-xs px-3 py-2 rounded-lg border border-edge hover:border-gold/50">Reset view</button>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2 mb-3" id="gFilters"></div>
      <div class="relative rounded-2xl border border-edge overflow-hidden bg-ink/40" style="height:68vh">
        <div id="EXPLORER" class="graph3d absolute inset-0"></div>
        <div id="gStats" class="absolute top-3 left-4 text-[11px] text-slate-400"></div>
        ${graphLegendHtml(false).replace('class="graph-legend ', 'class="graph-legend explorer-legend ')}
      </div>
    </div>`;

  const cont = el("#EXPLORER");
  cont.innerHTML = `<div class="grid place-items-center h-full text-sm text-slate-400 animate-pulse">Loading the legal universe…</div>`;
  let full;
  try { full = await api("/graph/full?limit=400"); }
  catch (e) { cont.innerHTML = `<div class="grid place-items-center h-full text-sm text-red-400">Could not load graph: ${esc(e.message)}</div>`; return; }
  cont.innerHTML = "";
  el("#gStats").innerHTML = `<b class="text-gold">${full.nodes.length}</b> nodes · <b class="text-gold">${full.links.length}</b> relationships`;

  const active = new Set(Object.keys(GTYPE).filter(t => t !== "Unknown"));
  const Graph = build3DGraph(cont, full, { particles: 1, textHeight: 5, camDist: 320, charge: -90, autoRotate: true, nodeRelSize: 4 });

  function applyFilter() {
    const nodes = full.nodes.filter(n => active.has(n.type));
    const ids = new Set(nodes.map(n => n.id));
    const links = full.links.filter(l => ids.has(l.source.id || l.source) && ids.has(l.target.id || l.target));
    Graph.graphData({ nodes, links });
    el("#gStats").innerHTML = `<b class="text-gold">${nodes.length}</b> nodes · <b class="text-gold">${links.length}</b> relationships`;
  }
  // type filter chips
  el("#gFilters").innerHTML = [...active].map(t =>
    `<button class="gchip active" data-t="${t}"><i style="background:${gtype(t).color}"></i>${t === "LegalConcept" ? "Concepts" : t + "s"}</button>`).join("");
  el("#gFilters").querySelectorAll(".gchip").forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.t; b.classList.toggle("active");
    if (active.has(t)) active.delete(t); else active.add(t);
    applyFilter();
  }));

  // search → focus the matching node
  el("#gqSearch").addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    const q = e.target.value.trim().toLowerCase(); if (!q) return;
    const hit = full.nodes.find(n => (n.label + " " + n.title).toLowerCase().includes(q));
    if (!hit) { el("#gStats").innerHTML = `<span class="text-red-400">No match for "${esc(q)}"</span>`; return; }
    Graph.__opts._paused = true;
    const r = Math.hypot(hit.x || 1, hit.y || 1, hit.z || 1) || 1;
    Graph.cameraPosition({ x: hit.x * 1.6, y: hit.y * 1.6, z: hit.z * 1.6 + 40 }, hit, 1000);
    showInspector(hit);
  });
  el("#gqReset").addEventListener("click", () => { Graph.__opts._paused = true; Graph.zoomToFit(800, 60); el("#nodeInspector").classList.add("hidden"); });
}

// ---------- generic feature panel helper ----------
function panel(title, subtitle, inner, eyebrow = "Legal Tool") {
  host().innerHTML = `<div class="max-w-4xl mx-auto fade-in">
    <div class="eyebrow mb-2">${eyebrow}</div>
    <h2 class="font-display text-2xl text-ink mb-1">${title}</h2>
    <p class="text-sm text-slate-400 mb-5">${subtitle}</p>
    <div class="card p-5">${inner}</div>
    <div id="result" class="mt-5"></div></div>`;
}
function loading() { el("#result").innerHTML = `<div class="text-sm text-slate-400 animate-pulse">Analyzing…</div>`; }
function showJSONerr(e) { el("#result").innerHTML = `<div class="text-red-400 text-sm">Error: ${esc(e.message)}</div>`; }

// ---------- CONTRADICTION ----------
function renderContradiction() {
  panel("Legal Contradiction Detector", "Upload/paste a contract clause-set; we flag conflicts against Indian statutes (PRD §7.1).",
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
  panel("Temporal Legal Timeline", "Amendment history + 'law as of date X' (PRD §7.2).",
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
  panel("Case Outcome Predictor", "Precedent-strength analysis from similar historical cases (PRD §7.3). Probabilistic & educational — not legal advice.",
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
  panel("Clause Risk Scorer", "Per-clause litigation risk (LOW/MED/HIGH) against the knowledge base (PRD §4.2).",
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
  panel("Jurisdiction Mapper", "Central vs State competence + precedent level (PRD §4.2).",
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
  panel("Smart Contract Drafter", "RAG-backed draft with legal basis + per-clause risk (PRD §4.2).",
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
  panel("Hindi Legal Query Bridge", "Ask in Hindi; we translate via legal glossary and answer with citations (PRD §7.4).",
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
  if (!state.isAdmin) { panel("Admin Analytics", "Sign in as an admin to view.", `<div class="text-sm text-slate-400">Admin access required (demo: admin@kg-legal.ai / admin).</div>`); return; }
  panel("Admin Analytics", "Live query volume, latency, confidence & quality (PRD §8.3).",
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
  panel("Plans & Billing", "Upgrade your tier (demo stub — no card charged).", `<div id="plans" class="grid sm:grid-cols-3 gap-4"></div>`, "Subscription");
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
