"""Negative control: rejects bad input on purpose. Synthetic."""


def safe_divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero is not allowed")
    return a / b
