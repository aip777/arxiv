"""
Vector storage and search on top of SQLite.

Vectors are stored L2-normalised as float32 bytes, so cosine similarity is a
plain dot product. Search is an exact scan with numpy: for a few thousand
abstracts that takes milliseconds and needs no extra service or index file.
"""
import numpy as np

from rag.models import PaperEmbedding


def to_blob(vector) -> bytes:
    array = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(array)
    if norm:
        array = array / norm
    return array.tobytes()


def nearest(query_vector, model: str, top_k: int) -> list[tuple[int, float]]:
    """Return up to `top_k` (paper_id, cosine distance) pairs, closest first."""
    rows = list(PaperEmbedding.objects.filter(model=model).values_list("paper_id", "embedding"))
    if not rows:
        return []

    paper_ids = [paper_id for paper_id, _ in rows]
    matrix = np.frombuffer(b"".join(blob for _, blob in rows), dtype=np.float32).reshape(len(rows), -1)
    query = np.frombuffer(to_blob(query_vector), dtype=np.float32)
    if query.shape[0] != matrix.shape[1]:
        raise ValueError(f"Query has {query.shape[0]} dimensions but the index has {matrix.shape[1]}.")

    similarities = matrix @ query
    best = np.argsort(-similarities)[:top_k]
    return [(paper_ids[i], float(1.0 - similarities[i])) for i in best]
