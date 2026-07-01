from __future__ import annotations

import re
import fitz
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse
from google.cloud import storage


EXCLUDE_PAGES: set[int] = {2}
TWO_COLUMN_RATIO_THRESHOLD = 0.25
CONTINUATION_NUMERIC_THRESHOLD = 0.85


def email_to_prefix(email: str) -> str:
    """
    Converts an email address into a safe prefix for GCS paths.
    Eg: rohit14101998@gmail.com  →  rohit14101998-gmail-com
    """
    return email.replace("@", "-").replace(".", "-")


def user_id_email_to_prefix(user_id: str, email: str) -> str:
    """
    Combines user ID and email into a unique GCS path prefix.
    Eg: ae478233_rohit14101998-gmail-com
    """
    return f"{user_id}_{email_to_prefix(email)}"


def is_numeric_cell(val: str) -> bool:
    """
    Checks if a cell value is numeric or represents a missing value (NA, N/A, etc.).
    Returns True if the cell is numeric or missing, False otherwise.
    """
    v = (val or "").strip().replace(",", "").replace("%", "").replace("-", "")
    if v in ("NA", "na", "N/A", ""):
        return True
    try:
        float(v)
        return True
    except ValueError:
        return False


def looks_like_continuation(table, prev_col_count: int) -> bool:
    """
    Determines if a table is likely a continuation of the previous table based on the number of columns
    and the content of the first row. If the first row is mostly numeric, it's likely a continuation.
    """
    if not table or len(table[0]) != prev_col_count:
        return False
    first_row = [str(c) if c else "" for c in table[0]]
    ratio = sum(is_numeric_cell(c) for c in first_row) / len(first_row)
    return ratio >= CONTINUATION_NUMERIC_THRESHOLD


def is_two_column_page(fitz_page: fitz.Page) -> bool:
    """
    Checks if a PDF page is likely to be two-column based on the position of text blocks.
    Returns True if the page is likely two-column, False otherwise.
    """
    pw = fitz_page.rect.width
    blocks = fitz_page.get_text("blocks", sort=True)
    text_blocks = [b for b in blocks if b[6] == 0 and str(b[4]).strip()]
    if not text_blocks:
        return False
    right = sum(1 for b in text_blocks if b[0] > pw * 0.45)
    return (right / len(text_blocks)) >= TWO_COLUMN_RATIO_THRESHOLD


def block_in_table(x0, y0, x1, y1, table_bboxes) -> bool:
    """
    Checks if a text block overlaps with any table bounding boxes.
    Returns True if it overlaps, False otherwise.
    """
    for tb in table_bboxes:
        tb_x0, tb_top, tb_x1, tb_bottom = tb
        if x0 < tb_x1 and x1 > tb_x0 and y0 < tb_bottom and y1 > tb_top:
            return True
    return False


def clean_text_block(text: str) -> str:
    """
    Fix word-per-line issue: if a block has many very short lines
    (avg < 20 chars), it's a fragmented block — rejoin as a paragraph.
    Also strips stray single-char lines (watermarks, artifacts).
    """
    lines = text.strip().splitlines()
    lines = [l for l in lines if len(l.strip()) != 1 or l.strip() == ""]
    if not lines:
        return ""
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return ""
    avg_len = sum(len(l.strip()) for l in non_empty) / len(non_empty)
    if avg_len < 25 and len(non_empty) > 3:
        rejoined = " ".join(l.strip() for l in non_empty if l.strip())
        rejoined = re.sub(r" {2,}", " ", rejoined)
        return rejoined
    return "\n".join(l.rstrip() for l in lines)


def extract_text_blocks(fitz_page: fitz.Page, table_bboxes: list, two_col: bool) -> list[dict]:
    """
    Extracts text blocks from a PDF page, excluding those that overlap with tables.
    If the page is two-column, it processes each column separately.
    Returns a list of dictionaries with block type, content, and bounding box.
    """
    pw = fitz_page.rect.width
    ph = fitz_page.rect.height
    if two_col:
        clips = [
            fitz.Rect(0,        0, pw * 0.5, ph),
            fitz.Rect(pw * 0.5, 0, pw,       ph),
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
            if block_in_table(x0, y0, x1, y1, table_bboxes):
                continue
            text = clean_text_block(text)
            if text:
                blocks_out.append({
                    "type": "text",
                    "content": text,
                    "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                })
    return blocks_out


def table_to_dict(
    table: list,
    is_continuation: bool,
    continued_from_page: Optional[int],
    table_index: int,
    page_num: int,
) -> dict:
    """
    Converts a table (list of lists) into a dictionary with metadata.
    If the first row is not numeric, it's treated as headers; otherwise, default headers are generated.
    """
    def clean(cell) -> str:
        return str(cell).replace("\n", " ").strip() if cell is not None else ""

    rows = [[clean(c) for c in row] for row in table if any(c for c in row)]
    if not rows:
        return {}

    col_count = max(len(r) for r in rows)
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    first = rows[0]
    if not all(is_numeric_cell(c) for c in first):
        headers = first
        data_rows = rows[1:]
    else:
        headers = [f"col_{i}" for i in range(col_count)]
        data_rows = rows

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


def download_file(gcs_url: str) -> BytesIO:
    """Downloads a file from GCS and returns it as a BytesIO object."""
    client = storage.Client()
    parsed = urlparse(gcs_url)
    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    file_obj = BytesIO()
    blob.download_to_file(file_obj)
    file_obj.seek(0)
    return file_obj


def delete_gcs_file(gcs_url: str) -> None:
    """Deletes a single file from GCS by its gs:// URL. No-op if URL is empty."""
    if not gcs_url:
        return
    client = storage.Client()
    parsed = urlparse(gcs_url)
    client.bucket(parsed.netloc).blob(parsed.path.lstrip("/")).delete()


def delete_gcs_prefix(bucket_name: str, prefix: str) -> None:
    """Deletes all blobs under the given prefix, effectively removing the folder."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix=prefix))
    if blobs:
        bucket.delete_blobs(blobs)