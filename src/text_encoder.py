"""Sentence encoder shared by intent prediction and semantic retrieval.

all-MiniLM-L6-v2 is loaded once, on first use, and never at import time,
so scripts that only need the deterministic stages never pay for it.
Embeddings are L2-normalised, so a dot product is a cosine similarity.
"""
from __future__ import annotations

import numpy as np

from configs.settings import SETTINGS

_encoder = None


def load_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        local_copy = SETTINGS.models_dir / SETTINGS.sentence_model_id.split("/")[-1]
        source = str(local_copy) if local_copy.exists() else SETTINGS.sentence_model_id
        _encoder = SentenceTransformer(source, device="cpu")
    return _encoder


def encode(texts: list[str]) -> np.ndarray:
    """Return one L2-normalised 384-d vector per text as a float32 matrix."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vectors = load_encoder().encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(vectors, dtype=np.float32)
