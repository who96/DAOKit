from __future__ import annotations

import hashlib
import math
import re


def embed_text(text: str, *, dimensions: int) -> tuple[float, ...]:
    if dimensions <= 0:
        raise ValueError("dimensions must be > 0")

    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    if not tokens:
        return tuple(0.0 for _ in range(dimensions))

    vector = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], byteorder="big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        magnitude = (digest[3] + 1) / 256.0
        vector[index] += sign * magnitude

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return tuple(0.0 for _ in range(dimensions))
    return tuple(round(value / norm, 8) for value in vector)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have equal dimensions")
    return float(sum(a * b for a, b in zip(left, right)))
