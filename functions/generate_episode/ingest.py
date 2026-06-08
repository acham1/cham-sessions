import logging
import os
import tempfile

from google.cloud import storage

logger = logging.getLogger(__name__)

# Cap extracted text so a huge attachment can't blow up the prompt (and the
# Claude Agent SDK CLI transport caps a single message at ~1MB). 400K chars is
# ~100K tokens — covers a full research paper while staying well under the
# transport ceiling and within the model's context. For inputs larger than this
# (e.g. a book), the tail is truncated; a map-reduce summarize pass would be the
# next step if that becomes common.
MAX_EXTRACT_CHARS = 400_000

_TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".html", ".htm"}


def _extract_text(path: str, content_type: str, filename: str) -> str | None:
    """Extract plain text from an attachment. Returns None for binary types we
    can't read. We never hand raw files (esp. PDFs) to the agent's Read tool —
    Read turns a PDF into base64 page images, which exceeds the SDK's transport
    buffer; extracting text here keeps the payload small."""
    name = filename.lower()
    ctype = (content_type or "").lower()

    is_pdf = "pdf" in ctype or name.endswith(".pdf")
    is_text = ctype.startswith("text/") or os.path.splitext(name)[1] in _TEXT_EXTS

    text = None
    if is_pdf:
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            logger.exception("PDF text extraction failed for %s", filename)
            return None
    elif is_text:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception:
            logger.exception("Text read failed for %s", filename)
            return None
    else:
        return None

    text = (text or "").strip()
    if not text:
        return None
    if len(text) > MAX_EXTRACT_CHARS:
        text = text[:MAX_EXTRACT_CHARS] + "\n\n[... attachment truncated ...]"
    return text


def prepare_request(request: dict) -> dict:
    """Materialize the inbound request: download attachments from GCS and
    extract their text so it can be embedded directly in the agent prompt.
    """
    work_dir = tempfile.mkdtemp(prefix="cham-")
    files = []

    attachments = request.get("attachments") or []
    if attachments:
        client = storage.Client()
        for att in attachments:
            gcs_uri = att.get("gcs_uri", "")
            if not gcs_uri.startswith("gs://"):
                continue
            bucket_name, _, blob_path = gcs_uri[len("gs://") :].partition("/")
            local_name = os.path.basename(blob_path)
            local_path = os.path.join(work_dir, local_name)
            filename = att.get("filename", local_name)
            content_type = att.get("content_type", "")
            try:
                client.bucket(bucket_name).blob(blob_path).download_to_filename(
                    local_path
                )
            except Exception:
                logger.exception("Failed to download %s", gcs_uri)
                continue

            text = _extract_text(local_path, content_type, filename)
            files.append(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "text": text,
                }
            )
            logger.info(
                "Attachment %s: extracted %s",
                filename,
                f"{len(text)} chars" if text else "no text (unsupported/binary)",
            )

    return {
        "work_dir": work_dir,
        "files": files,
        "sender": request.get("sender", ""),
        "subject": request.get("subject", ""),
        "body_text": request.get("body_text", ""),
    }
