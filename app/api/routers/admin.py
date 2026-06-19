"""Admin analytics router (PRD §8.3 custom dashboard)."""
from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, require_admin
from app.db import repo


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = min(len(s) - 1, int(round(pct * (len(s) - 1))))
    return s[idx]


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/metrics")
def metrics(_: Principal = Depends(require_admin)) -> dict:
    logs = repo.recent_query_logs(limit=5000)
    latencies = [l.latency_ms for l in logs]
    confidence = Counter(l.confidence for l in logs if l.confidence)
    cache_hits = sum(1 for l in logs if l.cache_hit)
    by_day: dict[str, int] = defaultdict(int)
    for l in logs:
        by_day[l.created_at.strftime("%Y-%m-%d")] += 1

    halluc = [l.hallucination_score for l in logs]
    return {
        "total_queries": len(logs),
        "latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else 0,
        },
        "confidence_distribution": dict(confidence),
        "avg_hallucination_score": round(sum(halluc) / len(halluc), 3) if halluc else 0.0,
        "cache_hit_rate": round(cache_hits / len(logs), 3) if logs else 0.0,
        "queries_by_day": dict(sorted(by_day.items())),
    }


@router.get("/eval")
def eval_scores(_: Principal = Depends(require_admin)) -> dict:
    from app.eval.ragas_eval import evaluate

    return evaluate()["summary"]
