"""Shared branch template validation and safe Issue title components."""

import re
import string
import unicodedata


MANUAL_FIELDS = {"project_id", "run_id"}
ISSUE_FIELDS = {"date", "approver", "issue_title"}


def template_fields(template, *, manual=False):
    parsed = list(string.Formatter().parse(template))
    fields = {field for _, field, _, _ in parsed if field is not None}
    supported = (MANUAL_FIELDS,) if manual else (MANUAL_FIELDS, ISSUE_FIELDS)
    if fields not in supported:
        raise ValueError("Use project_id/run_id or date/approver/issue_title placeholders")
    if any(spec or conversion for _, _, spec, conversion in parsed):
        raise ValueError("Branch template format modifiers are not supported")
    return fields


def valid_name(name):
    return bool(name and name[0].isalnum()
                and all(char.isalnum() or char in "._-/" for char in name)
                and len(name.encode("utf-8")) <= 240
                and ".." not in name and "//" not in name and not name.endswith(("/", "."))
                and not any(part.startswith(".") or part.endswith(".lock") for part in name.split("/")))


def issue_title_component(title):
    """Preserve Unicode letters/numbers and valid dots; remove ref syntax."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("An approved Issue title is required")
    text = unicodedata.normalize("NFC", title)
    text = "".join(char if char.isalnum() or char in "._-" else "-" for char in text)
    text = re.sub(r"\.{2,}", "-", re.sub(r"-+", "-", text)).strip("-.")
    text = text.encode("utf-8")[:120].decode("utf-8", errors="ignore").strip("-.")
    if text.lower().endswith(".lock"):
        text = text[:-5] + "-lock"
    return text or "issue"
