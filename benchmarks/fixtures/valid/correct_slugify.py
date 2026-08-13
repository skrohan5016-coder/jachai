"""Negative control: correct code that must not be flagged. Synthetic."""


def slugify(text: str) -> str:
    cleaned = [ch.lower() if ch.isalnum() else "-" for ch in text]
    return "-".join(part for part in "".join(cleaned).split("-") if part)
