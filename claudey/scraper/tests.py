from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from .models import UniversityData
from .management.commands import scrape_acu, scrape_bologna


class ScraperHelperTests(TestCase):
    """Scraper yardımcılarının URL filtreleme, kategori ve içerik çıkarımını test eder."""

    def test_scrape_acu_skips_files_and_english_urls(self):
        # Tarayıcı PDF/görsel ve İngilizce sayfaları kuyruğa almamalıdır.
        self.assertTrue(scrape_acu.should_skip_url("https://example.com/file.pdf"))
        self.assertTrue(scrape_acu.should_skip_url("https://example.com/en/page"))
        self.assertFalse(scrape_acu.should_skip_url("https://www.acibadem.edu.tr/iletisim"))

    def test_scrape_acu_extracts_title_table_text_and_category(self):
        # Tablo başlıkları korunursa ücret/kontenjan gibi cevaplarda bağlam bozulmaz.
        html = """
        <html>
          <head><title>Ücretler | Acıbadem</title></head>
          <body>
            <main>
              <h1>Yedek Başlık</h1>
              <table>
                <tr><th>Program</th><th>Ücret</th></tr>
                <tr><td>Tıp</td><td>100 TL</td></tr>
              </table>
              <p>Öğrenim ücretleri hakkında detaylı açıklama metni.</p>
            </main>
          </body>
        </html>
        """
        soup = scrape_acu.BeautifulSoup(html, "lxml")

        title = scrape_acu.extract_title(soup, "https://www.acibadem.edu.tr/aday/ucret")
        content = scrape_acu.extract_main_content(soup, "https://www.acibadem.edu.tr/aday/ucret")

        self.assertEqual(title, "Ücretler")
        self.assertIn("Program | Ücret", content)
        self.assertIn("Program: Tıp; Ücret: 100 TL", content)
        self.assertEqual(scrape_acu.guess_category("https://example.com/aday/kayit"), "admission")

    @patch("scraper.management.commands.scrape_bologna.requests.get")
    def test_scrape_bologna_fetch_content_removes_navigation_noise(self, mock_get):
        # Bologna içerik çıkarımı nav/footer/script gürültüsünü temizlemelidir.
        mock_get.return_value = Mock(
            status_code=200,
            text="""
            <html><body>
              <nav>Menü</nav><script>bad()</script>
              <main>Program hakkında geçerli ve yeterli içerik.</main>
              <footer>Footer</footer>
            </body></html>
            """,
        )

        content = scrape_bologna.fetch_content("https://obs.acibadem.edu.tr/page")

        self.assertIn("Program hakkında geçerli", content)
        self.assertNotIn("Menü", content)
        self.assertNotIn("Footer", content)


class ScrapeAcuCommandTests(TestCase):
    """Ana site scraper komutunun kayıt oluşturma ve update davranışını test eder."""

    def _html(self, paragraph):
        return f"""
        <html>
          <head><title>İletişim | Acıbadem</title></head>
          <body>
            <main>
              <p>{paragraph}</p>
              <a href="/aday/ogrenci">Aday Öğrenci</a>
            </main>
          </body>
        </html>
        """

    @patch("scraper.management.commands.scrape_acu.time.sleep")
    @patch("scraper.management.commands.scrape_acu.requests.get")
    def test_scrape_acu_updates_existing_url_without_reindex(self, mock_get, _mock_sleep):
        # Aynı URL ikinci kez taranınca duplicate yaratmak yerine mevcut kaydı günceller.
        first_text = "Adres bilgisi ve iletişim detayları " * 5
        second_text = "Güncel adres bilgisi ve iletişim detayları " * 5
        mock_get.side_effect = [
            Mock(status_code=200, headers={"Content-Type": "text/html"}, text=self._html(first_text)),
            Mock(status_code=200, headers={"Content-Type": "text/html"}, text=self._html(second_text)),
        ]

        call_command(
            "scrape_acu",
            "--max-pages",
            "1",
            "--delay",
            "0",
            "--no-reindex",
            stdout=StringIO(),
        )
        call_command(
            "scrape_acu",
            "--max-pages",
            "1",
            "--delay",
            "0",
            "--no-reindex",
            stdout=StringIO(),
        )

        self.assertEqual(UniversityData.objects.count(), 1)
        entry = UniversityData.objects.get()
        self.assertIn("Güncel adres", entry.content)
        self.assertEqual(entry.source, "main_site")


class ReindexVectorsCommandTests(TestCase):
    """Reindex komutunun seçenekleri doğru uyguladığını mock'larla test eder."""

    def setUp(self):
        self.main_entry = UniversityData.objects.create(
            title="Ana Site Kaydı",
            url="https://example.com/main",
            content="Ana site içeriği",
            source="main_site",
            content_hash="old-hash",
        )
        self.bologna_entry = UniversityData.objects.create(
            title="Bologna Kaydı",
            url="https://example.com/bologna",
            content="Bologna içeriği",
            source="bologna",
            content_hash="old-hash",
        )

    @patch("scraper.management.commands.reindex_vectors.collection")
    @patch("scraper.management.commands.reindex_vectors.reindex_all")
    def test_reindex_vectors_full_resets_only_selected_source(
        self,
        mock_reindex_all,
        mock_collection,
    ):
        # --full ve --source birlikte kullanıldığında sadece seçilen kaynak sıfırlanır.
        mock_collection.count.return_value = 0
        mock_reindex_all.return_value = {
            "indexed": 1,
            "unchanged": 0,
            "empty": 0,
            "failed": 0,
        }

        call_command(
            "reindex_vectors",
            "--full",
            "--source",
            "bologna",
            stdout=StringIO(),
        )

        self.main_entry.refresh_from_db()
        self.bologna_entry.refresh_from_db()
        queryset = mock_reindex_all.call_args.args[0]

        self.assertEqual(self.main_entry.content_hash, "old-hash")
        self.assertEqual(self.bologna_entry.content_hash, "")
        self.assertEqual(list(queryset.values_list("source", flat=True)), ["bologna"])

    @patch("scraper.management.commands.reindex_vectors.prune_orphan_vectors")
    @patch("scraper.management.commands.reindex_vectors.collection")
    @patch("scraper.management.commands.reindex_vectors.reindex_all")
    def test_reindex_vectors_prune_passes_valid_database_ids(
        self,
        mock_reindex_all,
        mock_collection,
        mock_prune_orphan_vectors,
    ):
        # --prune ChromaDB temizliği için mevcut PostgreSQL id'lerini gönderir.
        mock_collection.count.return_value = 2
        mock_reindex_all.return_value = {
            "indexed": 0,
            "unchanged": 2,
            "empty": 0,
            "failed": 0,
        }
        mock_prune_orphan_vectors.return_value = 1

        call_command("reindex_vectors", "--prune", stdout=StringIO())

        valid_ids = mock_prune_orphan_vectors.call_args.args[0]

        self.assertEqual(
            valid_ids,
            {str(self.main_entry.id), str(self.bologna_entry.id)},
        )

    @patch("scraper.management.commands.reindex_vectors.collection")
    @patch("scraper.management.commands.reindex_vectors.reindex_all")
    def test_reindex_vectors_limit_passes_limited_queryset(
        self,
        mock_reindex_all,
        mock_collection,
    ):
        # --limit yalnız istenen sayıda kaydı reindex_all'a göndermelidir.
        mock_collection.count.return_value = 0
        mock_reindex_all.return_value = {
            "indexed": 0,
            "unchanged": 1,
            "empty": 0,
            "failed": 0,
        }

        call_command("reindex_vectors", "--limit", "1", stdout=StringIO())

        queryset = mock_reindex_all.call_args.args[0]

        self.assertEqual(list(queryset.values_list("id", flat=True)), [self.main_entry.id])
