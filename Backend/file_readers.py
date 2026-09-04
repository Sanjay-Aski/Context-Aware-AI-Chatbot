"""Extraction helpers for chat attachments. Original bytes are kept separately in GridFS."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import mimetypes
import os
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


MAX_TEXT_CHARS = 45_000
MAX_VIDEO_FRAMES = 8
MAX_VIDEO_DURATION_SECONDS = 30 * 60
CODE_EXTENSIONS = {
    ".py": "Python", ".pyw": "Python", ".java": "Java", ".c": "C", ".h": "C/C++ header",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++ header", ".hh": "C++ header",
    ".js": "JavaScript", ".jsx": "React JSX", ".ts": "TypeScript", ".tsx": "React TSX",
    ".go": "Go", ".rs": "Rust", ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift",
    ".kt": "Kotlin", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
    ".bat": "Windows batch", ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".xml": "XML",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".ini": "INI",
    ".md": "Markdown", ".rst": "reStructuredText", ".txt": "Text", ".log": "Log", ".env": "Environment config",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg", ".m4v"}
logger = logging.getLogger(__name__)


@dataclass
class ProcessedUpload:
    filename: str
    content_type: str
    size: int
    sha256: str
    category: str
    metadata: dict[str, Any] = field(default_factory=dict)
    extracted_text: str = ""
    model_images: list[bytes] = field(default_factory=list)
    audio_payload: bytes | None = None


class FileProcessingError(ValueError):
    """Raised when a known file type cannot be safely read."""


def _decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise FileProcessingError("Binary content cannot be read as text.")
    control_bytes = sum(byte < 9 or 13 < byte < 32 for byte in data)
    if data and control_bytes / len(data) > 0.02:
        raise FileProcessingError("Binary content cannot be read as text.")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileProcessingError("This file is not readable as text.")


def _limit_text(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _base(filename: str, content_type: str, data: bytes, category: str) -> ProcessedUpload:
    return ProcessedUpload(
        filename=Path(filename).name or "attachment",
        content_type=content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        category=category,
    )


def _image_bytes(data: bytes) -> tuple[bytes, dict[str, Any]]:
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as opened:
            image_format = opened.format or "unknown"
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            image.thumbnail((2048, 2048))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue(), {
                "format": image_format,
                "width": width,
                "height": height,
                "model_width": image.width,
                "model_height": image.height,
            }
    except Exception as exc:
        raise FileProcessingError("The image could not be decoded.") from exc


def _extract_pdf(data: bytes) -> tuple[str, dict[str, Any], list[bytes]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        page_count = len(reader.pages)
        info = reader.metadata
        metadata = {
            "page_count": page_count,
            "title": str(info.title) if info and info.title else None,
            "author": str(info.author) if info and info.author else None,
        }
        text = "\n\n".join(f"[Page {index + 1}]\n{page}" for index, page in enumerate(pages) if page)
    except Exception as exc:
        raise FileProcessingError("The PDF could not be opened. It may be encrypted or damaged.") from exc

    # Scanned PDFs have no embedded text; render a few pages for the vision model.
    page_images: list[bytes] = []
    if not text.strip() and page_count:
        try:
            import fitz

            pdf = fitz.open(stream=data, filetype="pdf")
            for page in list(pdf)[:MAX_VIDEO_FRAMES]:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                page_images.append(pixmap.tobytes("jpeg"))
            pdf.close()
            metadata["scanned_pages_rendered"] = len(page_images)
        except Exception:
            metadata["scanned_pages_rendered"] = 0
    return text, metadata, page_images


def _extract_docx(data: bytes) -> tuple[str, dict[str, Any]]:
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table_index, table in enumerate(document.tables, start=1):
            parts.append(f"[Table {table_index}]")
            parts.extend(" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows)
        props = document.core_properties
        return "\n".join(parts), {
            "paragraph_count": len(document.paragraphs),
            "table_count": len(document.tables),
            "title": props.title or None,
            "author": props.author or None,
        }
    except Exception as exc:
        raise FileProcessingError("The DOCX document could not be opened.") from exc


def _extract_pptx(data: bytes) -> tuple[str, dict[str, Any]]:
    from pptx import Presentation

    try:
        presentation = Presentation(io.BytesIO(data))
        slides = []
        for index, slide in enumerate(presentation.slides, start=1):
            lines = [shape.text.strip() for shape in slide.shapes if getattr(shape, "has_text_frame", False) and shape.text.strip()]
            if lines:
                slides.append(f"[Slide {index}]\n" + "\n".join(lines))
        return "\n\n".join(slides), {"slide_count": len(presentation.slides)}
    except Exception as exc:
        raise FileProcessingError("The PowerPoint document could not be opened.") from exc


def _extract_xlsx(data: bytes) -> tuple[str, dict[str, Any]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        parts = []
        sheets = []
        for sheet in workbook.worksheets:
            sheets.append({"name": sheet.title, "rows": sheet.max_row, "columns": sheet.max_column})
            parts.append(f"[Sheet: {sheet.title}]")
            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = ["" if value is None else str(value) for value in row]
                parts.append("\t".join(values))
                if row_index >= 1000:
                    parts.append("[Sheet content truncated after 1000 rows]")
                    break
        workbook.close()
        return "\n".join(parts), {"sheets": sheets}
    except Exception as exc:
        raise FileProcessingError("The spreadsheet could not be opened.") from exc


def _extract_csv(data: bytes, delimiter: str) -> tuple[str, dict[str, Any]]:
    try:
        text = _decode_text(data)
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        columns = len(rows[0]) if rows else 0
        return "\n".join("\t".join(row) for row in rows), {"row_count": len(rows), "column_count": columns}
    except Exception as exc:
        raise FileProcessingError("The delimited text file could not be read.") from exc


def _audio_info(data: bytes) -> dict[str, Any]:
    import av

    try:
        container = av.open(io.BytesIO(data))
        audio = next((stream for stream in container.streams if stream.type == "audio"), None)
        if audio is None:
            raise FileProcessingError("No audio track was found in this file.")
        duration = float(audio.duration * audio.time_base) if audio.duration and audio.time_base else float(container.duration / av.time_base) if container.duration else None
        metadata = {
            "duration_seconds": round(duration, 2) if duration is not None else None,
            "sample_rate": audio.codec_context.sample_rate,
            "codec": audio.codec_context.name,
            "channels": audio.codec_context.channels,
        }
        container.close()
        return metadata
    except FileProcessingError:
        raise
    except Exception as exc:
        raise FileProcessingError("The audio file could not be decoded.") from exc


def _extract_video(data: bytes) -> tuple[list[bytes], dict[str, Any], bytes | None]:
    import av
    import numpy as np

    try:
        container = av.open(io.BytesIO(data))
        video = next((stream for stream in container.streams if stream.type == "video"), None)
        if video is None:
            raise FileProcessingError("No video track was found in this file.")
        duration = float(video.duration * video.time_base) if video.duration and video.time_base else float(container.duration / av.time_base) if container.duration else None
        if duration and duration > MAX_VIDEO_DURATION_SECONDS:
            raise FileProcessingError("Videos longer than 30 minutes are not supported yet.")

        wanted_times = set()
        if duration and duration > 0:
            count = min(MAX_VIDEO_FRAMES, max(1, int(duration // 10) + 1))
            wanted_times = {duration * index / count for index in range(count)}
        else:
            wanted_times = {0.0}

        frames: list[bytes] = []
        next_time = min(wanted_times)
        for frame in container.decode(video):
            timestamp = float(frame.time or 0.0)
            if timestamp + 0.05 < next_time:
                continue
            image = frame.to_image().convert("RGB")
            image.thumbnail((1536, 1536))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            frames.append(output.getvalue())
            later = [value for value in wanted_times if value > timestamp + 0.05]
            if not later or len(frames) >= MAX_VIDEO_FRAMES:
                break
            next_time = min(later)

        has_audio = any(stream.type == "audio" for stream in container.streams)
        metadata = {
            "duration_seconds": round(duration, 2) if duration is not None else None,
            "width": video.codec_context.width,
            "height": video.codec_context.height,
            "video_codec": video.codec_context.name,
            "audio_track": has_audio,
            "sampled_frames": len(frames),
        }
        container.close()

        audio_payload = None
        if has_audio:
            audio_container = av.open(io.BytesIO(data))
            audio_stream = next(stream for stream in audio_container.streams if stream.type == "audio")
            output = io.BytesIO()
            with wave.open(output, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in audio_container.decode(audio_stream):
                    for converted in resampler.resample(frame):
                        wav_file.writeframes(converted.to_ndarray().astype(np.int16).tobytes())
                for converted in resampler.resample(None):
                    wav_file.writeframes(converted.to_ndarray().astype(np.int16).tobytes())
            audio_container.close()
            audio_payload = output.getvalue()
        return frames, metadata, audio_payload
    except FileProcessingError:
        raise
    except Exception as exc:
        raise FileProcessingError("The video could not be decoded. Try MP4, MOV, MKV, or WebM.") from exc


def transcribe_audio(data: bytes) -> tuple[str, dict[str, Any]]:
    """Transcribe speech locally with a lazily loaded faster-whisper model."""

    model_name = os.environ.get("AUDIO_TRANSCRIPTION_MODEL", "tiny")
    device = os.environ.get("AUDIO_TRANSCRIPTION_DEVICE", "cpu")
    compute_type = os.environ.get("AUDIO_TRANSCRIPTION_COMPUTE_TYPE", "int8")
    try:
        from faster_whisper import WhisperModel

        model = _get_whisper_model(model_name, device, compute_type)
        # Pass the encoded stream directly so MP3/M4A/etc. bytes are not mislabeled
        # as a WAV file based on a temporary filename.
        segments, info = model.transcribe(io.BytesIO(data), vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return transcript, {
            "language": getattr(info, "language", None),
            "language_probability": round(float(info.language_probability), 3) if getattr(info, "language_probability", None) is not None else None,
            "transcriber": f"faster-whisper/{model_name}",
        }
    except Exception as exc:
        logger.exception("Audio transcription failed using faster-whisper model %s", model_name)
        raise FileProcessingError("Audio transcription failed. Check that the local faster-whisper model can be downloaded and loaded.") from exc


@lru_cache(maxsize=1)
def _get_whisper_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def process_upload(filename: str, content_type: str, data: bytes) -> ProcessedUpload:
    extension = Path(filename).suffix.lower()
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if extension == ".pdf" or mime == "application/pdf":
        item = _base(filename, mime, data, "pdf")
        text, metadata, images = _extract_pdf(data)
        item.metadata.update(metadata)
        item.extracted_text = text
        item.model_images = images
    elif extension == ".docx" or mime.endswith("wordprocessingml.document"):
        item = _base(filename, mime, data, "document")
        item.extracted_text, metadata = _extract_docx(data)
        item.metadata.update(metadata)
    elif extension == ".pptx" or mime.endswith("presentationml.presentation"):
        item = _base(filename, mime, data, "presentation")
        item.extracted_text, metadata = _extract_pptx(data)
        item.metadata.update(metadata)
    elif extension in {".xlsx", ".xlsm"} or "spreadsheetml" in mime:
        item = _base(filename, mime, data, "spreadsheet")
        item.extracted_text, metadata = _extract_xlsx(data)
        item.metadata.update(metadata)
    elif extension in IMAGE_EXTENSIONS or mime.startswith("image/"):
        item = _base(filename, mime, data, "image")
        image_data, metadata = _image_bytes(data)
        item.metadata.update(metadata)
        item.model_images = [image_data]
        item.extracted_text = f"Image attachment: {item.metadata.get('format')} image, {item.metadata.get('width')} x {item.metadata.get('height')} pixels."
    elif extension in VIDEO_EXTENSIONS or mime.startswith("video/"):
        item = _base(filename, mime, data, "video")
        frames, metadata, audio_payload = _extract_video(data)
        item.metadata.update(metadata)
        item.model_images = frames
        item.audio_payload = audio_payload
        item.extracted_text = f"Video attachment: {metadata.get('duration_seconds')} seconds, {metadata.get('width')} x {metadata.get('height')} pixels, {metadata.get('sampled_frames')} sampled frames."
    elif extension in AUDIO_EXTENSIONS or mime.startswith("audio/"):
        item = _base(filename, mime, data, "audio")
        item.metadata.update(_audio_info(data))
        item.audio_payload = data
        item.extracted_text = "Audio attachment. Speech transcription is being prepared."
    elif extension in {".csv", ".tsv"}:
        item = _base(filename, mime, data, "spreadsheet")
        item.extracted_text, metadata = _extract_csv(data, "\t" if extension == ".tsv" else ",")
        item.metadata.update(metadata)
    else:
        try:
            text = _decode_text(data)
            language = CODE_EXTENSIONS.get(extension)
            category = "code" if language and language not in {"Markdown", "reStructuredText", "Text", "Log", "Environment config"} else "text"
            item = _base(filename, mime, data, category)
            item.metadata.update({"language": language, "line_count": text.count("\n") + 1})
            item.extracted_text = text
        except FileProcessingError:
            item = _base(filename, mime, data, "file")
            item.extracted_text = "The file is attached, but this file type has no text extractor. Use a PDF, DOCX, PPTX, XLSX, CSV, source-code, image, audio, or video file for content understanding."

    item.metadata["truncated"] = len(item.extracted_text) > MAX_TEXT_CHARS
    item.extracted_text, _ = _limit_text(item.extracted_text)
    return item
