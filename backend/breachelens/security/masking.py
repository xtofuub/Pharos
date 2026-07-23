"""Sensitive value masking."""
from __future__ import annotations

import re


def mask_value(value: str, visible: int = 2) -> str:
    """Mask a value, keeping `visible` chars at start and end."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "•" * max(4, len(value))
    head = value[:visible]
    tail = value[-visible:]
    masked_len = min(20, max(6, len(value) - visible * 2))
    return f"{head}{'•' * masked_len}{tail}"


def mask_email(email: str) -> str:
    if "@" not in email:
        return mask_value(email, 2)
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{'•' * max(4, len(local))}@{domain}"
    head = local[:2]
    mask_len = max(4, min(20, len(local) - 2))
    return f"{head}{'•' * mask_len}@{domain}"


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return "•" * len(phone)
    last4 = digits[-4:]
    return f"+1-•••-•••-{last4}"


def mask_ip(ip: str) -> str:
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.••.••"
    if ":" in ip:
        parts = ip.split(":")
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:••••:••••"
    return mask_value(ip, 2)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return "•" * min(32, len(value))


def mask_credit_card(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 13:
        return mask_value(value, 2)
    last4 = digits[-4:]
    return f"•••• •••• •••• {last4}"


def mask_preview(line: str, query: str) -> str:
    """Mask a full line for preview, preserving the query substring and a small context window."""
    if query:
        lower_line = line.lower()
        lower_query = query.lower()
        pos = lower_line.find(lower_query)
        if pos != -1:
            start = max(0, pos - 20)
            end = min(len(line), pos + len(query) + 40)
            masked = "•" * start
            masked += line[start:end]
            if end < len(line):
                masked += "•" * (len(line) - end)
            return _mask_sensitive_within(masked)
    return _mask_sensitive_within(line)


def _mask_sensitive_within(s: str) -> str:
    """Mask passwords, tokens, credit cards inside a string."""
    out = s
    labeled_re = re.compile(
        r"(?i)\b(password|passwd|pass|pwd|token|api[_-]?key|secret|session|cookie|bearer)\s*[:=]\s*(\S+)"
    )
    out = labeled_re.sub(lambda m: f"{m.group(1)}:{mask_secret(m.group(2))}", out)
    cc_re = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
    out = cc_re.sub(lambda m: mask_credit_card(m.group(0)), out)
    return out
