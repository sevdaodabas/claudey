from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from scraper.models import UniversityData
from chat.vector_service import get_embedding, collection

@receiver(post_save, sender=UniversityData)
def sync_chromadb_on_save(sender, instance, **kwargs):
    """Kayıt eklendiğinde veya güncellendiğinde vektörü ChromaDB'ye aktarır."""
    full_text = f"{instance.title}. {instance.content}"
    vector = get_embedding(full_text)
    
    if vector:
        collection.upsert(
            embeddings=[vector],
            documents=[full_text],
            metadatas=[{"title": instance.title}],
            ids=[str(instance.id)]
        )

@receiver(post_delete, sender=UniversityData)
def sync_chromadb_on_delete(sender, instance, **kwargs):
    """Kayıt silindiğinde ChromaDB'den de siler."""
    collection.delete(ids=[str(instance.id)])