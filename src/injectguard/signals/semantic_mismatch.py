from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from importlib import resources
from typing import Any, TypedDict, cast

from injectguard.signals.common import SignalMatch, clamp, cosine
from injectguard.types import ContainerType

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,}")


class _CentroidData(TypedDict):
    dimension: int
    centroids: dict[str, list[float]]


def score(content: str, container: ContainerType, source: str | None = None) -> SignalMatch:
    centroids = _load_centroids()
    expected = centroids.get("centroids", {}).get(container.value) or centroids.get(
        "centroids",
        {},
    ).get("UNKNOWN")
    if not expected:
        return SignalMatch("semantic_mismatch", 0.0, [], "no centroid")

    embedded = _embed(content, int(centroids.get("dimension", len(expected))))
    similarity = cosine(embedded, expected)
    mismatch = clamp((1.0 - similarity) * 0.9)

    if container in {ContainerType.MARKDOWN, ContainerType.UNKNOWN}:
        mismatch *= 0.5
    if len(TOKEN_RE.findall(content)) < 5:
        mismatch *= 0.4

    return SignalMatch(
        name="semantic_mismatch",
        score=clamp(mismatch),
        spans=[],
        details=f"container-topic similarity={similarity:.2f}",
    )


@lru_cache(maxsize=1)
def _load_centroids() -> _CentroidData:
    with (
        resources.files("injectguard.data")
        .joinpath("centroids.json")
        .open(
            "r",
            encoding="utf-8",
        ) as handle
    ):
        return cast(_CentroidData, json.load(handle))


def _embed(text: str, dimension: int) -> list[float]:
    transformer = _load_transformer()
    if transformer is not None:
        try:
            vector = transformer.encode([text], normalize_embeddings=True)[0]
            if len(vector) == dimension:
                return [float(value) for value in vector]
        except Exception:
            pass
    return _hash_embedding(text, dimension)


@lru_cache(maxsize=1)
def _load_transformer() -> Any | None:
    if os.environ.get("INJECTGUARD_DISABLE_TRANSFORMERS") == "1":
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    try:
        return SentenceTransformer(
            os.environ.get("INJECTGUARD_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            local_files_only=True,
        )
    except TypeError:
        return None
    except Exception:
        return None


def _hash_embedding(text: str, dimension: int) -> list[float]:
    vector = [0.0] * dimension
    tokens = TOKEN_RE.findall(text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = sum(value * value for value in vector) ** 0.5
    if not norm:
        return vector
    return [value / norm for value in vector]
