"""Section-aware legal document parser (PRD §4.1 "Smart Legal PDF Parser").

Preserves the Indian legal hierarchy:  Act -> Section -> Sub-clause -> Proviso.

Text extraction prefers IBM Docling if installed, then pdfminer.six, then a plain
read for `.txt`. The structural splitter is pure-Python regex so it always runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---- regex patterns for Indian legal structure ----
# "1." / "302." / "66A." / "Section 302." style section headers
SECTION_RE = re.compile(
    r"^\s*(?:Section\s+)?(?P<num>\d+[A-Z]?)\.\s+(?P<title>[^\n]+)",
    re.IGNORECASE,
)
# Sub-clauses: "(1)", "(a)", "(i)" — Arabic, alpha, and Roman numerals
SUBCLAUSE_RE = re.compile(r"^\s*\((?P<label>[0-9]+|[a-z]+|[ivxlcdm]+)\)\s+(?P<text>.+)", re.IGNORECASE)
# Provisos and explanations are first-class in Indian drafting
PROVISO_RE = re.compile(r"^\s*Provided\s+(?:further\s+|also\s+)?that\b", re.IGNORECASE)
EXPLANATION_RE = re.compile(r"^\s*Explanation\s*[\.\-:]?", re.IGNORECASE)
EXCEPTION_RE = re.compile(r"^\s*Exception\s*\d*\s*[\.\-:]?", re.IGNORECASE)


@dataclass
class SubClause:
    label: str
    text: str
    kind: str = "subclause"  # subclause | proviso | explanation | exception


@dataclass
class ParsedSection:
    number: str
    title: str
    text: str = ""
    subclauses: List[SubClause] = field(default_factory=list)
    provisos: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)

    def full_text(self) -> str:
        parts = [f"Section {self.number}. {self.title}", self.text]
        for sc in self.subclauses:
            parts.append(f"({sc.label}) {sc.text}")
        for p in self.provisos:
            parts.append(p)
        for e in self.explanations:
            parts.append(e)
        return "\n".join(x for x in parts if x).strip()


@dataclass
class ParsedDocument:
    source: str
    title: str
    sections: List[ParsedSection] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Text extraction
# --------------------------------------------------------------------------- #
def extract_text(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        # 1) Try Docling (richest structure)
        try:
            from docling.document_converter import DocumentConverter  # type: ignore

            conv = DocumentConverter()
            result = conv.convert(str(path))
            return result.document.export_to_markdown()
        except Exception:
            pass
        # 2) Fall back to pdfminer.six
        try:
            from pdfminer.high_level import extract_text as pdfminer_extract  # type: ignore

            return pdfminer_extract(str(path))
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Could not extract text from {path}. Install docling or pdfminer.six."
            ) from exc

    raise ValueError(f"Unsupported file type: {suffix}")


# --------------------------------------------------------------------------- #
# Structural splitting
# --------------------------------------------------------------------------- #
def split_sections(text: str, title: str = "Untitled", source: str = "") -> ParsedDocument:
    """Split raw legal text into a Section -> Sub-clause -> Proviso hierarchy."""
    doc = ParsedDocument(source=source, title=title)
    current: Optional[ParsedSection] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        sec_match = SECTION_RE.match(line)
        if sec_match:
            if current:
                doc.sections.append(current)
            current = ParsedSection(
                number=sec_match.group("num"),
                title=sec_match.group("title").strip(),
            )
            continue

        if current is None:
            continue  # preamble before first section

        if PROVISO_RE.match(line):
            current.provisos.append(line.strip())
            continue
        if EXPLANATION_RE.match(line) or EXCEPTION_RE.match(line):
            current.explanations.append(line.strip())
            continue

        sub_match = SUBCLAUSE_RE.match(line)
        if sub_match:
            current.subclauses.append(
                SubClause(label=sub_match.group("label"), text=sub_match.group("text").strip())
            )
            continue

        # plain continuation line -> body text
        current.text = (current.text + " " + line.strip()).strip()

    if current:
        doc.sections.append(current)
    return doc


def parse_file(path: str | Path, title: Optional[str] = None) -> ParsedDocument:
    path = Path(path)
    text = extract_text(path)
    return split_sections(text, title=title or path.stem, source=str(path))
