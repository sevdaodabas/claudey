from django.core.management.base import BaseCommand
from scraper.models import UniversityData
from chat.vector_service import (
    build_embedding_text,
    collection,
    get_embedding,
    split_text_into_chunks,
)

class Command(BaseCommand):

    def handle(self, *args, **options):
        docs = UniversityData.objects.all()
        total = docs.count()
        self.stdout.write(f"Toplam {total} kayıt ChromaDB'ye aktarılıyor...")
        
        for idx, doc in enumerate(docs, 1):
            collection.delete(where={"parent_id": str(doc.id)})

            embeddings = []
            documents = []
            metadatas = []
            ids = []

            for chunk_index, chunk in enumerate(
                split_text_into_chunks(build_embedding_text(doc.title, doc.content))
            ):
                vector = get_embedding(chunk)
                if not vector:
                    continue

                embeddings.append(vector)
                documents.append(chunk)
                metadatas.append(
                    {
                        "parent_id": str(doc.id),
                        "title": doc.title,
                        "url": doc.url,
                        "category": doc.category,
                        "source": doc.source,
                        "level": doc.level,
                        "chunk_index": chunk_index,
                    }
                )
                ids.append(f"{doc.id}:{chunk_index}")

            if embeddings:
                collection.upsert(
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )
                self.stdout.write(self.style.SUCCESS(f"[{idx}/{total}] Eklendi: {doc.title[:50]}..."))
            else:
                self.stdout.write(self.style.ERROR(f"[{idx}/{total}] HATA - Vektör alınamadı: {doc.title[:50]}..."))
                
        self.stdout.write(self.style.SUCCESS("Aktarım tamamlandı!"))
