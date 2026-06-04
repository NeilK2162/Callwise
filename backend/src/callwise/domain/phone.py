"""E.164 phone normalization (PRD §5.1, edge case #22).

Accepts the many shapes a spreadsheet throws at us (`0091...`, `+91 ...`, spaces,
dashes, parens) and returns canonical E.164, or raises so the row lands in the
`rejected_rows` artifact rather than failing the whole upload.
"""

from __future__ import annotations

import phonenumbers


class InvalidPhoneNumber(ValueError):
    pass


def normalize_e164(raw: str, default_region: str = "IN") -> str:
    """Return E.164 (e.g. ``+919876543210``) or raise InvalidPhoneNumber."""
    if raw is None:
        raise InvalidPhoneNumber("empty")
    candidate = raw.strip()
    if not candidate:
        raise InvalidPhoneNumber("empty")
    try:
        parsed = phonenumbers.parse(candidate, default_region)
    except phonenumbers.NumberParseException as exc:  # noqa: PERF203
        raise InvalidPhoneNumber(f"unparseable: {raw!r}") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber(f"invalid: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_e164(e164: str) -> str:
    """Mask for display/logs: ``+91 ····· 4821`` (PII minimization, PRD §14.5)."""
    if len(e164) < 5:
        return "·" * len(e164)
    return f"{e164[:3]} ····· {e164[-4:]}"
