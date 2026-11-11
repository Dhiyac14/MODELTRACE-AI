"""Deterministic checks on source references returned by the LLM.

A reference is kept only if its quote is really in the cited file. If the quote is found at
other lines, the line numbers are corrected. A fact marked "verified" with no surviving
reference is downgraded to "inferred".
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from llm.schemas import Fact, SourceRef

Sources = dict[str, list[str]]  # display name -> file lines


def load_sources(paths: list[str | Path]) -> Sources:
    """Read files keyed by the path as given (use repository-relative paths)."""
    return {Path(p).as_posix(): Path(p).read_text(encoding="utf-8").splitlines() for p in paths}


def render_listing(sources: Sources) -> str:
    """Number every line so the LLM can cite it."""
    blocks = []
    for name, lines in sources.items():
        width = len(str(len(lines)))
        body = "\n".join(f"{i:>{width}}| {line}" for i, line in enumerate(lines, start=1))
        blocks.append(f"=== FILE: {name} ===\n{body}")
    return "\n\n".join(blocks)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _resolve(name: str, sources: Sources) -> str | None:
    if name in sources:
        return name
    matches = [key for key in sources if PurePosixPath(key).name == PurePosixPath(name).name]
    return matches[0] if len(matches) == 1 else None


def verify_ref(ref: SourceRef, sources: Sources) -> SourceRef | None:
    """Return the reference with ``verified=True`` (line numbers corrected if needed), or None."""
    name = _resolve(ref.file, sources)
    quote = _norm(ref.quote)
    if name is None or not quote:
        return None
    lines = sources[name]
    if 1 <= ref.line_start <= ref.line_end <= len(lines) and quote in _norm(" ".join(lines[ref.line_start - 1 : ref.line_end])):
        return ref.model_copy(update={"file": name, "verified": True})
    span = ref.quote.count("\n") + 1
    for width in (span, span + 1):
        for start in range(len(lines) - width + 1):
            if quote in _norm(" ".join(lines[start : start + width])):
                return ref.model_copy(
                    update={"file": name, "line_start": start + 1, "line_end": start + width, "verified": True}
                )
    return None


def verify_refs(refs: list[SourceRef], sources: Sources, label: str, warnings: list[str]) -> list[SourceRef]:
    kept = [checked for checked in (verify_ref(r, sources) for r in refs) if checked is not None]
    if len(kept) < len(refs):
        warnings.append(f"{label}: {len(refs) - len(kept)} source reference(s) not found in the cited file and removed.")
    return kept


def verify_fact(fact: Fact, sources: Sources, label: str, warnings: list[str]) -> Fact:
    evidence = verify_refs(fact.evidence, sources, label, warnings)
    update: dict = {"evidence": evidence}
    if fact.status == "verified" and not evidence:
        update["status"] = "inferred"
        update["note"] = f"{fact.note} Downgraded from verified: no source reference could be checked.".strip()
        warnings.append(f"{label}: downgraded from verified to inferred.")
    return fact.model_copy(update=update)


def verify_facts(model: BaseModel, sources: Sources) -> tuple[BaseModel, list[str]]:
    """Verify every ``Fact`` and ``list[Fact]`` field of a model. Returns the checked copy and warnings."""
    warnings: list[str] = []
    update: dict = {}
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, Fact):
            update[name] = verify_fact(value, sources, name, warnings)
        elif isinstance(value, list) and value and all(isinstance(v, Fact) for v in value):
            update[name] = [verify_fact(v, sources, f"{name}[{i}]", warnings) for i, v in enumerate(value)]
    return model.model_copy(update=update), warnings
