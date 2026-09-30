"""Provider-neutral, bounded RAG and citation validation for repository chat."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .analyzer import _safe_files

load_dotenv()

MAX_CONTEXT_CHARS = 10_000
INSUFFICIENT_EVIDENCE_ANSWER = (
    "Insufficient evidence in the retrieved repository files. "
    "Try naming a file, function, or technology to focus the search."
)
MAX_CONTEXT_CHARS = 10_000
MAX_CHUNKS = 8
SENSITIVE_NAMES = {".env", ".env.local", "id_rsa", "id_ed25519"}
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".cs",
    ".kt",
    ".sql",
    ".md",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
    ".json",
}


@dataclass
class ProviderResult:
    body: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None


def retrieve(root: Path, query: str) -> list[dict]:
    """Return a small set of lexical chunks; secret-like paths are never indexed."""
    terms = {
        term
        for term in re.findall(r"[a-zA-Z_][a-zA-Z0-9_.-]{2,}", query.lower())
        if term not in {"the", "and", "for", "with", "from", "what", "how", "does"}
    }
    if not terms:
        return []
    files, _ = _safe_files(root)
    ranked: list[tuple[int, str, dict]] = []
    total_chars = 0
    for path in files:
        rel = path.relative_to(root).as_posix()
        lower_name = path.name.lower()
        if (
            path.suffix.lower() not in SOURCE_EXTENSIONS
            or lower_name in SENSITIVE_NAMES
            or lower_name.startswith(".env")
            or any(
                word in lower_name for word in ("secret", "credential", "private-key")
            )
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        # Do not index obvious private key or credential files even when misnamed.
        if (
            "-----BEGIN PRIVATE KEY-----" in text
            or "-----BEGIN RSA PRIVATE KEY-----" in text
        ):
            continue
        lines = text.splitlines()
        scores = [sum(line.lower().count(term) for term in terms) for line in lines]
        best = max(scores, default=0)
        if best == 0:
            continue
        line_index = scores.index(best)
        start = max(0, line_index - 4)
        end = min(len(lines), line_index + 5)
        excerpt = "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))[:1800]
        chunk = {
            "file": rel,
            "start_line": start + 1,
            "end_line": end,
            "excerpt": excerpt,
        }
        ranked.append((best, rel, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    for _, _, chunk in ranked:
        size = len(chunk["excerpt"])
        if len(selected) >= MAX_CHUNKS or total_chars + size > MAX_CONTEXT_CHARS:
            continue
        selected.append(chunk)
        total_chars += size
    return selected


async def generate(
    system: str, prompt: str, *, max_output_tokens: int = 1200
) -> ProviderResult:
    model = os.getenv("AI_MODEL", "gemini-3.8-flash")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    started = time.monotonic()
    timeout = httpx.Timeout(25.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0.1,
                        "maxOutputTokens": max_output_tokens,
                    },
                },
            )
            if response.status_code != 503 or attempt == 1:
                break
            await asyncio.sleep(0.75)
        response.raise_for_status()
        data = response.json()
        body = "".join(
            part.get("text", "") for part in data["candidates"][0]["content"]["parts"]
        )
        usage = data.get("usageMetadata", {})
        return ProviderResult(
            body=body,
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            prompt_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )


def validate_claims(body: str, chunks: list[dict]) -> dict:
    """Reject claims with absent or un-retrieved citations before returning them."""
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {"answer": INSUFFICIENT_EVIDENCE_ANSWER, "claims": []}
    verified = []
    for claim in parsed.get("claims", [])[:20]:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim"), str):
            continue
        references = claim.get("evidence", [])
        matches = []
        for reference in references:
            if not isinstance(reference, dict) or not isinstance(
                reference.get("file"), str
            ):
                continue
            try:
                start_line = int(reference.get("start_line"))
                end_line = int(reference.get("end_line"))
            except (TypeError, ValueError):
                continue
            if start_line < 1 or end_line < start_line:
                continue
            source = next(
                (
                    chunk
                    for chunk in chunks
                    if reference["file"] == chunk["file"]
                    and chunk["start_line"] <= start_line
                    and end_line <= chunk["end_line"]
                ),
                None,
            )
            if source:
                matches.append(
                    {
                        "file": source["file"],
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                )
        if not matches:
            continue
        verified.append(
            {
                "claim": claim["claim"][:1000],
                "type": claim.get("type", "inference"),
                "confidence": max(0, min(1, float(claim.get("confidence", 0.5)))),
                "evidence": matches,
            }
        )
    if not verified:
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "claims": [],
        }
    return {
        "answer": " ".join(claim["claim"] for claim in verified),
        "claims": verified,
    }
