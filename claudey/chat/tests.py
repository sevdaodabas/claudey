import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from scraper.models import UniversityData

from . import views
from .vector_service import (
    build_embedding_text,
    compute_content_hash,
    normalize_text,
    split_text_into_chunks,
)


class MockOllamaStream:
    """Ollama'nın streaming response context manager davranışını taklit eder."""

    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def iter_lines(self, decode_unicode=False):
        return iter(self.lines)


class VectorServiceHelperTests(TestCase):
    """Vektör metni hazırlama, hash ve chunk yardımcılarını test eder."""

    def test_normalize_text_collapses_whitespace(self):
        # Embedding öncesi boşluk ve satır sonları tek boşluğa indirilmelidir.
        self.assertEqual(normalize_text("  Bir\n\nmetin\törneği  "), "Bir metin örneği")

    def test_compute_content_hash_is_stable_after_whitespace_normalization(self):
        # Aynı içerik farklı boşluklarla gelse bile aynı hash üretilmelidir.
        first = compute_content_hash(" Başlık ", "İçerik\nmetni")
        second = compute_content_hash("Başlık", "İçerik metni")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_build_embedding_text_joins_title_and_content(self):
        # Başlık ve içerik embedding metnine temiz tek cümle gibi eklenmelidir.
        self.assertEqual(
            build_embedding_text(" Program ", " Dört yıllık eğitim "),
            "Program. Dört yıllık eğitim",
        )

    def test_split_text_into_chunks_returns_empty_for_blank_text(self):
        # Boş içerik vektör indeksine gereksiz chunk üretmemelidir.
        self.assertEqual(split_text_into_chunks(" \n\t "), [])

    def test_split_text_into_chunks_uses_overlap(self):
        # Ardışık chunk'lar bağlam kopmasın diye overlap ile bölünmelidir.
        chunks = split_text_into_chunks("abcdefghij", chunk_size=6, overlap=2)

        self.assertEqual(chunks, ["abcdef", "efghij"])


class ChatHelperTests(TestCase):
    """Chat yardımcılarının intent, başlık ve özel bağlam ayıklama davranışını test eder."""

    def test_extract_keywords_removes_short_words_and_stop_words(self):
        # Aramada işe yaramayan kısa kelimeler ve stop word'ler çıkarılmalıdır.
        self.assertEqual(
            views.extract_keywords("Acıbadem Üniversitesi burs imkanları nedir?"),
            ["burs", "imkanları"],
        )

    def test_detect_query_intent_marks_fee_as_admission(self):
        # Ücret sorusu hem fee hem admission intent'i olarak işaretlenmelidir.
        intent = views.detect_query_intent("Tıp fakültesi öğrenim ücreti ne kadar?")

        self.assertTrue(intent["is_fee"])
        self.assertTrue(intent["is_admission"])
        self.assertFalse(intent["is_transport"])

    def test_get_simple_chat_reply_handles_greeting_without_ai(self):
        # Kısa selamlaşmalar Ollama çağrısı yapmadan sabit cevap döndürmelidir.
        self.assertEqual(
            views.get_simple_chat_reply("Merhaba"),
            "Merhaba, size nasıl yardımcı olabilirim?",
        )

    def test_fallback_title_from_question_limits_length(self):
        # Fallback başlık çok uzunsa güvenli maksimum uzunluğa kısaltılmalıdır.
        title = views.fallback_title_from_question("x" * 80)

        self.assertEqual(title, "x" * views.TITLE_MAX_LENGTH)

    def test_clean_generated_title_removes_prefix_and_punctuation(self):
        # Modelin döndürdüğü Başlık: gibi prefix ve tırnaklar temizlenmelidir.
        title = views.clean_generated_title('Başlık: "Burs İmkanları"', "Burs var mı?")

        self.assertEqual(title, "Burs İmkanları")

    def test_clean_generated_title_rejects_fee_title_for_location_question(self):
        # Konum sorusuna ücret başlığı gelirse soru tabanlı fallback kullanılmalıdır.
        title = views.clean_generated_title(
            "Öğrenim Ücreti",
            "Acıbadem Üniversitesi nerede bulunuyor?",
        )

        self.assertEqual(title, "Acıbadem Üniversitesi nerede bulunuyor")

    def test_fallback_title_from_question_does_not_split_words(self):
        # Başlık kısaltılırken kelimeler ortadan bölünmemelidir.
        title = views.fallback_title_from_question(
            "Acıbadem Üniversitesi kampüs konumu ve ulaşım seçenekleri hakkında bilgi verir misin?"
        )

        self.assertEqual(title, "Acıbadem Üniversitesi kampüs konumu ve ulaşım")

    def test_is_greeting_question_detects_short_greeting(self):
        # Başlık üretiminde kısa selamlaşma ile gerçek soru ayırt edilmelidir.
        self.assertTrue(views.is_greeting_question("selam"))
        self.assertFalse(views.is_greeting_question("Bilgisayar mühendisliği kaç yıl?"))

    def test_extract_location_context_omits_contact_details(self):
        # Adres bağlamı çıkarılırken telefon/e-posta gibi iletişim bilgileri atlanmalıdır.
        content = "\n".join(
            [
                "Adres: Kayışdağı Caddesi No:32 Ataşehir İstanbul",
                "Telefon: 0216 000 00 00",
                "E-posta: test@example.com",
            ]
        )

        self.assertEqual(
            views.extract_location_context(content),
            "Adres: Kayışdağı Caddesi No:32 Ataşehir İstanbul",
        )


class ChatViewTests(TestCase):
    """Chat endpoint'inin API, RAG payload ve streaming hata davranışlarını test eder."""

    def test_generate_title_returns_fallback_for_invalid_json(self):
        # Bozuk JSON gönderilirse title endpoint'i güvenli varsayılan başlık döndürür.
        response = self.client.post(
            reverse("generate_title"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"title": "Yeni Sohbet"})

    def test_generate_title_returns_general_chat_for_greeting(self):
        # Selamlama mesajı için Ollama'ya gitmeden genel sohbet başlığı üretilir.
        response = self.client.post(
            reverse("generate_title"),
            data=json.dumps({"question": "Merhaba"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Genel Sohbet"})

    @patch("chat.views.requests.post")
    def test_generate_title_falls_back_when_ollama_fails(self, mock_post):
        # Title üretim servisi hata verirse soru metninden fallback başlık çıkarılır.
        mock_post.side_effect = RuntimeError("service unavailable")

        response = self.client.post(
            reverse("generate_title"),
            data=json.dumps({"question": "Tıp fakültesi kaç yıl sürer?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Tıp fakültesi kaç yıl sürer"})

    def test_chat_api_rejects_get(self):
        # Chat endpoint'i sadece POST kabul eder; GET istekleri reddedilir.
        response = self.client.get(reverse("chat_api"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json(), {"reply": "Yalnızca POST destekleniyor."})

    def test_chat_api_rejects_invalid_json(self):
        # Bozuk JSON gövdesi kullanıcıya anlaşılır hata mesajı döndürmelidir.
        response = self.client.post(
            reverse("chat_api"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"reply": "Geçersiz istek verisi gönderildi."})

    def test_chat_api_rejects_empty_message(self):
        # Boş mesajlar model çağrısı yapılmadan validasyon hatası almalıdır.
        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "   "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"reply": "Lütfen bir mesaj yazın."})

    @patch("chat.views.requests.post")
    def test_chat_api_streams_simple_reply_without_ai_call(self, mock_post):
        # Teşekkür gibi basit mesajlar tek parça stream edilir ve AI servisine gitmez.
        user = get_user_model().objects.create_user(
            username="hasan",
            password="strong-test-password",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Teşekkürler"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "Rica ederim.")
        mock_post.assert_not_called()
        self.assertEqual(user.chat_messages.count(), 1)

    def test_search_vector_chunks_returns_normalized_results(self):
        # ChromaDB cevabı chat tarafının beklediği sade chunk listesine çevrilmelidir.
        mock_collection = Mock()
        mock_collection.query.return_value = {
            "documents": [["Program içeriği"]],
            "metadatas": [[{"parent_id": "1", "title": "Program"}]],
            "distances": [[0.42]],
        }

        with (
            patch("chat.views.collection", mock_collection),
            patch("chat.views.get_embedding", return_value=[0.1, 0.2]),
        ):
            self.assertEqual(
                views.search_vector_chunks("program"),
                [
                    {
                        "parent_id": "1",
                        "title": "Program",
                        "content": "Program içeriği",
                        "distance": 0.42,
                    }
                ],
            )

    def test_home_template_contains_frontend_streaming_and_storage_hooks(self):
        # Frontend JS test altyapısı yok; kritik streaming/localStorage parçaları template'te korunuyor mu bakar.
        response = self.client.get(reverse("home"))
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("response.body.getReader()", html)
        self.assertIn("new TextDecoder('utf-8')", html)
        self.assertIn("localStorage.setItem(storageKey", html)
        self.assertIn("fetch('/generate-title/'", html)

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context")
    def test_chat_api_sends_rag_context_to_ollama(self, mock_search_context, mock_post):
        # RAG sonucu varsa bağlamın Ollama payload'ına eklendiğini kontrol eder.
        user = get_user_model().objects.create_user(
            username="rag-user",
            password="strong-test-password",
        )
        self.client.force_login(user)
        entry = UniversityData(
            id=10,
            title="Bilgisayar Mühendisliği",
            url="https://example.com/bilgisayar",
            content="Bilgisayar Mühendisliği Programı dört yıllık bir lisans programıdır.",
        )
        mock_search_context.return_value = ([entry], [])
        mock_post.return_value = MockOllamaStream(
            [
                json.dumps(
                    {
                        "message": {"content": "Program dört yıllıktır."},
                        "done": True,
                    }
                )
            ]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Bilgisayar mühendisliği kaç yıl?"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")
        payload = mock_post.call_args.kwargs["json"]
        user_content = payload["messages"][-1]["content"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "Program dört yıllıktır.")
        self.assertIn("--- BAĞLAM BİLGİSİ ---", user_content)
        self.assertIn("Bilgisayar Mühendisliği", user_content)
        self.assertEqual(payload["options"], views.OLLAMA_OPTIONS)
        self.assertEqual(user.chat_messages.count(), 1)

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_sends_no_context_instruction_when_rag_is_empty(
        self,
        _mock_search_context,
        mock_post,
    ):
        # Bağlam bulunamazsa modele yalnız "bilgi yok" cevabı için sistem notu gider.
        mock_post.return_value = MockOllamaStream(
            [
                json.dumps(
                    {
                        "message": {"content": "Bu konuda elimde yeterli bilgi bulunmuyor."},
                        "done": True,
                    }
                )
            ]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Robotik laboratuvarı nerede?"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")
        payload = mock_post.call_args.kwargs["json"]
        user_content = payload["messages"][-1]["content"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "Bu konuda elimde yeterli bilgi bulunmuyor.")
        self.assertIn("Bağlam yok", user_content)
        self.assertEqual(payload["options"], views.CHAT_OLLAMA_OPTIONS)

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_does_not_save_guest_messages(self, _mock_search_context, mock_post):
        # Misafir kullanıcıların konuşması DB'ye yazılmaz; sadece frontend localStorage kullanır.
        mock_post.return_value = MockOllamaStream(
            [json.dumps({"message": {"content": "Yanıt"}, "done": True})]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Kampüs hakkında bilgi"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "Yanıt")
        self.assertEqual(views.ChatMessage.objects.count(), 0)

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_adds_recent_authenticated_history_to_payload(
        self,
        _mock_search_context,
        mock_post,
    ):
        # Login kullanıcısının son geçmişi Ollama mesajlarına sıralı şekilde eklenir.
        user = get_user_model().objects.create_user(
            username="history-user",
            password="strong-test-password",
        )
        views.ChatMessage.objects.create(
            user=user,
            user_query="Burs var mı?",
            ai_response="Burs bilgisi vardır.",
        )
        self.client.force_login(user)
        mock_post.return_value = MockOllamaStream(
            [json.dumps({"message": {"content": "Yeni yanıt"}, "done": True})]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Peki ücretler?"}),
            content_type="application/json",
        )

        b"".join(response.streaming_content)
        payload_messages = mock_post.call_args.kwargs["json"]["messages"]
        contents = [message["content"] for message in payload_messages]

        self.assertIn("Burs var mı?", contents)
        self.assertIn("Burs bilgisi vardır.", contents)

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_ignores_invalid_stream_lines_and_returns_error_chunk(
        self,
        _mock_search_context,
        mock_post,
    ):
        # Bozuk NDJSON satırları atlanır; Ollama error chunk'ı kullanıcıya aktarılır.
        mock_post.return_value = MockOllamaStream(
            [
                "{",
                json.dumps({"error": "model not found"}),
            ]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Program bilgisi"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body, "Ollama Hatası: model not found")

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_removes_bad_opening_salutation_from_stream(
        self,
        _mock_search_context,
        mock_post,
    ):
        # Model yanlış hitapla başlarsa ilk hitap kısmı stream'den temizlenir.
        mock_post.return_value = MockOllamaStream(
            [
                json.dumps(
                    {
                        "message": {
                            "content": "Sayın Bölüm Başkanı,\nBilgisayar programı dört yıllıktır."
                        },
                        "done": True,
                    }
                )
            ]
        )

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Bilgisayar mühendisliği kaç yıl?"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(body, "Bilgisayar programı dört yıllıktır.")

    @patch("chat.views.requests.post")
    @patch("chat.views.search_context", return_value=([], []))
    def test_chat_api_streams_fallback_when_ollama_fails(self, _mock_search_context, mock_post):
        # Ollama bağlantısı koparsa kullanıcıya kontrollü fallback döner.
        mock_post.side_effect = RuntimeError("ollama down")

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "Robotik laboratuvarı nerede?"}),
            content_type="application/json",
        )

        body = b"".join(response.streaming_content).decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            body,
            "Yapay zeka servisi şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
        )

    @patch("chat.views.requests.post")
    def test_generate_title_sends_expected_prompt_and_cleans_response(self, mock_post):
        # Bilgi sorusunda title endpoint'i kısa başlık prompt'unu gönderip cevabı temizler.
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {"content": 'Başlık: "Burs İmkanları"'}
        }
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("generate_title"),
            data=json.dumps({"question": "Burs imkanları nelerdir?"}),
            content_type="application/json",
        )

        payload = mock_post.call_args.kwargs["json"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Burs İmkanları"})
        self.assertFalse(payload["stream"])
        self.assertIn("en fazla 4 kelime", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][-1]["content"], "Soru: Burs imkanları nelerdir?")


class KeywordScoringTests(TestCase):
    """Keyword skorlaması, vektör arama kararı ve bağlam birleştirmeyi test eder."""

    def test_keyword_relevance_score_uses_title_url_and_content(self):
        # Anahtar kelime başlık, URL veya içerikte geçiyorsa pozitif skor üretmelidir.
        entry = UniversityData(
            title="Burs İmkanları",
            url="https://example.com/burs",
            content="Öğrenciler için burs seçenekleri vardır.",
        )

        self.assertGreater(views.keyword_relevance_score(entry, ["burs"]), 0)

    def test_should_use_vector_search_skips_contact_intents(self):
        # Adres/iletişim intent'lerinde vektör arama gürültü eklememelidir.
        intent = views.detect_query_intent("Adres nerede?")

        self.assertFalse(views.should_use_vector_search([], intent))

    def test_should_use_vector_search_uses_vector_for_empty_general_results(self):
        # Genel soruda keyword sonucu yoksa semantik arama devreye girmelidir.
        intent = views.detect_query_intent("Robotik laboratuvarı")

        self.assertTrue(views.should_use_vector_search([], intent))

    def test_build_context_deduplicates_vector_chunks_from_keyword_entries(self):
        # Aynı kayıttan gelen keyword ve vector sonucu bağlama iki kez eklenmemelidir.
        entry = UniversityData(
            id=1,
            title="Bilgisayar Mühendisliği",
            url="https://example.com/program",
            content="Bilgisayar mühendisliği dört yıllık bir programdır.",
        )
        vector_chunk = {
            "parent_id": "1",
            "title": "Bilgisayar Mühendisliği",
            "content": "Tekrar eden içerik",
            "distance": 0.2,
        }

        context = views.build_context(
            [entry],
            [vector_chunk],
            "Bilgisayar mühendisliği kaç yıl?",
        )

        self.assertIn("Bilgisayar Mühendisliği", context)
        self.assertNotIn("Tekrar eden içerik", context)

    def test_fee_search_prioritizes_tuition_page_over_scholarship_page(self):
        # Ücret sorusunda gerçek ücret sayfası burs sayfasının önüne geçmelidir.
        fee_entry = UniversityData.objects.create(
            title="Öğrenim Ücretleri",
            url="https://example.com/aday/ogrenim-ucretleri",
            content="Tıp fakültesi öğrenim ücreti tablosu ve ödeme bilgileri.",
            category="admission",
            source="main_site",
        )
        UniversityData.objects.create(
            title="Burs İmkanları",
            url="https://example.com/aday/burs",
            content="Tıp fakültesi öğrencileri için burs ve indirim seçenekleri.",
            category="admission",
            source="main_site",
        )

        results = views.search_keyword("Tıp fakültesi öğrenim ücreti ne kadar?")

        self.assertEqual(results[0], fee_entry)
