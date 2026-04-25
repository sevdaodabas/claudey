from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from scraper.models import UniversityData
from chat.vector_service import (
    build_embedding_text,
    collection,
    get_embedding,
    split_text_into_chunks,
)

@receiver(post_save, sender=UniversityData)
def sync_chromadb_on_save(sender, instance, **kwargs):
    """Kayıt eklendiğinde veya güncellendiğinde parçalı vektörleri ChromaDB'ye aktarır."""
    base_text = build_embedding_text(instance.title, instance.content)
    chunks = split_text_into_chunks(base_text)
    if not chunks:
        return

    existing_ids = collection.get(
        where={"parent_id": str(instance.id)},
        include=[],
    ).get("ids", [])
    if existing_ids:
        collection.delete(ids=existing_ids)

    embeddings = []
    documents = []
    metadatas = []
    ids = []

    for index, chunk in enumerate(chunks):
        vector = get_embedding(chunk)
        if not vector:
            continue

        embeddings.append(vector)
        documents.append(chunk)
        metadatas.append(
            {
                "parent_id": str(instance.id),
                "title": instance.title,
                "url": instance.url,
                "category": instance.category,
                "source": instance.source,
                "level": instance.level,
                "chunk_index": index,
            }
        )
        ids.append(f"{instance.id}:{index}")

    if embeddings:
        collection.upsert(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

@receiver(post_delete, sender=UniversityData)
def sync_chromadb_on_delete(sender, instance, **kwargs):
    """Kayıt silindiğinde ChromaDB'den de siler."""
    existing_ids = collection.get(
        where={"parent_id": str(instance.id)},
        include=[],
    ).get("ids", [])
    if existing_ids:
        collection.delete(ids=existing_ids)
