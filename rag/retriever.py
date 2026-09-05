"""
Retrieval interface for the Diagnose node.
Loads the persisted Chroma collection and returns relevant KB context
for a given failure_code.
"""

import chromadb
from chromadb.utils import embedding_functions

CHROMA_PATH = "rag/chroma_db"
COLLECTION_NAME = "failure_knowledge_base"
EMBED_MODEL = "all-MiniLM-L6-v2"

_client = None
_collection = None


def _get_collection():
    """Lazy-load the Chroma client + collection (avoids reload on every call)."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=CHROMA_PATH)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        )
        try:
            _collection = _client.get_collection(
                name=COLLECTION_NAME, embedding_function=embed_fn,
            )
        except Exception as e:  # index not built yet
            raise RuntimeError(
                "Knowledge-base index not found — run `python rag/build_index.py` "
                "(or use AGENT_MODE=playbook, which needs no index)."
            ) from e
    return _collection


def retrieve_context(failure_code: str, k: int = 2) -> str:
    """
    Retrieve top-k relevant KB entries for a failure_code.
    Returns a single formatted string ready to inject into the LLM prompt.
    """
    collection = _get_collection()

    # Query using the failure_code itself as the semantic query.
    # This also naturally surfaces related codes if the exact one isn't in KB.
    results = collection.query(
        query_texts=[failure_code],
        n_results=k,
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    if not documents:
        return "No relevant knowledge base context found."

    context_parts = []
    for doc, meta in zip(documents, metadatas):
        context_parts.append(f"[{meta['failure_code']}] {doc}")

    return "\n\n".join(context_parts)


if __name__ == "__main__":
    # Quick manual test
    test_codes = ["insufficient_funds", "mandate_lapsed", "invoice_unpaid"]
    for code in test_codes:
        print(f"--- Query: {code} ---")
        print(retrieve_context(code, k=1))
        print()