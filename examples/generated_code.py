"""A file in the style of code a model hands you: plausible, tested on the
happy path, and quietly wrong at the edges.

Five real bugs are planted here, one of each kind jachai looks for.
Four correct functions are mixed in — if the tool flags any of those, it is
crying wolf, and the fix belongs in checks.py, not here.
"""

from __future__ import annotations


# --- planted bug 1: dies on empty input ------------------------------------
def average(values: list[float]) -> float:
    """Arithmetic mean of a list of numbers."""
    return sum(values) / len(values)


# --- planted bug 2: silently reorders the caller's list ---------------------
def normalise_tags(tags: list[str]) -> list[str]:
    """Lowercase and sort a list of tags."""
    tags.sort()
    return [tag.strip().lower() for tag in tags]


# --- planted bug 3: annotation promises a dict, sometimes returns None ------
def find_user(users: list[dict], name: str) -> dict:
    """Look up a user record by name."""
    for user in users:
        if user.get("name") == name:
            return user


# --- planted bug 4: mutable default argument keeps state between calls ------
def collect(item: str, bucket: list[str] = []) -> list[str]:
    """Accumulate items into a bucket."""
    bucket.append(item)
    return bucket


# --- planted bug 5: loops forever on negative input -------------------------
def countdown(n: int) -> int:
    """Count down to zero and report how many steps it took."""
    steps = 0
    while n != 0:
        n -= 1
        steps += 1
    return steps


# --- correct: pure arithmetic ----------------------------------------------
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


# --- correct: handles empty and unicode input -------------------------------
def slugify(text: str) -> str:
    """Turn arbitrary text into a URL-safe slug."""
    cleaned = [ch.lower() if ch.isalnum() else "-" for ch in text]
    return "-".join(part for part in "".join(cleaned).split("-") if part)


# --- correct: rejects bad input on purpose, so its ValueError is not a bug ---
def safe_divide(a: float, b: float) -> float:
    """Divide a by b, refusing to divide by zero."""
    if b == 0:
        raise ValueError("division by zero is not allowed")
    return a / b


# --- correct: in-place by design, and says so by returning None -------------
def append_item(items: list[str], value: str) -> None:
    """Append a value to a list in place."""
    items.append(value)
