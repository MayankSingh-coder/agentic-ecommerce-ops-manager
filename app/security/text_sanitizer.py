import re


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"send\s+all\s+customer\s+emails?",
    r"exfiltrate\s+[^.?!]+",
    r"developer\s+message",
    r"system\s+message",
]

URL_PATTERN = re.compile(r"https?://\S+", flags=re.IGNORECASE)


def sanitize_untrusted_text(value: str | None, *, max_length: int = 240) -> str:
    if not value:
        return ""
    sanitized = " ".join(value.split())
    sanitized = URL_PATTERN.sub("[redacted-url]", sanitized)
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[redacted-instruction]", sanitized, flags=re.IGNORECASE)
    if len(sanitized) > max_length:
        return f"{sanitized[:max_length].rstrip()}..."
    return sanitized
