"""
embeddings.py -- Embedding utilities for cross-day deduplication.

Provides semantic similarity via sentence-transformers (nomic-embed-text-v1.5)
with Matryoshka truncation to 256 dimensions for efficient storage and comparison.
8K context window supports full article text in the future.
"""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Module-level singleton; populated lazily by load_model().
_model: Optional[object] = None

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
EMBEDDING_DIM = 256  # Matryoshka truncation from 768 → 256


def load_model():
    """
    Load the sentence-transformers model as a lazy singleton.

    The model is downloaded / cached on first call and reused for all
    subsequent calls within the same process.
    """
    global _model
    if _model is not None:
        return _model

    logger.info("Loading sentence-transformers model: %s", MODEL_NAME)
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
        logger.info("Model loaded successfully (full_dim=768, truncated_dim=%d)", EMBEDDING_DIM)
    except Exception as exc:
        logger.error("Failed to load sentence-transformers model: %s", exc)
        raise

    return _model


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Batch-encode a list of texts into 256-dimensional embeddings.

    Uses nomic-embed-text-v1.5 which encodes to 768d, then truncates to 256d
    via Matryoshka representation learning (retains ~95% quality).

    Returns a list of lists (one per input text), each containing 256 floats.
    """
    if not texts:
        logger.debug("compute_embeddings called with empty input; returning []")
        return []

    model = load_model()

    logger.debug("Encoding %d texts", len(texts))
    # Encode to full 768d, then truncate to 256d (Matryoshka)
    embeddings: np.ndarray = model.encode(texts, show_progress_bar=False)
    embeddings = embeddings[:, :EMBEDDING_DIM]

    # Convert to plain Python lists for JSON-serializability / DB storage
    return embeddings.tolist()


def batch_cosine_similarity(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between a single vector and every row of a matrix.

    Parameters
    ----------
    vec : np.ndarray
        1-D array of shape (d,).
    matrix : np.ndarray
        2-D array of shape (n, d) where each row is a candidate vector.

    Returns
    -------
    np.ndarray
        1-D array of shape (n,) with cosine similarities in [-1, 1].
        Returns an empty array (shape (0,)) when *matrix* has no rows.
    """
    if matrix.size == 0:
        return np.array([], dtype=np.float64)

    # L2-normalize the query vector
    vec_norm = np.linalg.norm(vec)
    if vec_norm == 0.0:
        logger.warning("batch_cosine_similarity received a zero vector")
        return np.zeros(matrix.shape[0], dtype=np.float64)
    vec_normed = vec / vec_norm

    # L2-normalize each row of the matrix
    row_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    # Guard against zero-norm rows (replace 0 with 1 to avoid division by zero;
    # the dot product for those rows will be 0 anyway).
    row_norms = np.where(row_norms == 0.0, 1.0, row_norms)
    matrix_normed = matrix / row_norms

    # Cosine similarity = dot product of unit vectors
    similarities = matrix_normed @ vec_normed

    return similarities
