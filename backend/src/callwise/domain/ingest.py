"""CSV/XLSX contact parsing (PRD §5.1, edge cases #19, #20, #22).

Streaming, per-row validation: phone → E.164, in-file dedup, tag-column normalization.
Invalid rows are collected (not fatal) so the valid rows still import. For very large
files (>~50k rows) the async worker path streams from S3 instead of buffering — this
synchronous path handles normal uploads.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from callwise.domain.phone import InvalidPhoneNumber, normalize_e164

# Header names handled specially; everything else becomes a custom field.
_RESERVED = {"phone", "phone_e164", "number", "customer_name", "name", "language", "timezone"}


@dataclass(slots=True)
class ParsedRow:
    phone_e164: str
    customer_name: str | None
    language: str
    timezone: str
    custom_fields: dict[str, Any]


@dataclass(slots=True)
class IngestResult:
    valid: list[ParsedRow] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0


def _coerce_row(row: dict[str, Any], default_country: str) -> ParsedRow:
    """Map one raw row → ParsedRow. Raises InvalidPhoneNumber on an un-normalizable phone."""
    lower = {(k or "").strip().lower(): v for k, v in row.items()}
    phone_raw = str(lower.get("phone") or lower.get("phone_e164") or lower.get("number") or "")
    e164 = normalize_e164(phone_raw, default_country)
    name = (str(lower.get("customer_name") or lower.get("name") or "").strip()) or None
    language = (str(lower.get("language") or "").strip()) or "en-IN"
    timezone = (str(lower.get("timezone") or "").strip()) or "Asia/Kolkata"
    custom = {
        (k or "").strip(): v
        for k, v in row.items()
        if (k or "").strip().lower() not in _RESERVED and v not in (None, "")
    }
    return ParsedRow(e164, name, language, timezone, custom)


def _ingest_rows(rows, default_country: str) -> IngestResult:
    result = IngestResult()
    seen: set[str] = set()
    for raw in rows:
        result.total += 1
        try:
            parsed = _coerce_row(raw, default_country)
        except InvalidPhoneNumber as exc:
            result.rejected.append({"row": raw, "reason": str(exc)})
            continue
        if parsed.phone_e164 in seen:  # in-file dedup (edge #20)
            result.rejected.append({"row": raw, "reason": "duplicate_in_file"})
            continue
        seen.add(parsed.phone_e164)
        result.valid.append(parsed)
    return result


def parse_csv(content: bytes, default_country: str) -> IngestResult:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return _ingest_rows(reader, default_country)


def parse_xlsx(content: bytes, default_country: str) -> IngestResult:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    except StopIteration:
        return IngestResult()

    def _dicts():
        for values in rows_iter:
            if values is None or all(v is None for v in values):
                continue
            yield dict(zip(headers, values, strict=False))

    result = _ingest_rows(_dicts(), default_country)
    wb.close()
    return result


def parse_contacts(filename: str, content: bytes, default_country: str = "IN") -> IngestResult:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(content, default_country)
    return parse_csv(content, default_country)
