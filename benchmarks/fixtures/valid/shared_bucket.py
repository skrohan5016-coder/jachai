"""Mutable default argument shared by every call. Synthetic."""


def collect(item: str, bucket: list[str] = []) -> list[str]:
    bucket.append(item)
    return bucket
