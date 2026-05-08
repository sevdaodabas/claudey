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


class VectorServiceHelperTests(TestCase):
    def test_normalize_text_collapses_whitespace(self):
        self.assertEqual(normalize_text("  Bir\n\nmetin\törneği  "), "Bir metin örneği")

    def test_compute_content_hash_is_stable_after_whitespace_normalization(self):
        first = compute_content_hash(" Başlık ", "İçerik\nmetni")
        second = compute_content_hash("Başlık", "İçerik metni")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_build_embedding_text_joins_title_and_content(self):
        self.assertEqual(
            build_embedding_text(" Program ", " Dört yıllık eğitim "),
            "Program. Dört yıllık eğitim",
        )

    def test_split_text_into_chunks_returns_empty_for_blank_text(self):
        self.assertEqual(split_text_into_chunks(" \n\t "), [])

    def test_split_text_into_chunks_uses_overlap(self):
        chunks = split_text_into_chunks("abcdefghij", chunk_size=6, overlap=2)

        self.assertEqual(chunks, ["abcdef", "efghij"])


class ChatHelperTests(TestCase):
    def test_extract_keywords_removes_short_words_and_stop_words(self):
        self.assertEqual(
            views.extract_keywords("Acıbadem Üniversitesi burs imkanları nedir?"),
            ["burs", "imkanları"],
        )

    def test_detect_query_intent_marks_fee_as_admission(self):
        intent = views.detect_query_intent("Tıp fakültesi öğrenim ücreti ne kadar?")

        self.assertTrue(intent["is_fee"])
        self.assertTrue(intent["is_admission"])
        self.assertFalse(intent["is_transport"])

    def test_get_simple_chat_reply_handles_greeting_without_ai(self):
        self.assertEqual(
            views.get_simple_chat_reply("Merhaba"),
            "Merhaba, size nasıl yardımcı olabilirim?",
        )

    def test_fallback_title_from_question_limits_length(self):
        title = views.fallback_title_from_question("x" * 80)

        self.assertEqual(title, "x" * views.TITLE_MAX_LENGTH)

    def test_clean_generated_title_removes_prefix_and_punctuation(self):
        title = views.clean_generated_title('Başlık: "Burs İmkanları"', "Burs var mı?")

        self.assertEqual(title, "Burs İmkanları")

    def test_clean_generated_title_rejects_fee_title_for_location_question(self):
        title = views.clean_generated_title(
            "Öğrenim Ücreti",
            "Acıbadem Üniversitesi nerede bulunuyor?",
        )

        self.assertEqual(title, "Acıbadem Üniversitesi nerede bulunuyor")

    def test_fallback_title_from_question_does_not_split_words(self):
        title = views.fallback_title_from_question(
            "Acıbadem Üniversitesi kampüs konumu ve ulaşım seçenekleri hakkında bilgi verir misin?"
        )

        self.assertEqual(title, "Acıbadem Üniversitesi kampüs konumu ve ulaşım")

    def test_is_greeting_question_detects_short_greeting(self):
        self.assertTrue(views.is_greeting_question("selam"))
        self.assertFalse(views.is_greeting_question("Bilgisayar mühendisliği kaç yıl?"))

    def test_extract_location_context_omits_contact_details(self):
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
    def test_generate_title_returns_fallback_for_invalid_json(self):
        response = self.client.post(
            reverse("generate_title"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"title": "Yeni Sohbet"})

    def test_generate_title_returns_general_chat_for_greeting(self):
        response = self.client.post(
            reverse("generate_title"),
            data=json.dumps({"question": "Merhaba"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Genel Sohbet"})

    @patch("chat.views.requests.post")
    def test_generate_title_falls_back_when_ollama_fails(self, mock_post):
        mock_post.side_effect = RuntimeError("service unavailable")

        response = self.client.post(
            reverse("generate_title"),
            data=json.dumps({"question": "Tıp fakültesi kaç yıl sürer?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Tıp fakültesi kaç yıl sürer"})

    def test_chat_api_rejects_get(self):
        response = self.client.get(reverse("chat_api"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json(), {"reply": "Yalnızca POST destekleniyor."})

    def test_chat_api_rejects_invalid_json(self):
        response = self.client.post(
            reverse("chat_api"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"reply": "Geçersiz istek verisi gönderildi."})

    def test_chat_api_rejects_empty_message(self):
        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps({"message": "   "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"reply": "Lütfen bir mesaj yazın."})

    @patch("chat.views.requests.post")
    def test_chat_api_streams_simple_reply_without_ai_call(self, mock_post):
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
        mock_collection = Mock()
        mock_collection.query.return_value = {
            "documents": [["Program içeriği"]],
            "metadatas": [[{"parent_id": "1", "title": "Program"}]],
            "distances": [[0.42]],
        }

        with (
            patch.object(views, "collection", mock_collection),
            patch.object(views, "get_embedding", return_value=[0.1, 0.2]),
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


class KeywordScoringTests(TestCase):
    def test_keyword_relevance_score_uses_title_url_and_content(self):
        entry = UniversityData(
            title="Burs İmkanları",
            url="https://example.com/burs",
            content="Öğrenciler için burs seçenekleri vardır.",
        )

        self.assertGreater(views.keyword_relevance_score(entry, ["burs"]), 0)

    def test_should_use_vector_search_skips_contact_intents(self):
        intent = views.detect_query_intent("Adres nerede?")

        self.assertFalse(views.should_use_vector_search([], intent))

    def test_should_use_vector_search_uses_vector_for_empty_general_results(self):
        intent = views.detect_query_intent("Robotik laboratuvarı")

        self.assertTrue(views.should_use_vector_search([], intent))

    def test_build_context_deduplicates_vector_chunks_from_keyword_entries(self):
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
