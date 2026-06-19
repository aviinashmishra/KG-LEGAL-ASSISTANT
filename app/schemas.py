"""Pydantic / typed schemas shared across the pipeline.

These are the data contracts between agents (PRD §6.1) and the public API.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

Confidence = Literal["HIGH", "MEDIUM", "LOW"]
Intent = Literal["research", "drafting", "compliance", "strategy"]


# --------------------------------------------------------------------------- #
# Knowledge-graph + retrieval primitives
# --------------------------------------------------------------------------- #
class GraphNode(BaseModel):
    """A node retrieved from the knowledge graph (Neo4j or NetworkX)."""

    node_id: str
    labels: List[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.properties.get("title") or self.properties.get("name") or self.node_id)

    def as_text(self) -> str:
        p = self.properties
        bits = [self.title]
        for key in ("number", "act", "year", "court", "text", "definition", "outcome"):
            if p.get(key):
                bits.append(f"{key}: {p[key]}")
        return " | ".join(str(b) for b in bits)


class Document(BaseModel):
    """A retrieved text chunk (vector / BM25 path)."""

    doc_id: str
    text: str
    source_node_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0


class RankedChunk(BaseModel):
    """A fused, reranked context chunk handed to the reasoner."""

    doc_id: str
    text: str
    source_node_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    origin: List[str] = Field(default_factory=list)  # which paths produced it: kg/dense/bm25


# --------------------------------------------------------------------------- #
# IRAC reasoning + citations (PRD §4.1, Appendix A)
# --------------------------------------------------------------------------- #
class Rule(BaseModel):
    section: Optional[str] = None
    act: Optional[str] = None
    case: Optional[str] = None
    year: Optional[int] = None
    court: Optional[str] = None
    text: str = ""
    kg_node: Optional[str] = None
    confidence: Confidence = "MEDIUM"


class IRACSchema(BaseModel):
    issue: str
    applicable_rules: List[Rule] = Field(default_factory=list)
    application: str = ""
    conclusion: str = ""
    confidence: Confidence = "MEDIUM"
    hallucination_score: float = 0.0
    kg_nodes_traversed: List[str] = Field(default_factory=list)


class Citation(BaseModel):
    kg_node: Optional[str] = None
    display: str                       # e.g. "(Section 302, Indian Penal Code, 1860)"
    verified: bool = False
    confidence: Confidence = "LOW"


# --------------------------------------------------------------------------- #
# LangGraph pipeline state (PRD §6.1)
# --------------------------------------------------------------------------- #
class LegalAgentState(TypedDict, total=False):
    original_query: str
    language: str                       # "en" | "hi"
    intent: Intent
    sub_questions: List[str]
    kg_results: List[GraphNode]
    vector_results: List[Document]
    fused_context: List[RankedChunk]
    irac_output: IRACSchema
    verified_citations: List[Citation]
    hallucination_score: float
    rewrite_count: int
    final_answer: str
    confidence: Confidence
    trace: List[str]                    # human-readable progress log (streamed to UI)


# --------------------------------------------------------------------------- #
# Public API request/response
# --------------------------------------------------------------------------- #
class QueryRequest(BaseModel):
    query: str
    language: str = "en"


class QueryResponse(BaseModel):
    answer: str
    confidence: Confidence
    irac: Optional[IRACSchema] = None
    citations: List[Citation] = Field(default_factory=list)
    hallucination_score: float = 0.0
    kg_nodes_traversed: List[str] = Field(default_factory=list)
    trace: List[str] = Field(default_factory=list)
    conversation_id: Optional[int] = None
    cache_hit: bool = False


# --------------------------------------------------------------------------- #
# Auth / account
# --------------------------------------------------------------------------- #
class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tier: str
    is_admin: bool = False


class AccountResponse(BaseModel):
    email: str
    full_name: str = ""
    tier: str
    is_admin: bool = False
    usage_today: int = 0
    daily_quota: int = 0


# --------------------------------------------------------------------------- #
# Feature request models (PRD §7 / §4.2)
# --------------------------------------------------------------------------- #
class ContradictionRequest(BaseModel):
    document_a: str
    document_b: str = ""


class TimelineRequest(BaseModel):
    section_number: str
    as_of_date: Optional[str] = None


class OutcomeRequest(BaseModel):
    facts: str
    offence_section: Optional[str] = None
    desired_outcome: Optional[str] = None


class ClauseRiskRequest(BaseModel):
    contract_text: str


class JurisdictionRequest(BaseModel):
    query: str


class DraftRequest(BaseModel):
    contract_type: str
    parties: List[str] = Field(default_factory=list)
    key_terms: str = ""


class HindiRequest(BaseModel):
    query_hi: str
