from pathlib import Path

from langchain_community.vectorstores import FAISS

from app.semantic.embeddings import FakeEmbeddingProvider, LangChainEmbeddingAdapter
from app.semantic.faiss_io import load_faiss_local, save_faiss_local


def test_faiss_round_trip_supports_unicode_windows_paths(tmp_path: Path) -> None:
    embeddings = LangChainEmbeddingAdapter(FakeEmbeddingProvider())
    store = FAISS.from_texts(["Python API testing"], embeddings, normalize_L2=True)
    unicode_path = tmp_path / "中文向量索引"

    save_faiss_local(store, unicode_path)
    loaded = load_faiss_local(unicode_path, embeddings, normalize_l2=True)

    assert loaded.similarity_search("Python", k=1)[0].page_content == "Python API testing"
