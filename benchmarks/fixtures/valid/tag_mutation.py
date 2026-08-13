"""Sorts the caller's list in place while looking pure. Synthetic."""


def normalise_tags(tags: list[str]) -> list[str]:
    tags.sort()
    return [tag.strip().lower() for tag in tags]
