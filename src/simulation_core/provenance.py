"""Exact JSON Pointer references for supplied inputs and explicit assumptions."""

import re

from pydantic import JsonValue


def pointer_tokens(path: str) -> list[str]:
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError("Expected a non-root JSON Pointer with valid ~0/~1 escapes")
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def resolve_pointer(document: JsonValue, path: str) -> JsonValue:
    current = document
    for token in pointer_tokens(path):
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
            index = int(token)
            if index >= len(current):
                raise ValueError(f"Unresolved configuration path: {path}")
            current = current[index]
        else:
            raise ValueError(f"Unresolved configuration path: {path}")
    return current


def same_json(left: JsonValue, right: JsonValue) -> bool:
    # Python equality equates True and 1; input preservation must not.
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right
