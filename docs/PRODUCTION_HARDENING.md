# Production Hardening Plan — KG-RAG Legal Assistant

**Target:** MVP launch — tens to low-hundreds of users, single region, one instance.
**Constraint:** Free / near-free tiers only ($0–~$0/mo).
**Goal:** Stable, secure, and **durable** — never lose data, never OOM, no obvious security holes.

This is deliberately **not** a horizontal-scaling plan. You don't need Kubernetes, autoscaling,
or multiple replicas yet. Those are noted in "Deferred" so you know where the road goes.

---

## TL;DR — do these in order

1. **P0 — Durable database (Postgres).** SQLite on Render free tier is wiped on every redeploy. *(free, ~1 hr)*
2. **P0 — Security must-fix.** Fail-fast on default secrets, lock down CORS. *(free, ~1 hr)*
3. **P1 — Persistent vectors + graph (free managed tiers).** Survive restarts, better retrieval. *(free, ~2 hr)*
4. **P1 — Config-driven prod settings.** One `ENVIRONMENT=production` switch that enforces the above. *(free, ~1 hr)*
5. **P2 — Operational hygiene.** Migrations-lite, error handling, log shipping, uptime ping. *(free, ~2 hr)*
6. **P3 — Quality + cost.** Retrieval quality within free RAM limits, optional paid upgrades. *(decision)*

Total: roughly **one focused day** of work, $0 in recurring cost.

---

## The single biggest risk (read this first)

Render's free web service has an **ephemeral filesystem** and **spins down after ~15 min idle**.
Consequences for the current default deployment:

- `data/app.db` (SQLite) — **users, conversations, billing, API keys are deleted on every redeploy/restart.**
- `data/index/` snapshots — rebuilt on cold start (slow first request, but not data loss).
- First request after spin-down pays a cold-start + graph-rebuild penalty (acceptable for MVP).

**Fix = move the relational data to a free managed Postgres.** Everything else is secondary.

---

## P0 — Durability: managed Postgres

**Why:** Without this, every deploy resets your platform. This alone is the difference between
"demo" and "MVP people can actually sign up for."

**What to do (free):**
- Provision a free Postgres: **Neon** (0.5 GB, no sleep) or **Supabase** (500 MB). Neon recommended.
- Set `DATABASE_URL=postgresql+psycopg://...` in Render env vars.
- Add the driver to `requirements.txt`: `psycopg[binary]>=3.1`.
- Add connection-pool args in [app/db/database.py](../app/db/database.py) for Postgres
  (`pool_pre_ping=True`, modest `pool_size`/`max_overflow`) so dropped idle connections
  (common on free tiers) auto-recover.

**Code touch points:**
- `app/db/database.py` — `get_engine()` already branches on `sqlite`; add the non-sqlite pool config.
- `requirements.txt` — add psycopg.
- No model changes needed (SQLModel is portable).

**Acceptance:** redeploy the service, confirm a user created before the deploy still logs in after.

---

## P0 — Security must-fix

Three holes that are fine for a local demo but not for a public URL.

### 1. Fail-fast on insecure defaults in production
Today the app boots happily with `JWT_SECRET=change-me-in-production` and `ADMIN_PASSWORD=admin`.
Add an `ENVIRONMENT` setting (`development` default / `production`). When `production`:
- Refuse to start if `JWT_SECRET` is the default or shorter than 32 chars.
- Refuse to start if `ADMIN_PASSWORD` is `admin` or empty.

**Touch points:** [app/config.py](../app/config.py) (add field + a `validate_production()` method),
called once in the `lifespan` startup in [app/api/main.py](../app/api/main.py).

### 2. Lock down CORS
[app/api/main.py:58](../app/api/main.py#L58) uses `allow_origins=["*"]`. Replace with an
`ALLOWED_ORIGINS` env var (comma-separated). In production, reject `*`. Keep `*` only in dev.

### 3. Confirm secret hygiene
- `render.yaml` already auto-generates `JWT_SECRET` and marks keys `sync: false` — good.
- Add `ADMIN_PASSWORD` enforcement to the deploy checklist (it's `sync: false` but has no default guard).

**Acceptance:** with `ENVIRONMENT=production` and default secrets, the app exits with a clear error.
With real secrets + a single configured origin, browser calls from other origins are blocked.

---

## P1 — Persistent vectors + graph (free managed tiers)

**Why:** Your retrieval index and knowledge graph are rebuilt in-process at every cold start
([app/bootstrap.py:42](../app/bootstrap.py#L42)). That's fine for correctness but means: slow cold
starts, and all of RAM is spent holding the graph + vectors. Externalizing them frees RAM and
makes restarts cheap. Your abstractions already support both backends — this is **config, not a rewrite.**

**What to do (free):**
- **Vectors → Qdrant Cloud free tier** (1 GB). Set `QDRANT_URL` + `QDRANT_API_KEY`.
- **Graph → Neo4j AuraDB Free** (200k nodes / 400k rels). Set `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD`.
- Run `scripts/ingest_seed.py` once against the managed backends to populate them (the `release`
  phase in `Procfile` / Dockerfile already does this — verify it points at the managed instances).

**⚠️ Embedding-dimension gotcha:** the Qdrant collection is created with whatever the *current*
embedder's `dim` is (hashing=512, MiniLM=384, OpenAI=3072). If you later switch embedders the
collection becomes invalid. **Pin one embedder before first ingest** and document it. See P3.

**Touch points:** none in code — these activate via env vars
([graph_store.py:47](../app/kg/graph_store.py#L47), [vector_store.py:134](../app/retrieval/vector_store.py#L134)).
Just verify the ingest step targets them.

**Acceptance:** `/ready` reports `"graph":"neo4j"` and `"vectors":"qdrant"`, and a cold start no
longer rebuilds the graph from seed (or rebuilds fast).

---

## P1 — One `ENVIRONMENT=production` switch

Tie the above together so prod can't be misconfigured:

- Add `ENVIRONMENT` to `Settings`.
- `validate_production()` checks: strong JWT secret, non-default admin password, non-`*` CORS,
  and (warn, don't fail) that `DATABASE_URL` is not SQLite.
- Print a clear startup banner of what's active vs missing (you already have `provider_banner()` —
  extend it with a prod-readiness section).

**Touch points:** `app/config.py`, `app/api/main.py` lifespan, `.env.example` (document the new vars).

---

## P2 — Operational hygiene

Small things that make the difference when something breaks at 2am.

- **Schema migrations (lite).** You use `SQLModel.metadata.create_all` — fine for greenfield, but it
  won't apply column changes. For MVP, adopt **Alembic** now (one-time setup) so future schema
  changes are safe on the live Postgres. *(Or accept create_all + document "schema changes need a
  manual migration" — acceptable at this scale, but Alembic is cheap insurance.)*
- **Keep-alive ping.** Render free spins down after 15 min. A free **UptimeRobot** monitor hitting
  `/health` every 10 min keeps it warm *and* gives you uptime alerts. (Note: this consumes free
  instance-hours; fine for MVP, revisit if you near the monthly cap.)
- **Error visibility.** Wire **Sentry** (free tier) for exception tracking — far more useful than
  reading Render logs. ~10 lines in `main.py`. Your middleware already catches+logs 500s
  ([middleware.py:32](../app/core/middleware.py#L32)); Sentry adds stack traces + alerting.
- **Log retention.** Render free logs are short-lived. If you want history, ship JSON logs to a free
  tier (Better Stack / Logtail). Optional for MVP.
- **Request-body limits & timeouts.** Add a max request size and an upstream timeout so a slow LLM
  call can't hang a worker indefinitely.

---

## P3 — Quality & cost decisions (no free lunch)

The honest free-tier trade-off on **embeddings**:

| Option | Quality | RAM | Cost |
|--------|---------|-----|------|
| Hashing embedder (current free default) | Low | Tiny | $0 |
| `sentence-transformers/MiniLM` (local) | Good | ~500MB+ (torch) — **OOMs Render 512MB free** | $0 but needs paid instance |
| OpenAI `text-embedding-3-large` | Best | Tiny (API) | ~$0.13/M tokens (cheap, not free) |

**Recommendation for MVP:** either (a) accept hashing embeddings for now and gate retrieval quality
as a "known limitation," or (b) spend the ~$5/mo for a 1GB+ instance so you can run the local MiniLM
model, which is the best quality-per-dollar. OpenAI embeddings cost pennies if you'd rather not host
a model — your call, but it's not strictly "free."

**LLM:** reasoning already runs on Claude when `ANTHROPIC_API_KEY` is set, else the deterministic stub.
The stub is genuinely grounded (cites real KG nodes) so the app is *usable* with zero LLM spend — good
MVP posture. Add a real key when you want natural-language IRAC prose.

---

## Deferred (you don't need these for MVP — here's the road ahead)

- **Multiple workers / replicas** — only meaningful once graph+vectors are fully external (P1 does this).
  Then switch the start command to `gunicorn -k uvicorn.workers.UvicornWorker -w N`. Until then, **stay
  single-worker** (multiple workers each rebuild in-memory state and waste RAM).
- **Async endpoints** — current sync handlers run on the threadpool; fine at this scale.
- **Redis** (`REDIS_URL`) for shared cache/rate-limit — only needed with >1 instance. Upstash has a free
  tier when you get there.
- **Autoscaling, multi-region, load testing, full OpenTelemetry/Prometheus** — growth-stage concerns.

---

## Suggested execution order (one day)

1. Provision Neon Postgres → set `DATABASE_URL`, add psycopg, add pool config. **Verify durability.**
2. Add `ENVIRONMENT` + `validate_production()` + CORS allowlist. **Verify fail-fast.**
3. Provision Qdrant Cloud + Neo4j Aura → set env vars, re-run ingest. **Verify `/ready`.**
4. Add Sentry + UptimeRobot. 
5. (Optional) Alembic baseline migration.
6. Decide embeddings posture (P3) and document it.

Every step is independently shippable and reversible.
