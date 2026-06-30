"""
Hybrid PDF Extractor — JSON output
====================================
Stores extracted content as structured JSON.
Each page is a dict with separate text blocks and table objects.
This is the correct pre-chunking format for RAG pipelines.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz
import pdfplumber
from fastapi import HTTPException
from google.cloud import storage
from sqlalchemy.orm import Session
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

from apps.auth.repository import AuthRepository
from apps.core.config import settings
from apps.core.global_utils import logOperation
from apps.core.ai_models import get_embed_model
from apps.core.database import SessionLocal
from .chunker import chunk_document
from .models import Chunk, Ingestion
from .repository import IngestionRepository
from .schemas import IngestionStatus

logger = logging.getLogger(__name__)

# Pages to skip (1-indexed)
EXCLUDE_PAGES: set[int] = {2}

TWO_COLUMN_RATIO_THRESHOLD   = 0.25
CONTINUATION_NUMERIC_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Helpers (same as before)
# ---------------------------------------------------------------------------

def _is_numeric_cell(val: str) -> bool:
    v = (val or "").strip().replace(",", "").replace("%", "").replace("-", "")
    if v in ("NA", "na", "N/A", ""):
        return True
    try:
        float(v)
        return True
    except ValueError:
        return False


def _looks_like_continuation(table, prev_col_count: int) -> bool:
    if not table or len(table[0]) != prev_col_count:
        return False
    first_row = [str(c) if c else "" for c in table[0]]
    ratio = sum(_is_numeric_cell(c) for c in first_row) / len(first_row)
    return ratio >= CONTINUATION_NUMERIC_THRESHOLD


def _is_two_column_page(fitz_page: fitz.Page) -> bool:
    pw = fitz_page.rect.width
    blocks = fitz_page.get_text("blocks", sort=True)
    text_blocks = [b for b in blocks if b[6] == 0 and str(b[4]).strip()]
    if not text_blocks:
        return False
    right = sum(1 for b in text_blocks if b[0] > pw * 0.45)
    return (right / len(text_blocks)) >= TWO_COLUMN_RATIO_THRESHOLD


def _block_in_table(x0, y0, x1, y1, table_bboxes) -> bool:
    for tb in table_bboxes:
        tb_x0, tb_top, tb_x1, tb_bottom = tb
        if x0 < tb_x1 and x1 > tb_x0 and y0 < tb_bottom and y1 > tb_top:
            return True
    return False


def _clean_text_block(text: str) -> str:
    """
    Fix word-per-line issue: if a block has many very short lines
    (avg < 20 chars), it's a fragmented block — rejoin as a paragraph.
    Also strips stray single-char lines (watermarks, artifacts).
    """
    lines = text.strip().splitlines()

    # Remove stray single/double char lines (watermarks like 'v', 'vc')
    lines = [l for l in lines if len(l.strip()) != 1 or l.strip() == ""]

    if not lines:
        return ""

    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return ""

    avg_len = sum(len(l.strip()) for l in non_empty) / len(non_empty)

    # If avg line is very short → fragmented block, rejoin
    if avg_len < 25 and len(non_empty) > 3:
        rejoined = " ".join(l.strip() for l in non_empty if l.strip())
        # Collapse multiple spaces
        rejoined = re.sub(r" {2,}", " ", rejoined)
        return rejoined

    # Otherwise normalise trailing whitespace per line
    return "\n".join(l.rstrip() for l in lines)


def _extract_text_blocks(fitz_page: fitz.Page, table_bboxes: list,
                          two_col: bool) -> list[dict]:
    """
    Returns a list of text block dicts:
      { "type": "text", "content": "...", "bbox": [x0,y0,x1,y1] }
    """
    pw = fitz_page.rect.width
    ph = fitz_page.rect.height

    if two_col:
        clips = [
            fitz.Rect(0,       0, pw * 0.5, ph),
            fitz.Rect(pw * 0.5, 0, pw,      ph),
        ]
    else:
        clips = [fitz.Rect(0, 0, pw, ph)]

    blocks_out = []
    for clip in clips:
        blocks = fitz_page.get_text("blocks", clip=clip, sort=True)
        for block in blocks:
            x0, y0, x1, y1, text, *_ = block
            if block[6] != 0:
                continue
            if _block_in_table(x0, y0, x1, y1, table_bboxes):
                continue
            text = _clean_text_block(text)
            if text:
                blocks_out.append({
                    "type": "text",
                    "content": text,
                    "bbox": [round(x0, 1), round(y0, 1),
                              round(x1, 1), round(y1, 1)],
                })
    return blocks_out


def _table_to_dict(table: list, is_continuation: bool,
                   continued_from_page: Optional[int],
                   table_index: int, page_num: int) -> dict:
    """
    Convert pdfplumber table to a structured dict:
    {
      "type": "table",
      "is_continuation": bool,
      "continued_from_page": int | null,
      "headers": [...],
      "rows": [[...], ...],
      "raw_text": "flattened text for embedding"
    }
    """
    def clean(cell) -> str:
        return str(cell).replace("\n", " ").strip() if cell is not None else ""

    rows = [[clean(c) for c in row] for row in table if any(c for c in row)]
    if not rows:
        return {}

    col_count = max(len(r) for r in rows)
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    # Heuristic: if first row looks like headers (not all numeric), use it
    first = rows[0]
    if not all(_is_numeric_cell(c) for c in first):
        headers = first
        data_rows = rows[1:]
    else:
        headers = [f"col_{i}" for i in range(col_count)]
        data_rows = rows

    # Flatten to plain text for embedding
    raw_lines = []
    if headers[0] != "col_0":
        raw_lines.append(" | ".join(headers))
    for row in data_rows:
        raw_lines.append(" | ".join(row))
    raw_text = "\n".join(raw_lines)

    return {
        "type": "table",
        "table_index": table_index,
        "page": page_num,
        "is_continuation": is_continuation,
        "continued_from_page": continued_from_page if is_continuation else None,
        "headers": headers,
        "rows": data_rows,
        "raw_text": raw_text,
    }


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def data_extractor(file_path: str, output_dir: str = ".") -> Path:
    """
    Extract PDF to structured JSON.

    Output schema:
    {
      "source": "filename.pdf",
      "total_pages": N,
      "excluded_pages": [...],
      "pages": [
        {
          "page": 1,
          "excluded": false,
          "two_column": false,
          "blocks": [
            { "type": "text", "content": "...", "bbox": [...] },
            { "type": "table", "headers": [...], "rows": [[...]], "raw_text": "..." },
            ...
          ]
        },
        ...
      ]
    }
    """
    if not file_path.endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (Path(file_path).stem + ".json")

    fitz_doc   = fitz.open(file_path)
    total_pages = len(fitz_doc)

    document = {
        "source": Path(file_path).name,
        "total_pages": total_pages,
        "excluded_pages": sorted(EXCLUDE_PAGES),
        "pages": [],
    }

    prev_last_col_count: Optional[int] = None
    prev_last_page: int = 0

    with pdfplumber.open(file_path) as pdf_doc:
        for page_num in range(1, total_pages + 1):

            if page_num in EXCLUDE_PAGES:
                document["pages"].append({
                    "page": page_num,
                    "excluded": True,
                    "reason": "Template placeholder page — info duplicated on other pages",
                    "blocks": [],
                })
                prev_last_col_count = None
                continue

            fitz_page   = fitz_doc[page_num - 1]
            plumb_page  = pdf_doc.pages[page_num - 1]

            found_tables = plumb_page.find_tables()
            raw_tables   = plumb_page.extract_tables()
            table_bboxes = [ft.bbox for ft in found_tables]

            two_col = _is_two_column_page(fitz_page)

            # Text blocks first (Fix 4)
            text_blocks = _extract_text_blocks(fitz_page, table_bboxes, two_col)

            # Table blocks
            table_blocks = []
            this_page_last_col_count = None

            for i, table in enumerate(raw_tables):
                if not table:
                    continue
                col_count = len(table[0]) if table else 0
                is_cont = (
                    prev_last_col_count is not None
                    and _looks_like_continuation(table, prev_last_col_count)
                )
                tdict = _table_to_dict(
                    table, is_cont, prev_last_page if is_cont else None,
                    table_index=i, page_num=page_num
                )
                if tdict:
                    table_blocks.append(tdict)
                this_page_last_col_count = col_count

            prev_last_col_count = this_page_last_col_count
            prev_last_page = page_num

            document["pages"].append({
                "page": page_num,
                "excluded": False,
                "two_column": two_col,
                "blocks": text_blocks + table_blocks,
            })

    out_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return out_path

class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IngestionRepository(db)
        self._bucket = storage.Client().bucket(settings.gcs_bucket_name)
        self._embed_model: Optional[TextEmbeddingModel] = None

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _email_to_prefix(email: str) -> str:
        """rohit14101998@gmail.com  →  rohit14101998-gmail-com"""
        return email.replace("@", "-").replace(".", "-")

    def _upload_file_to_gcs(self, path: Path, key: str, content_type: str) -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_filename(str(path), content_type=content_type)
        return f"gs://{settings.gcs_bucket_name}/{key}"

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = get_embed_model(self)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), settings.embedding_batch_size):
            batch = texts[i : i + settings.embedding_batch_size]
            inputs = [
                TextEmbeddingInput(text=t, task_type="RETRIEVAL_DOCUMENT")
                for t in batch
            ]
            results = model.get_embeddings(
                inputs, output_dimensionality=settings.embedding_output_dimensionality, auto_truncate=True
            )
            vectors.extend(r.values for r in results)
        return vectors

    # ── public sync method called from the route handler ─────────────────────

    @logOperation
    def create_ingestion_record(
        self, filename: str, user_id: str
    ) -> tuple[Ingestion, str]:
        """
        Create a pending DB record and return (record, user_email).
        Called synchronously before the 202 response is sent.
        """
        user = AuthRepository(self.db).get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        record = self.repo.create(
            user_id=user.id,
            file_name=filename,
            file_url="",
            status=IngestionStatus.PENDING,
        )
        return record, user.email
    
    @logOperation
    def get_ingestion_record_by_id(
        self, ingestion_id: str, user_id: str
    ) -> Optional[Ingestion]:
        """
        Fetch a specific ingestion record by ID for the given user.
        Returns None if not found or not owned by the user.
        """
        record = self.repo.get_by_id(ingestion_id)
        if record and str(record.user_id) == user_id:
            return record
        return None
    
    @logOperation
    def get_latest_ingestion_record(
        self, user_id: str
    ) -> Optional[Ingestion]:
        """
        Fetch the latest ingestion record for the given user.
        Returns None if no record is found.
        """
        return self.repo.get_latest_ingestion_by_user_id(user_id)

    # ── background pipeline ───────────────────────────────────────────────────

    def _run_pipeline(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        user_email: str,
        ingestion_id: uuid.UUID,
    ) -> None:
        record = self.repo.get_by_id(ingestion_id)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        prefix = self._email_to_prefix(user_email)
        stem = Path(filename).stem # this will just fetch the filename without the .pdf extension 

        try:
            # The route handler passes the uploaded file as raw bytes (file_bytes) so
            # it can return the 202 immediately without keeping the request open.
            # However, both data_extractor (fitz/pdfplumber) and the GCS upload call
            # need an actual file path on disk — they cannot work with an in-memory
            # bytes object. TemporaryDirectory creates an isolated folder for this
            # session; everything written inside is automatically deleted when the
            # `with` block exits, even if an exception is raised mid-pipeline.
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                # Reconstruct the file on disk so path-based APIs can consume it
                pdf_path = tmp_dir / filename   # e.g. /tmp/xyz/Term-life-policy-doc-unlocked.pdf
                pdf_path.write_bytes(file_bytes)

                # 1 — Upload PDF to GCS-----------------------------------------
                pdf_key = f"{prefix}/original_uploads/{ts}_{filename}"
                file_url = self._upload_file_to_gcs(pdf_path, pdf_key, "application/pdf")
                self.repo.update(record, file_url=file_url, status=IngestionStatus.UPLOADED)

                # 2 — Extract PDF → JSON ---------------------------------------
                self.repo.update(record, status=IngestionStatus.EXTRACTING)
                json_path = data_extractor(str(pdf_path), output_dir=str(tmp_dir))
                self.repo.update(record, status=IngestionStatus.EXTRACTED)

                # 3 — Upload JSON to GCS ---------------------------------------
                json_key = f"{prefix}/converted_data/{ts}_{stem}.json"
                json_url = self._upload_file_to_gcs(json_path, json_key, "application/json")
                self.repo.update(record, json_url=json_url)

                # 4 — Chunk ----------------------------------------------------
                doc = json.loads(json_path.read_text(encoding="utf-8"))
                chunk_list = chunk_document(doc)

                # 5 — Embed + store --------------------------------------------
                self.repo.update(record, status=IngestionStatus.INDEXING)
                vectors = self._embed([c["content"] for c in chunk_list])

                # chunk_objects calculated below is a flat list of Chunk ORM objects, one per chunk, e.g.:
                # [
                #   Chunk(chunk_index=0, block_type="text",      page=1, content="Dear Rohit...",          embedding=[0.012, -0.034, ...]),
                #   Chunk(chunk_index=1, block_type="text",      page=3, content="Policy Schedule...",     embedding=[0.091,  0.004, ...]),
                #   Chunk(chunk_index=2, block_type="table_full",page=3, content="Policy No | Plan Opt..", embedding=[-0.02,  0.067, ...]),
                #   Chunk(chunk_index=3, block_type="table_row", page=10,content="Sr. No.: 1 | Cancer..", embedding=[0.043, -0.011, ...]),
                #   ...  (317 total for the sample doc)
                # ]
                chunk_objects = [
                    Chunk(
                        ingestion_id=ingestion_id,
                        user_id=uuid.UUID(user_id),
                        chunk_index=i,
                        block_type=c["block_type"],
                        page=c["page"],
                        content=c["content"],
                        embedding=v,
                        meta=c.get("meta"),
                    )
                    for i, (c, v) in enumerate(zip(chunk_list, vectors))
                ]
                self.db.add_all(chunk_objects)
                self.db.commit()

                self.repo.update(
                    record,
                    status=IngestionStatus.INDEXED,
                    chunk_count=len(chunk_objects),
                )
                self.repo.update(record, status=IngestionStatus.COMPLETED)

        except Exception as exc:
            logger.exception("Ingestion pipeline failed for %s", ingestion_id)
            self.repo.update(
                record,
                status=IngestionStatus.FAILED,
                failed_at_stage=record.status,
                error_message=str(exc)[:2000],
            )
            raise


@logOperation
def run_ingestion_pipeline(
    *,
    file_bytes: bytes,
    filename: str,
    user_id: str,
    user_email: str,
    ingestion_id: uuid.UUID,
) -> None:
    """
    Module-level entry point for FastAPI BackgroundTasks.
    Creates its own DB session so it is independent of the closed request session.
    """
    db = SessionLocal()
    try:
        IngestionService(db)._run_pipeline(
            file_bytes=file_bytes,
            filename=filename,
            user_id=user_id,
            user_email=user_email,
            ingestion_id=ingestion_id,
        )
    except Exception:
        pass  # failure already persisted to DB in _run_pipeline
    finally:
        db.close()