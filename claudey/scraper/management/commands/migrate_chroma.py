"""Geriye uyumluluk: 'migrate_chroma' artık 'reindex_vectors --full' için alias.

Eski betiklerde/CI'da bu komut ismi kullanılmış olabilir; davranışı
korumak için (tüm kayıtları yeniden embed eder) --full ile çağırırız.
Yeni kullanımlarda doğrudan ``python manage.py reindex_vectors`` tercih edin
(varsayılan delta — yalnız değişen sayfalar embed edilir, çok daha hızlı).
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "DEPRECATED: 'reindex_vectors --full' için alias. "
        "Yeni komutu kullanmanız önerilir."
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            "[DEPRECATED] 'migrate_chroma' artık 'reindex_vectors --full' alias'ı. "
            "Yeni komut: python manage.py reindex_vectors  (varsayılan delta — daha hızlı)"
        ))
        call_command("reindex_vectors", full=True)
