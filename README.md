# ⚖️ KG-RAG Legal Assistant — Production Platform

India's Knowledge-Graph-powered, multi-agent **legal intelligence platform**. It combines a
**Neo4j knowledge graph**, **hybrid vector retrieval** (dense + BM25 + RRF + Cohere rerank), and a
**7-node LangGraph pipeline** to deliver **citation-grounded, hallucination-checked IRAC answers**
for Indian law — wrapped in a **premium web product** with auth, history, billing tiers, an admin
analytics dashboard, and a full suite of differentiator features.

**Local-first & zero-config:** runs end-to-end **offline** (SQLite + in-memory cache/graph/vectors +
deterministic stub reasoner). Add credentials to `.env` and each layer **auto-upgrades** to its real
provider — no code changes.

```
┌────────────────────────── Premium SPA (served by FastAPI at / ) ──────────────────────────┐
│  streaming chat · KG graph viz · 7 feature tabs · history · admin charts · billing         │
└──────────────────────────────────────────┬─────────────────────────────────────────────────┘
                                            │  /api/v1/*  (auth · chat · features · admin · billing)
┌───────────────────────────── FastAPI (middleware: req-id, rate-limit, security) ───────────┐
│  query_planner → retrieval → irac_reasoner → citation_verifier → synthesizer  (+rewrite loop)│
│        hybrid retrieval: KG Cypher + dense vectors + BM25  →  RRF  →  rerank  →  top-k        │
│  persistence (SQLite/Postgres) · cache (mem/Redis) · rate-limit · structured logs · tracing  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

## Provider abstraction (real ↔ fallback)

| Layer | Real (set in `.env`) | Fallback (always runs) |
|---|---|---|
| LLM | Anthropic Claude (Opus/Haiku) | deterministic grounded stub |
| Embeddings | OpenAI `text-embedding-3-large` | sentence-transformers / hashing |
| Graph | Neo4j AuraDB | in-memory NetworkX |
| Vectors | Qdrant | in-memory numpy cosine |
| Rerank | Cohere | RRF passthrough |
| DB | Postgres (`DATABASE_URL`) | SQLite (`data/app.db`) |
| Cache / Rate-limit | Redis (`REDIS_URL`) | in-memory |
| Tracing | LangSmith / Phoenix | no-op |

## Quickstart (no keys needed)

```bash
pip install -r requirements.txt
python scripts/ingest_seed.py          # build KG + indexes
pytest -q                              # 15+ tests, all on fallbacks
uvicorn app.api.main:app --reload      # open http://localhost:8000  → premium SPA
```

Or with the classic demo UI: `streamlit run ui/streamlit_app.py`
Or the whole stack in Docker: `docker compose up --build` (API + Neo4j + Qdrant + Redis).

## Deploy (one-click flash deployment)

The app ships as a single FastAPI service (SPA + API in one container) and binds to `$PORT`, so it
drops onto any cloud host. Every provider key is **optional** — with none set it still runs fully on
local fallbacks. Set `JWT_SECRET` (and `ADMIN_PASSWORD`) for any public deployment.

| Platform | How | Notes |
|---|---|---|
| **Render** | New → Blueprint → pick this repo (`render.yaml`) | Free plan, Docker, auto-deploy on push; `JWT_SECRET` auto-generated. |
| **Railway** | New Project → Deploy from repo (`Procfile`) | Runs `release: ingest_seed` then `web: uvicorn`. |
| **Fly.io** | `fly launch --no-deploy && fly deploy` (`fly.toml`) | `fly secrets set ANTHROPIC_API_KEY=… JWT_SECRET=…`. |
| **Any Docker host** | `docker build -t kg-legal . && docker run -p 8000:8000 -e PORT=8000 kg-legal` | Self-host / VPS / Cloud Run / ECS. |

Set provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `NEO4J_URI`/`NEO4J_PASSWORD`, `QDRANT_URL`/
`QDRANT_API_KEY`, `COHERE_API_KEY`, `REDIS_URL`) in the platform's dashboard/secrets to upgrade each
layer to its real provider. Health: `GET /health`; readiness + active providers: `GET /ready`.

> SQLite (`data/app.db`) is ephemeral on free/stateless hosts — attach a persistent disk/volume at
> `/app/data`, or set `DATABASE_URL` to managed Postgres, to retain users & history across deploys.

## Product features

**Core research**
- Streaming multi-agent IRAC answers with live agent-trace, verified citations, confidence, and an
  interactive knowledge-graph of the nodes traversed.
- Conversation history & saved research (per user).

**Differentiator suite** (`/api/v1/features/*`)
| Feature | Endpoint | PRD |
|---|---|---|
| Legal Contradiction Detector | `POST /features/contradiction` | §7.1 |
| Temporal Legal Timeline (law-as-of-date) | `POST /features/timeline` | §7.2 |
| Case Outcome Predictor (precedent strength) | `POST /features/outcome` | §7.3 |
| Clause Risk Scorer | `POST /features/clause-risk` | §4.2 |
| Jurisdiction Mapper | `POST /features/jurisdiction` | §4.2 |
| Smart Contract Drafter | `POST /features/draft` | §4.2 |
| Hindi Legal Query Bridge | `POST /features/hindi` | §7.4 |

**Platform**
- Auth (JWT + API keys), subscription tiers (free/pro/enterprise) with daily quotas, billing stub.
- Admin analytics: query volume, p50/p95 latency, confidence & hallucination distribution, cache-hit
  rate, live golden-set eval (`/api/v1/admin/metrics`, `/admin/eval`).
- Hardening: structured JSON logs, request-ids, rate limiting, response caching, security headers,
  global exception handling, `/health` + `/ready` probes.

## Configuration
Copy `.env.example` → `.env`. Everything is optional; fill only the layers you want live. The active
providers print at startup and are reported by `GET /ready`.

## Project layout
```
app/
  agents/      7-node LangGraph pipeline + LLM provider
  kg/          graph stores (Neo4j / NetworkX), builder, NL→Cypher
  retrieval/   embeddings, vector store, BM25, RRF + rerank, indexer
  features/    contradiction · temporal · outcome · clause_risk · jurisdiction · drafter · hindi
  db/          SQLModel models, engine, repositories
  auth/        security (JWT/pw/api-key), deps, tiers
  core/        logging · middleware · cache · ratelimit · observability
  billing/     tier/quota checkout stub
  api/         main app + routers (auth, chat, features, admin, billing)
  web/         premium single-file SPA (index.html + assets/)
  eval/        golden dataset + metrics
ui/            Streamlit demo
scripts/       ingest_seed.py
tests/         parser · retrieval · pipeline · auth · features · api_v1 · cache/ratelimit
Dockerfile · docker-compose.yml · Makefile · .github/workflows/ci.yml
```

## Scope boundaries (follow-ups)
- Billing is a tier/quota + invoice **stub** (no live payment processor).
- Bulk 40k-case ingestion / IndianKanoon crawl (seed + drop-in PDFs only).
- Org multi-tenancy beyond user+admin+tier; production secrets management / TLS (deploy-time).

## Disclaimer
For research and educational use. Seed legal texts are paraphrased summaries, **not** verbatim
statutory text. Outputs are **not legal advice**.
