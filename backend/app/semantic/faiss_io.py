"""Unicode-safe persistence helpers for locally generated FAISS stores.

FAISS's native Windows file API cannot open paths containing some non-ASCII
characters. Serializing the index in memory and using Python's path-aware file
API preserves the same on-disk LangChain format without changing retrieval.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.faiss import dependable_faiss_import
from langchain_core.embeddings import Embeddings


def save_faiss_local(store: FAISS, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    faiss = dependable_faiss_import()
    serialized = faiss.serialize_index(store.index)
    (path / "index.faiss").write_bytes(serialized.tobytes())
    with (path / "index.pkl").open("wb") as handle:
        pickle.dump((store.docstore, store.index_to_docstore_id), handle)


def load_faiss_local(
    path: Path,
    embeddings: Embeddings,
    *,
    normalize_l2: bool,
) -> FAISS:
    """Load an index created by this application from a validated local path."""
    faiss = dependable_faiss_import()
    serialized = np.frombuffer((path / "index.faiss").read_bytes(), dtype=np.uint8)
    index = faiss.deserialize_index(serialized)
    with (path / "index.pkl").open("rb") as handle:
        docstore, index_to_docstore_id = pickle.load(handle)
    return FAISS(
        embeddings,
        index,
        docstore,
        index_to_docstore_id,
        normalize_L2=normalize_l2,
    )
