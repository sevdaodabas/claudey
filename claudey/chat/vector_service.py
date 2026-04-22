import requests
import chromadb
from chromadb.config import Settings

OLLAMA_EMBED_URL = "http://claudey_ai:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

chroma_client = chromadb.PersistentClient(path="./chroma_db_data",
                                          settings=Settings(anonymized_telemetry=False))
collection = chroma_client.get_or_create_collection(name="university_docs")

def get_embedding(text, is_query=False):
    """Verilen metni Ollama kullanarak sayı dizisine (vektöre) çevirir."""

    prefix = "search_query: " if is_query else "search_document: "
    processed_text = prefix + text

    try:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": processed_text},
            timeout=120
        )
        return response.json().get('embedding', [])
    except Exception as e:
        print(f"Embedding Hatası: {e}")
        return []