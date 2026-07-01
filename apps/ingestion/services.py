"""
Hybrid PDF Extractor — JSON output
====================================
Stores extracted content as structured JSON.
Each page is a dict with separate text blocks and table objects.
This is the correct pre-chunking format for RAG pipelines.
"""

from __future__ import annotations

import json
import fitz
import uuid
import tempfile
from pathlib import Path
from typing import Optional
import pdfplumber
from fastapi import HTTPException
from google.cloud import storage
from sqlalchemy.orm import Session
from io import BytesIO
from zipfile import ZipFile
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
from .utils import (
    download_file,
    delete_gcs_file,
    delete_gcs_prefix,
    user_id_email_to_prefix,
    EXCLUDE_PAGES,
    is_two_column_page,
    extract_text_blocks,
    looks_like_continuation,
    table_to_dict,
)


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IngestionRepository(db)
        self._bucket = storage.Client().bucket(settings.gcs_bucket_name)
        self._embed_model: Optional[TextEmbeddingModel] = None

    def upload_file_to_gcs(self, path: Path, key: str, content_type: str) -> str:
        """
        Uploads a file to Google Cloud Storage and returns the GCS URL.
        """
        blob = self._bucket.blob(key)
        blob.upload_from_filename(str(path), content_type=content_type)
        return f"gs://{settings.gcs_bucket_name}/{key}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Gets embeddings for a list of texts using the Vertex AI embedding model.
        Returns a list of embedding vectors.
        """
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

    @staticmethod
    @logOperation
    def data_extractor(file_path: str, output_dir: str = ".") -> Path:
        """
        Extracts text and tables from a PDF file and saves the structured content as JSON.
        Returns the path to the JSON file.
        """
        if not file_path.endswith(".pdf"):
            raise ValueError("Only PDF files are supported.")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / (Path(file_path).stem + ".json")

        fitz_doc = fitz.open(file_path)
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

                fitz_page  = fitz_doc[page_num - 1]
                plumb_page = pdf_doc.pages[page_num - 1]

                found_tables = plumb_page.find_tables()
                raw_tables   = plumb_page.extract_tables()
                table_bboxes = [ft.bbox for ft in found_tables]

                two_col     = is_two_column_page(fitz_page)
                text_blocks = extract_text_blocks(fitz_page, table_bboxes, two_col)

                table_blocks = []
                this_page_last_col_count = None

                for i, table in enumerate(raw_tables):
                    if not table:
                        continue
                    col_count = len(table[0]) if table else 0
                    is_cont = (
                        prev_last_col_count is not None
                        and looks_like_continuation(table, prev_last_col_count)
                    )
                    tdict = table_to_dict(
                        table, is_cont, prev_last_page if is_cont else None,
                        table_index=i, page_num=page_num,
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
            encoding="utf-8",
        )
        return out_path

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
    
    @logOperation
    def fetch_all_ingestion_records(
        self, user_id: str
    ) -> Optional[Ingestion]:
        """
        Fetch all ingestion records for the given user.
        Returns None if no record is found.
        """
        return self.repo.get_all_ingestions_by_user_id(user_id)
    
    @logOperation
    def download_ingestion_files(self, ingestion_id: str) -> BytesIO:
        """
        Download the PDF and JSON files for the given ingestion record as a ZIP.
        Raises HTTPException if the record is not found.
        """
        record = self.repo.get_by_id(ingestion_id)
        if not record:
            raise HTTPException(status_code=404, detail="Ingestion record not found")

        pdf_file = download_file(record.file_url)
        json_file = download_file(record.json_url)

        zip_buffer = BytesIO()
        with ZipFile(zip_buffer, "w") as zip_file:
            zip_file.writestr(Path(record.file_url).name, pdf_file.getvalue())
            zip_file.writestr(Path(record.json_url).name, json_file.getvalue())

        zip_buffer.seek(0)

        return zip_buffer

    @logOperation
    def delete_all_ingestion_records(self, user_id: str) -> None:
        """
        Delete all ingestion records and associated files for the given user.
        Raises HTTPException if no records are found.
        """
        records = self.repo.get_all_ingestions_by_user_id(user_id)
        if not records:
            raise HTTPException(status_code=404, detail="No ingestion records found for the user")

        user = AuthRepository(self.db).get_user_by_id(user_id)
        prefix = user_id_email_to_prefix(user_id, user.email)
        delete_gcs_prefix(settings.gcs_bucket_name, prefix)

        for record in records:
            self.repo.delete_chunks_by_ingestion_id(record.id)
            self.db.delete(record)

        self.db.commit()

    @logOperation
    def delete_ingestion_record_by_id(self, ingestion_id: str) -> None:
        """
        Delete a specific ingestion record and its associated files by ID.
        Raises HTTPException if the record is not found.
        """
        record = self.repo.get_by_id(ingestion_id)
        if not record:
            raise HTTPException(status_code=404, detail="Ingestion record not found")

        delete_gcs_file(record.file_url)
        delete_gcs_file(record.json_url)

        self.repo.delete_chunks_by_ingestion_id(record.id)
        self.db.delete(record)
        self.db.commit()

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
        prefix = user_id_email_to_prefix(user_id, user_email)
        stem = Path(filename).stem

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
                pdf_key = f"{prefix}/original_uploads/{ingestion_id}_{filename}"
                file_url = self.upload_file_to_gcs(pdf_path, pdf_key, "application/pdf")
                self.repo.update(record, file_url=file_url, status=IngestionStatus.UPLOADED)

                # 2 — Extract PDF → JSON ---------------------------------------
                self.repo.update(record, status=IngestionStatus.EXTRACTING)
                json_path = self.data_extractor(str(pdf_path), output_dir=str(tmp_dir))
                self.repo.update(record, status=IngestionStatus.EXTRACTED)

                # 3 — Upload JSON to GCS ---------------------------------------
                json_key = f"{prefix}/converted_data/{ingestion_id}_{stem}.json"
                json_url = self.upload_file_to_gcs(json_path, json_key, "application/json")
                self.repo.update(record, json_url=json_url)

                # 4 — Chunk ----------------------------------------------------
                doc = json.loads(json_path.read_text(encoding="utf-8"))
                chunk_list = chunk_document(doc)

                # 5 — Embed + store --------------------------------------------
                self.repo.update(record, status=IngestionStatus.INDEXING)
                vectors = self.embed([c["content"] for c in chunk_list])

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