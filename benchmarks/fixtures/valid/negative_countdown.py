"""Loops forever on negative input. Synthetic."""


def countdown(n: int) -> int:
    steps = 0
    while n != 0:
        n -= 1
        steps += 1
    return steps
