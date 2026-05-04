from functools import lru_cache
import hashlib
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


def compute_content_hash(title, content):
    """İçerik değişimini tespit etmek için title+content'in deterministik hash'i."""
    payload = f"{normalize_text(title)}\n{normalize_text(content)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


# --- Indexing API ---------------------------------------------------------
#
# Bu yardımcılar UniversityData kayıtlarını ChromaDB'ye yazmak/silmek/yeniden
# inşa etmek için kullanılır. Scraper'lar her kayıt sonrası `index_entry`
# çağırır; toplu reindex_vectors komutu da `reindex_all` kullanır.

def delete_entry_vectors(entry_id):
    """Bir UniversityData kaydının ChromaDB'deki tüm chunk'larını siler."""
    try:
        collection.delete(where={"parent_id": str(entry_id)})
    except Exception as e:
        # ChromaDB chunk yoksa hata atabilir — sessizce geç.
        print(f"delete_entry_vectors({entry_id}): {e}")


def index_entry(entry, force=False):
    """Tek bir UniversityData kaydını chunk'lara böler, embed eder ve ChromaDB'ye
    upsert eder. İçerik değişmemişse (content_hash eşleşiyorsa) atlar.

    Returns: 'indexed' | 'unchanged' | 'empty' | 'failed'
    """
    text = build_embedding_text(entry.title, entry.content)
    if not text:
        delete_entry_vectors(entry.id)
        return "empty"

    new_hash = compute_content_hash(entry.title, entry.content)
    existing_hash = getattr(entry, "content_hash", None)
    if not force and existing_hash == new_hash and existing_hash:
        return "unchanged"

    chunks = split_text_into_chunks(text)
    if not chunks:
        delete_entry_vectors(entry.id)
        return "empty"

    embeddings = []
    documents = []
    metadatas = []
    ids = []

    for chunk_index, chunk in enumerate(chunks):
        vector = get_embedding(chunk)
        if not vector:
            continue
        embeddings.append(vector)
        documents.append(chunk)
        metadatas.append({
            "parent_id": str(entry.id),
            "title": entry.title,
            "url": entry.url,
            "category": entry.category,
            "source": entry.source,
            "level": entry.level,
            "chunk_index": chunk_index,
            "content_hash": new_hash,
        })
        ids.append(f"{entry.id}:{chunk_index}")

    if not embeddings:
        return "failed"

    # Önce eski chunk'ları sil (chunk sayısı azalmışsa orphan kalmasın), sonra yaz.
    delete_entry_vectors(entry.id)
    collection.upsert(
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    # Hash alanı modelde varsa güncelle (caller tarafında save() çağrılır).
    if hasattr(entry, "content_hash"):
        entry.content_hash = new_hash

    return "indexed"


def get_indexed_parent_ids():
    """ChromaDB'de şu an indexlenmiş parent_id setini döndürür (orphan tespiti için)."""
    parent_ids = set()
    try:
        # Tüm metadatayı tek seferde al — koleksiyon büyürse sayfalanabilir.
        result = collection.get(include=["metadatas"])
        for meta in result.get("metadatas") or []:
            pid = meta.get("parent_id")
            if pid:
                parent_ids.add(str(pid))
    except Exception as e:
        print(f"get_indexed_parent_ids: {e}")
    return parent_ids


def prune_orphan_vectors(valid_entry_ids):
    """PostgreSQL'de artık olmayan kayıtların ChromaDB chunk'larını siler.
    valid_entry_ids: DB'deki tüm UniversityData id'lerinin str setı.
    Returns: silinen parent sayısı.
    """
    indexed = get_indexed_parent_ids()
    orphans = indexed - {str(i) for i in valid_entry_ids}
    for parent_id in orphans:
        delete_entry_vectors(parent_id)
    return len(orphans)


def reindex_all(queryset, force=False, on_progress=None):
    """Verilen UniversityData queryset'ini sırayla index'ler.
    on_progress: opsiyonel callable(idx, total, status, entry).
    Returns: dict(indexed=int, unchanged=int, empty=int, failed=int).
    """
    stats = {"indexed": 0, "unchanged": 0, "empty": 0, "failed": 0}
    total = queryset.count()
    for idx, entry in enumerate(queryset.iterator(), 1):
        status = index_entry(entry, force=force)
        stats[status] = stats.get(status, 0) + 1
        if hasattr(entry, "content_hash"):
            try:
                entry.save(update_fields=["content_hash"])
            except Exception:
                # content_hash alanı henüz migration uygulanmadıysa sessizce geç.
                pass
        if on_progress:
            on_progress(idx, total, status, entry)
    return stats
