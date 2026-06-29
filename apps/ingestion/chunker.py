from __future__ import annotations

import re

SHORT_THRESH = 80    # approx tokens — merge with neighbours
LONG_THRESH = 400    # approx tokens — split at semantic boundaries
OVERLAP_WORDS = 38   # ≈ 50 tokens carried into the next split chunk

# Split text at the start of a numbered definition: "1. Capital", "16. Grace Period"
# Negative lookbehind prevents false matches on decimals like "3.14"
_NUMBERED_DEF = re.compile(r"(?<!\d)(?=\d+\.\s+[A-Z])")

# Split at part/clause markers: "PART-B", "PART C", "1.1(a)", "Appendix I–"
_CLAUSE_MARKER = re.compile(
    r"(?=PART[\s\-][A-Z]|(?:\d+\.){2,}\([a-z]\)|Appendix\s+[IVX])",
    re.IGNORECASE,
)


def _approx_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def _apply_overlap(parts: list[str]) -> list[str]:
    out = []
    for i, part in enumerate(parts):
        if i > 0:
            tail = " ".join(parts[i - 1].split()[-OVERLAP_WORDS:])
            part = (tail + " " + part).strip()
        out.append(part)
    return out


def _split_long_text(text: str) -> list[str]:
    """Split a long text block at semantic boundaries (priority order)."""
    for pattern in (_NUMBERED_DEF, _CLAUSE_MARKER):
        parts = [p.strip() for p in pattern.split(text) if p.strip()]
        if len(parts) > 1:
            return _apply_overlap(parts)
    # Fallback: paragraph breaks
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) > 1:
        return _apply_overlap(parts)
    return [text]


def chunk_document(doc: dict) -> list[dict]:
    """
    Apply type-aware + size-aware chunking to a data_extractor JSON document.

    Returns a list of chunk dicts:
        { content: str, block_type: str, page: int, meta: dict }

    block_type is one of: "text", "table_row", "table_full"
    """
    chunks: list[dict] = []
    pending: list[tuple[dict, int]] = []  # (block, page_num) — short text blocks awaiting merge
    pending_tokens = 0

    def flush() -> None:
        nonlocal pending, pending_tokens
        if not pending:
            return
        merged = "\n\n".join(b["content"] for b, _ in pending)
        if merged.strip():
            first_block, first_page = pending[0]
            chunks.append({
                "content": merged,
                "block_type": "text",
                "page": first_page,
                "meta": {"bbox": first_block.get("bbox")},
            })
        pending.clear()
        pending_tokens = 0

    for page in doc["pages"]:
        if page.get("excluded"):
            continue
        pn = page["page"]

        for block in page["blocks"]:
            btype = block["type"]

            # ── text blocks ──────────────────────────────────────────────────
            if btype == "text":
                t = _approx_tokens(block["content"])

                if t < SHORT_THRESH:
                    pending.append((block, pn))
                    pending_tokens += t
                    # Flush once accumulated size crosses the threshold
                    if pending_tokens >= SHORT_THRESH:
                        flush()

                else:
                    flush()
                    if t <= LONG_THRESH:
                        chunks.append({
                            "content": block["content"],
                            "block_type": "text",
                            "page": pn,
                            "meta": {"bbox": block.get("bbox")},
                        })
                    else:
                        for part in _split_long_text(block["content"]):
                            chunks.append({
                                "content": part,
                                "block_type": "text",
                                "page": pn,
                                "meta": {"bbox": block.get("bbox")},
                            })

            # ── table blocks ─────────────────────────────────────────────────
            elif btype == "table":
                flush()
                headers = block.get("headers", [])
                # CI illness table → one chunk per row
                is_ci = bool(
                    headers and headers[0].strip().lower() in ("sr. no.", "sr.no.")
                )

                if is_ci:
                    for row in block.get("rows", []):
                        row_text = " | ".join(
                            f"{h}: {v}"
                            for h, v in zip(headers, row)
                            if h.strip() and v.strip()
                        )
                        if row_text.strip():
                            chunks.append({
                                "content": row_text,
                                "block_type": "table_row",
                                "page": pn,
                                "meta": {
                                    "table_index": block.get("table_index"),
                                    "is_continuation": block.get("is_continuation", False),
                                    "continued_from_page": block.get("continued_from_page"),
                                },
                            })
                else:
                    # GSV / SSV / numeric / lookup table → entire table as one chunk
                    raw = block.get("raw_text", "").strip()
                    if raw:
                        chunks.append({
                            "content": raw,
                            "block_type": "table_full",
                            "page": pn,
                            "meta": {
                                "table_index": block.get("table_index"),
                                "is_continuation": block.get("is_continuation", False),
                                "continued_from_page": block.get("continued_from_page"),
                                "headers": headers,
                            },
                        })

    flush()  # emit any remaining short blocks at end of document
    return chunks
