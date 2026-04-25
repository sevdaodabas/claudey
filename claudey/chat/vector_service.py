from functools import lru_cache
import re

import chromadb
import requests
from chromadb.config import Settings

OLLAMA_EMBED_URL = "http://claudey_ai:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 180

chroma_client = chromadb.PersistentClient(path="./chroma_db_data",
                                          settings=Settings(anonymized_telemetry=False))
collection = chroma_client.get_or_create_collection(name="university_docs")
session = requests.Session()


def normalize_text(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_embedding_text(title, content):
    title = normalize_text(title)
    content = normalize_text(content)
    return f"{title}. {content}".strip(". ")


def split_text_into_chunks(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Uzun içerikleri daha isabetli retrieval için örtüşmeli parçalara ayır."""
    normalized = normalize_text(text)
    if not normalized:
        return []

    if len(normalized) <= chunk_size:
        return [normalized]

    chunks = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(text_length, start + chunk_size)

        if end < text_length:
            boundary = normalized.rfind(" ", start, end)
            if boundary > start + (chunk_size // 2):
                end = boundary

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(end - overlap, start + 1)

    return chunks


@lru_cache(maxsize=256)
def _get_embedding_cached(processed_text):
    response = session.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": processed_text},
        timeout=(5, 45),
    )
    response.raise_for_status()
    return response.json().get("embedding", [])

def get_embedding(text, is_query=False):
    """Verilen metni Ollama kullanarak sayı dizisine (vektöre) çevirir."""
    normalized = normalize_text(text)
    if not normalized:
        return []

    prefix = "search_query: " if is_query else "search_document: "
    processed_text = prefix + normalized

    try:
        return _get_embedding_cached(processed_text)
    except Exception as e:
        print(f"Embedding Hatası: {e}")
        return []
