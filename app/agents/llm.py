"""LLM provider abstraction.

`get_llm()` returns an Anthropic-backed client when ANTHROPIC_API_KEY is set,
otherwise a deterministic StubLLM that produces structured, citation-aware output
from the retrieved context so the whole pipeline runs offline.
"""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from app.config import get_settings
from app.schemas import IRACSchema, RankedChunk, Rule


class BaseLLM:
    is_real: bool = False

    def complete(self, prompt: str, max_tokens: int = 1024, fast: bool = False) -> str:
        raise NotImplementedError

    def reason_irac(self, query: str, context: List[RankedChunk]) -> IRACSchema:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Real provider
# --------------------------------------------------------------------------- #
class AnthropicLLM(BaseLLM):
    is_real = True

    def __init__(self) -> None:
        import anthropic

        s = get_settings()
        self._client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        self._model = s.anthropic_model
        self._fast_model = s.anthropic_fast_model

    def complete(self, prompt: str, max_tokens: int = 1024, fast: bool = False) -> str:
        msg = self._client.messages.create(
            model=self._fast_model if fast else self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    def reason_irac(self, query: str, context: List[RankedChunk]) -> IRACSchema:
        ctx = _format_context(context)
        prompt = _IRAC_PROMPT.format(query=query, context=ctx)
        raw = self.complete(prompt, max_tokens=2000)
        data = _safe_json(raw)
        if data:
            try:
                return IRACSchema(**_coerce_irac(data))
            except Exception:
                pass
        # if the model didn't return clean JSON, degrade to stub assembly
        return StubLLM().reason_irac(query, context)


# --------------------------------------------------------------------------- #
# Deterministic fallback
# --------------------------------------------------------------------------- #
class StubLLM(BaseLLM):
    is_real = False

    def complete(self, prompt: str, max_tokens: int = 1024, fast: bool = False) -> str:
        # used only by optional LLM-only paths (extraction/cypher); safe no-op
        return ""

    def reason_irac(self, query: str, context: List[RankedChunk]) -> IRACSchema:
        """Build a grounded IRAC answer purely from retrieved context.

        Every rule is tied to a real source node id, so citation verification
        succeeds and the answer is genuinely grounded even without an LLM.
        """
        rules: List[Rule] = []
        nodes: List[str] = []
        for ch in context[:5]:
            meta = ch.metadata
            node_id = ch.source_node_id
            if node_id:
                nodes.append(node_id)
            labels = meta.get("labels", [])
            if "Case" in labels:
                rules.append(
                    Rule(
                        case=meta.get("title"),
                        year=_safe_int(meta.get("year")),
                        court=meta.get("court"),
                        text=_first_sentence(ch.text),
                        kg_node=node_id,
                        confidence="HIGH" if node_id else "LOW",
                    )
                )
            else:
                rules.append(
                    Rule(
                        section=meta.get("number"),
                        act=meta.get("act") or meta.get("act_title"),
                        text=_first_sentence(ch.text),
                        kg_node=node_id,
                        confidence="HIGH" if node_id else "LOW",
                    )
                )

        application = " ".join(_first_sentence(ch.text) for ch in context[:3]) or (
            "No directly applicable provisions were retrieved for this query."
        )
        top = context[0] if context else None
        conclusion = (
            f"Based on {_describe(top)}, {_first_sentence(top.text)}"
            if top
            else "Insufficient grounded context to reach a conclusion."
        )
        confidence = "HIGH" if any(r.kg_node for r in rules) else "LOW"
        return IRACSchema(
            issue=query.strip().rstrip("?") + "?",
            applicable_rules=rules,
            application=application,
            conclusion=conclusion,
            confidence=confidence,
            hallucination_score=0.0,
            kg_nodes_traversed=_dedup(nodes),
        )


_IRAC_PROMPT = """You are an Indian legal reasoning engine. Apply the IRAC framework
(Issue, Rule, Application, Conclusion) to the user's question using ONLY the retrieved context.
Every rule MUST include the `kg_node` id of the source chunk it came from. Never invent section
numbers or case names. Output STRICT JSON only with this schema:
{{
  "issue": str,
  "applicable_rules": [{{"section": str|null, "act": str|null, "case": str|null, "year": int|null,
                         "court": str|null, "text": str, "kg_node": str|null,
                         "confidence": "HIGH"|"MEDIUM"|"LOW"}}],
  "application": str,
  "conclusion": str,
  "confidence": "HIGH"|"MEDIUM"|"LOW"
}}

QUESTION: {query}

RETRIEVED CONTEXT (each chunk shows its kg_node id):
{context}
"""


def _format_context(context: List[RankedChunk]) -> str:
    lines = []
    for ch in context:
        lines.append(f"[kg_node={ch.source_node_id}] {ch.text}")
    return "\n\n".join(lines) if lines else "(no context retrieved)"


# ---- helpers ----
def _safe_json(raw: str) -> Optional[dict[str, Any]]:
    raw = raw.strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(raw[s : e + 1])
    except json.JSONDecodeError:
        return None


def _coerce_irac(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("applicable_rules", [])
    for r in data["applicable_rules"]:
        if isinstance(r.get("year"), str) and r["year"].isdigit():
            r["year"] = int(r["year"])
    return data


def _first_sentence(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    m = re.search(r"^(.*?[.])(\s|$)", text)
    return (m.group(1) if m else text)[:400]


def _describe(chunk: Optional[RankedChunk]) -> str:
    if not chunk:
        return "the retrieved context"
    meta = chunk.metadata
    if meta.get("number"):
        return f"Section {meta['number']} {meta.get('act') or ''}".strip()
    if meta.get("title"):
        return meta["title"]
    return chunk.source_node_id or "the retrieved context"


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _dedup(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


_LLM: Optional[BaseLLM] = None


def get_llm(force_new: bool = False) -> BaseLLM:
    global _LLM
    if _LLM is not None and not force_new:
        return _LLM
    settings = get_settings()
    if settings.use_anthropic:
        try:
            _LLM = AnthropicLLM()
            return _LLM
        except Exception as exc:  # pragma: no cover
            print(f"[llm] Anthropic init failed ({exc}); using stub LLM.")
    _LLM = StubLLM()
    return _LLM
