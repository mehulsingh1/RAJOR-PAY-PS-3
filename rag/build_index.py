"""
Build vector index from knowledge_base.json into ChromaDB.
Run once (or whenever knowledge_base.json changes) to (re)build the index.
"""

import json

import chromadb
from chromadb.utils import embedding_functions

KB_PATH = "rag/knowledge_base.json"
CHROMA_PATH = "rag/chroma_db"
COLLECTION_NAME = "failure_knowledge_base"

EMBED_MODEL = "all-MiniLM-L6-v2"


def load_kb(path: str = KB_PATH) -> list[dict]:
    with open(path, "r") as f:
        return json.load(f)


def entry_to_text(entry: dict) -> str:
    """Flatten a KB entry into a single text blob for embedding."""
    return (
        f"failure_code: {entry['failure_code']} | stage: {entry['stage']} | "
        f"typical_causes: {entry['typical_causes']} | "
        f"recommended_resolution: {entry['recommended_resolution']} | "
        f"compliance_notes: {entry['compliance_notes']} | "
        f"urgency: {entry['urgency']}"
    )


def build_index():
    kb = load_kb()

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Drop existing collection if present, to allow clean rebuilds
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )

    ids = [entry["failure_code"] for entry in kb]
    documents = [entry_to_text(entry) for entry in kb]
    metadatas = [
        {
            "failure_code": entry["failure_code"],
            "stage": entry["stage"],
            "urgency": entry["urgency"],
        }
        for entry in kb
    ]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    print(f"Indexed {len(kb)} KB entries into ChromaDB at '{CHROMA_PATH}'")
    return collection


if __name__ == "__main__":
    build_index()