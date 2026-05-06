"""UniversityData kayıtlarını ChromaDB ile senkronize eder.

Varsayılan davranış (delta): yalnızca content_hash'i değişmiş veya hiç
indexlenmemiş kayıtları embed eder. Hızlı ve maliyet açısından düşük.

Bayraklar:
- ``--full``  Tüm kayıtların hash'ini sıfırlar; her kayıt yeniden embed edilir.
              (İlk kurulumda veya embedding modeli değiştiğinde kullanın.)
- ``--prune`` PostgreSQL'de artık olmayan kayıtların ChromaDB chunk'larını siler.
- ``--source main_site|bologna`` Yalnızca belirli kaynaktan gelen kayıtları işler.
- ``--limit N`` İlk N kaydı işler (test için).

Eski ``migrate_chroma`` komutu hâlâ çalışır ama bu komut tercih edilmelidir;
aynı işi delta + prune + ilerleme istatistikleriyle yapar.
"""

import time

from django.core.management.base import BaseCommand
from chat.vector_service import (
    collection,
    prune_orphan_vectors,
    reindex_all,
)
from scraper.models import UniversityData


class Command(BaseCommand):
    help = (
        "UniversityData kayıtlarını ChromaDB'ye senkronize eder. "
        "Varsayılan: delta (yalnızca değişenler). --full ile tüm kayıtlar yeniden embed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Tüm kayıtları yeniden embed et (content_hash sıfırlanır).",
        )
        parser.add_argument(
            "--prune",
            action="store_true",
            help="PG'de artık olmayan kayıtların ChromaDB chunk'larını sil.",
        )
        parser.add_argument(
            "--source",
            choices=["main_site", "bologna"],
            help="Yalnızca belirli kaynaktan gelen kayıtları işle.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="İlk N kaydı işle (test için).",
        )

    def handle(self, *args, **options):
        full = options["full"]
        prune = options["prune"]
        source = options.get("source")
        limit = options.get("limit")

        queryset = UniversityData.objects.all().order_by("id")
        if source:
            queryset = queryset.filter(source=source)
        if limit:
            queryset = queryset[:limit]

        if full:
            # Tüm content_hash'leri sıfırla — index_entry hepsini yeniden embed eder.
            updated = queryset.update(content_hash="")
            self.stdout.write(
                self.style.WARNING(
                    f"--full: {updated} kaydın content_hash'i sıfırlandı, hepsi yeniden embed edilecek."
                )
            )

        total = queryset.count()
        before_chunks = collection.count()
        self.stdout.write(
            f"Toplam {total} kayıt işlenecek. ChromaDB şu an {before_chunks} chunk içeriyor."
        )
        start = time.time()

        last_print = [0]

        def on_progress(idx, total, status, entry):
            # Her 10 kayıtta veya değişen kayıt başına satır yaz.
            should_print = status in ("indexed", "failed", "empty") or idx - last_print[0] >= 10 or idx == total
            if not should_print:
                return
            last_print[0] = idx
            style = {
                "indexed": self.style.SUCCESS,
                "unchanged": self.style.NOTICE,
                "empty": self.style.WARNING,
                "failed": self.style.ERROR,
            }.get(status, self.style.NOTICE)
            self.stdout.write(
                style(f"[{idx:4d}/{total}] {status:9s} {entry.title[:60]}")
            )

        stats = reindex_all(queryset, force=False, on_progress=on_progress)

        elapsed = time.time() - start
        self.stdout.write(self.style.SUCCESS("\n=== Reindex Özet ==="))
        self.stdout.write(f"  Yeni/Güncel embed:  {stats['indexed']}")
        self.stdout.write(f"  Değişmemiş (skip):  {stats['unchanged']}")
        self.stdout.write(f"  Boş içerik:         {stats['empty']}")
        self.stdout.write(f"  Başarısız:          {stats['failed']}")
        self.stdout.write(f"  Süre:               {elapsed:.1f}s")

        if prune:
            valid_ids = set(
                str(i) for i in UniversityData.objects.values_list("id", flat=True)
            )
            removed = prune_orphan_vectors(valid_ids)
            if removed:
                self.stdout.write(
                    self.style.SUCCESS(f"  Prune: {removed} orphan kayıt temizlendi.")
                )
            else:
                self.stdout.write(self.style.NOTICE("  Prune: orphan yok."))

        after_chunks = collection.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nChromaDB chunk sayısı: {before_chunks} -> {after_chunks}"
            )
        )
