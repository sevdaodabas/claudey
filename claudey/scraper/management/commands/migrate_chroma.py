from django.core.management.base import BaseCommand
from scraper.models import UniversityData
from chat.vector_service import get_embedding, collection

class Command(BaseCommand):

    def handle(self, *args, **options):
        docs = UniversityData.objects.all()
        total = docs.count()
        self.stdout.write(f"Toplam {total} kayıt ChromaDB'ye aktarılıyor...")
        
        for idx, doc in enumerate(docs, 1):
            full_text = f"{doc.title}. {doc.content}"
            vector = get_embedding(full_text)
            
            if vector:
                collection.upsert(
                    embeddings=[vector],
                    documents=[full_text],
                    metadatas=[{"title": doc.title}],
                    ids=[str(doc.id)]
                )
                self.stdout.write(self.style.SUCCESS(f"[{idx}/{total}] Eklendi: {doc.title[:50]}..."))
            else:
                self.stdout.write(self.style.ERROR(f"[{idx}/{total}] HATA - Vektör alınamadı: {doc.title[:50]}..."))
                
        self.stdout.write(self.style.SUCCESS("Aktarım tamamlandı!"))