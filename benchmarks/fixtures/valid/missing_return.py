"""Annotation promises a dict; the not-found path returns None. Synthetic."""


def find_user(users: list[dict], name: str) -> dict:
    for user in users:
        if user.get("name") == name:
            return user
