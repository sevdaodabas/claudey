import json
import re

import requests
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from .models import ChatMessage
from .rag_config import (
    CHAT_KEYWORDS,
    INTENT_HINTS,
    INTENT_PRIORITY_FILTERS,
    INTENT_PROMPT_NOTES,
    NOISY_URL_HINTS,
    STOP_WORDS,
)
from .vector_service import collection, get_embedding
from scraper.models import UniversityData

OLLAMA_URL = "http://claudey_ai:11434/api/chat"
MODEL_NAME = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "Sen Acıbadem Üniversitesi asistanı Claudey'sin. Kısa, net ve doğal Türkçe kullan.\n\n"
    "KURALLAR:\n"
    "1. SOHBET: Teşekkür veya selamlama mesajlarına çok kısa, doğal bir karşılık ver (Örn: 'Rica ederim', 'Sizi dinliyorum.'). Sohbetin başında kendini zaten tanıttın, bu yüzden kendini tekrar tanıtma veya uzun uzun selam verme.\n"
    "2. BİLGİ: Üniversite sorularında SADECE verilen BAĞLAM BİLGİSİ'ni kullan.\n"
    "3. ADRES: Kullanıcı yalnız adres veya konum soruyorsa sadece adres ver; telefon, e-posta, ulaşım tarifi veya ek bilgi verme.\n"
    "4. KALİTE: Bağlamdaki bilgileri birleştirerek cevap ver; bağlamda olmayan ayrıntı, tarih, ücret, kontenjan, hat veya kişi adı uydurma. Markdown başlıkları kullanma; düz metin veya kısa maddelerle yaz.\n"
    "5. BİLİNMEYEN: Bağlamda cevap yoksa sadece 'Bu konuda elimde yeterli bilgi bulunmuyor.' de."
)

OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.85,
    "num_ctx": 3072,
    "num_predict": 420,
}

TITLE_MAX_LENGTH = 50
VECTOR_DISTANCE_LIMIT = 1.2
MIN_STRONG_KEYWORD_SCORE = 1.6
FEE_HINTS = ("ücret", "ucret", "fiyat", "öğrenim ücreti", "ogrenim ucreti")
SCHOLARSHIP_HINTS = ("burs", "indirim")


def get_or_create_session_key(request):
    """Misafir sohbetlerini birbirinden ayırmak için oturum anahtarı sağlar."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_message_queryset(request):
    """Hesaplı kullanıcı için sohbet geçmişi döndürür."""
    if request.user.is_authenticated:
        return ChatMessage.objects.filter(user=request.user)
    return ChatMessage.objects.none()


def has_hint(text, intent_name):
    """Metinde verilen intent'e ait ipuçlarından biri geçiyorsa True döndürür."""
    return any(hint in text for hint in INTENT_HINTS[intent_name])


def extract_keywords(text):
    """Mesajı sadeleştirip anlamlı arama anahtar kelimelerini çıkarır."""
    clean_msg = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return [w for w in clean_msg.split() if len(w) > 2 and w not in STOP_WORDS]


def detect_query_intent(user_msg):
    """Kullanıcı mesajının hangi soru tipine ait olduğunu kaba kurallarla sınıflandırır."""
    text = (user_msg or "").lower()
    intent = {
        "is_location": has_hint(text, "location"),
        "is_contact": has_hint(text, "contact"),
        "is_transport": has_hint(text, "transport"),
        "is_admission": has_hint(text, "admission"),
        "is_program": has_hint(text, "program"),
        "is_life": has_hint(text, "life"),
    }
    intent["is_fee"] = any(hint in text for hint in FEE_HINTS)
    intent["is_scholarship"] = any(hint in text for hint in SCHOLARSHIP_HINTS)
    intent["is_contact"] = intent["is_contact"] or intent["is_location"]
    if intent["is_transport"]:
        intent["is_location"] = False
        intent["is_contact"] = True
    if intent["is_fee"]:
        intent["is_admission"] = True
    if intent["is_life"]:
        intent["is_location"] = False
        intent["is_contact"] = has_hint(text, "contact")
    return intent


def keyword_relevance_score(entry, keywords):
    """Anahtar kelimelerin başlık, URL ve içerikte geçmesine göre temel bir skor üretir."""
    title_lower = entry.title.lower()
    url_lower = entry.url.lower()
    content_lower = entry.content.lower()
    score = 0.0

    for kw in keywords:
        if kw in title_lower:
            score += 1.5
        if kw in url_lower:
            score += 1.2
        if kw in content_lower:
            score += 0.35

    return score


def score_entry_for_intent(entry, intent):
    """Kaydın mevcut kullanıcı niyetine ne kadar uygun olduğunu ek kurallarla puanlar."""
    title_lower = entry.title.lower()
    url_lower = entry.url.lower()
    content_lower = entry.content.lower()
    score = 0.0

    if any(hint in url_lower for hint in NOISY_URL_HINTS):
        score -= 0.6

    if entry.category == "contact":
        score += 0.2

    if intent["is_location"] or intent["is_contact"]:
        if "ulasim" in url_lower or "ulaşım" in title_lower:
            score += 1.5
        if "iletisim" in url_lower or "iletişim" in title_lower:
            score += 1.0
        if "kayışdağı" in content_lower or "kayisdagi" in content_lower:
            score += 2.0
        if "ataşehir" in content_lower or "atasehir" in content_lower:
            score += 2.0
        if "istanbul" in content_lower:
            score += 1.0
        if "0216" in content_lower:
            score += 0.5

    if intent["is_transport"]:
        if "ulasim" in url_lower or "ulaşım" in title_lower:
            score += 2.4
        if any(token in content_lower for token in ("metroyla", "otobüsle", "otobusle", "metro hattı", "metro hatti", "durağı", "duragi")):
            score += 2.0
        if any(token in content_lower for token in ("küçükbakkalköy", "kucukbakkalkoy", "kozyatağı", "kozyatagi", "kadıköy", "kadikoy", "üsküdar", "uskudar")):
            score += 1.5

    if intent["is_admission"]:
        if entry.category == "admission":
            score += 1.6
        if intent["is_fee"]:
            if any(token in title_lower for token in ("öğrenim ücret", "ogrenim ucret", "ücretleri", "ucretleri")):
                score += 3.0
            if any(token in url_lower for token in ("ogrenim-ucret", "ucretleri", "ucret")):
                score += 2.4
            if "burs" in title_lower and not intent["is_scholarship"]:
                score -= 2.2
        if any(token in url_lower for token in ("aday", "kayit", "ucret", "burs", "puan", "kontenjan", "basvuru")):
            score += 1.0
        if any(token in title_lower for token in ("ücret", "ucret", "burs", "başvuru", "basvuru", "kayıt", "kayit")):
            score += 0.8

    if intent["is_program"]:
        if entry.category in ("program", "course", "staff"):
            score += 1.5
        if entry.source == "bologna":
            score += 1.2
        if any(token in url_lower for token in ("akademik", "lisans", "onlisans", "lisansustu", "mufredat", "ders", "akademik-kadro")):
            score += 0.9
        if any(token in title_lower for token in ("program", "bölüm", "bolum", "fakülte", "fakulte", "müfredat", "mufredat")):
            score += 0.7

    if intent["is_life"]:
        if entry.category == "general":
            score += 1.2
        if any(token in url_lower for token in ("acuda-yasam", "ogrenci", "kampus", "yurt", "spor", "kutuphane", "erasmus")):
            score += 1.0
        if any(token in title_lower for token in ("kampüs", "kampus", "konaklama", "spor", "kulüp", "kulup", "öğrenci", "ogrenci")):
            score += 0.7

    return score


def build_keyword_filter(keywords, include_url=True):
    """Anahtar kelimeler için title/content ve isteğe bağlı URL tabanlı Django filtresi kurar."""
    from django.db.models import Q

    keyword_filter = Q()
    for kw in keywords:
        condition = Q(title__icontains=kw) | Q(content__icontains=kw)
        if include_url:
            condition |= Q(url__icontains=kw)
        keyword_filter |= condition
    return keyword_filter


def get_priority_queryset(intent, keyword_filter):
    """Intent'e göre önce bakılacak yüksek öncelikli kayıt kümesini döndürür."""
    from django.db.models import Q

    if intent["is_location"] or intent["is_contact"]:
        contact_filter = (
            Q(category="contact") |
            Q(title__icontains="iletişim") |
            Q(title__icontains="iletisim") |
            Q(title__icontains="ulaşım") |
            Q(title__icontains="ulasim") |
            Q(url__icontains="iletisim") |
            Q(url__icontains="ulasim") |
            Q(url__icontains="kampus") |
            Q(url__icontains="kampüs")
        )
        return (
            UniversityData.objects
            .filter(contact_filter)
            .exclude(url__icontains="/akademik/")
            .order_by("-scraped_at")[:INTENT_PRIORITY_FILTERS["contact"]["limit"]]
        )

    if intent["is_admission"]:
        if intent["is_fee"] and not intent["is_scholarship"]:
            fee_filter = (
                Q(title__icontains="ücret") |
                Q(title__icontains="ucret") |
                Q(title__icontains="öğrenim") |
                Q(title__icontains="ogrenim") |
                Q(url__icontains="ucret") |
                Q(url__icontains="ogrenim-ucret")
            )
            return (
                UniversityData.objects
                .filter(fee_filter & keyword_filter)
                .order_by("-scraped_at")[:INTENT_PRIORITY_FILTERS["admission"]["limit"]]
            )

        return (
            UniversityData.objects
            .filter(Q(category="admission") & keyword_filter)
            .order_by("-scraped_at")[:INTENT_PRIORITY_FILTERS["admission"]["limit"]]
        )

    if intent["is_program"]:
        return (
            UniversityData.objects
            .filter(Q(category__in=["program", "course", "staff"]) & keyword_filter)
            .order_by("-scraped_at")[:INTENT_PRIORITY_FILTERS["program"]["limit"]]
        )

    if intent["is_life"]:
        return (
            UniversityData.objects
            .filter(Q(category__in=["general", "contact"]) & keyword_filter)
            .order_by("-scraped_at")[:INTENT_PRIORITY_FILTERS["life"]["limit"]]
        )

    return None


def get_intent_priority_results(intent, keywords):
    """Öncelikli queryset sonucunu skorlayıp en güçlü aday kayıtları seçer."""
    keyword_filter = build_keyword_filter(keywords)
    queryset = get_priority_queryset(intent, keyword_filter)
    if queryset is None:
        return []

    results = list(queryset)
    for entry in results:
        entry.title_hit_count = sum(1 for kw in keywords if kw in entry.title.lower())
        entry.match_score = score_entry_for_intent(entry, intent) + keyword_relevance_score(entry, keywords)

    results.sort(key=lambda entry: entry.match_score, reverse=True)
    return [entry for entry in results if getattr(entry, "match_score", 0) > 0][:4]


def extract_relevant_paragraphs(content, keywords, max_chars=800):
    """İçerikten sorguyla en ilgili paragrafları çıkar."""
    paragraphs = re.split(r"\n+", content)
    merged = []
    buffer = []
    for line in paragraphs:
        line = line.strip()
        if not line:
            if buffer:
                merged.append(" ".join(buffer))
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        merged.append(" ".join(buffer))

    if not keywords or not merged:
        return content[:max_chars]

    scored = []
    for para in merged:
        if len(para) < 15:
            continue
        score = sum(1 for kw in keywords if kw.lower() in para.lower())
        if score > 0:
            scored.append((score, para))

    scored.sort(key=lambda item: -item[0])
    if not scored:
        return content[:max_chars]

    result = []
    total = 0
    for _, para in scored:
        paragraph_text = (
            extract_keyword_window(para, keywords, max_chars - total)
            if len(para) > max_chars - total
            else para
        )
        if total + len(paragraph_text) > max_chars:
            remaining = max_chars - total
            if remaining > 80:
                result.append(extract_keyword_window(para, keywords, remaining))
            break
        result.append(paragraph_text)
        total += len(paragraph_text)

    return "\n\n".join(result)


def extract_keyword_window(text, keywords, max_chars):
    """Uzun tek paragraflarda sayfa başı yerine eşleşen terimlerin çevresini döndürür."""
    if not text or max_chars <= 0:
        return ""

    if len(text) <= max_chars:
        return text

    lower_text = text.lower()
    candidate_positions = []
    for keyword in keywords:
        keyword_lower = keyword.lower()
        position = lower_text.find(keyword_lower)
        if position >= 0:
            candidate_positions.append(position)

    if not candidate_positions:
        return text[:max_chars].strip()

    best_start = 0
    best_score = -1
    for position in candidate_positions:
        start = max(0, position - (max_chars // 3))
        end = min(len(text), start + max_chars)
        start = max(0, end - max_chars)
        window = lower_text[start:end]
        score = sum(1 for keyword in keywords if keyword.lower() in window)
        if score > best_score:
            best_score = score
            best_start = start

    snippet = text[best_start:best_start + max_chars].strip()
    if "|" in snippet and "|" in text[:500]:
        table_header = text[:min(360, text.find("|") + 260)].strip()
        if table_header and table_header not in snippet:
            remaining = max_chars - len(table_header) - 5
            snippet = f"{table_header}\n...\n{snippet[:remaining].strip()}" if remaining > 80 else snippet
    if best_start > 0:
        snippet = "..." + snippet
    if best_start + max_chars < len(text):
        snippet += "..."
    return snippet


def extract_location_context(content, max_chars=320):
    """Adres sorularında sadece konum/adres odaklı satırları bırakır."""
    if not content:
        return ""

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    location_markers = (
        "kampüs", "kampus", "cad.", "caddesi", "sokak", "mah.", "mahalle",
        "no:", "ataşehir", "atasehir", "istanbul", "adres",
    )
    blocked_markers = (
        "telefon", "e-posta", "eposta", "mail", "@", "ulaşım", "ulasim",
        "metroyla", "otobüsle", "otobusle", "çağrı merkezi", "cagri merkezi",
    )

    selected = []
    for line in lines:
        lower_line = line.lower()
        if any(marker in lower_line for marker in blocked_markers):
            continue
        if any(marker in lower_line for marker in location_markers):
            selected.append(line)

    if not selected:
        return ""

    result = " ".join(selected)
    return result[:max_chars].strip()


def extract_transport_context(content, max_chars=650):
    """Ulaşım sorularında sadece yol tarifi odaklı satırları bırakır."""
    if not content:
        return ""

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    transport_markers = (
        "ulaşım", "ulasim", "metroyla", "otobüsle", "otobusle", "metro hattı",
        "metro hatti", "istasyonu", "durağı", "duragi", "yürüyerek", "yuruyerek",
        "kadıköy", "kadikoy", "üsküdar", "uskudar", "küçükbakkalköy", "kucukbakkalkoy",
        "kozyatağı", "kozyatagi", "m8", "m4", "19k", "19y", "19v", "19s", "19t", "14a", "11t", "320a",
    )
    blocked_markers = (
        "telefon", "e-posta", "eposta", "mail", "@", "çağrı merkezi", "cagri merkezi",
        "öğrenci işleri", "ogrenci isleri", "mali işler", "mali isler",
    )

    selected = []
    for line in lines:
        lower_line = line.lower()
        if any(marker in lower_line for marker in blocked_markers):
            continue
        if any(marker in lower_line for marker in transport_markers):
            selected.append(line)

    if not selected:
        return ""

    result = " ".join(selected)
    return result[:max_chars].strip()


def get_context_extractor(intent):
    """Intent'e göre özel bağlam ayıklayıcıyı seçer."""
    if intent["is_transport"]:
        return extract_transport_context
    if intent["is_location"]:
        return extract_location_context
    return None


def search_keyword(user_msg):
    """Önce tam metin arama, sonra keyword fallback ile aday kayıtları bulur."""
    keywords = extract_keywords(user_msg)
    intent = detect_query_intent(user_msg)
    priority_results = get_intent_priority_results(intent, keywords)
    if priority_results:
        return priority_results

    if not keywords:
        return []

    query_text = " ".join(keywords)
    search_vector = (
        SearchVector("title", weight="A", config="simple") +
        SearchVector("content", weight="B", config="simple")
    )
    search_query = SearchQuery(query_text, config="simple", search_type="plain")

    candidates = list(
        UniversityData.objects
        .annotate(rank=SearchRank(search_vector, search_query))
        .filter(rank__gte=0.03)
        .exclude(title__iexact="acıbadem üniversitesi")
        .exclude(title__iexact="acibadem universitesi")
        .order_by("-rank", "-scraped_at")[:8]
    )

    for entry in candidates:
        title_lower = entry.title.lower()
        entry.title_hit_count = sum(1 for kw in keywords if kw in title_lower)
        entry.match_score = (
            float(getattr(entry, "rank", 0)) +
            (entry.title_hit_count * 0.15) +
            score_entry_for_intent(entry, intent)
        )

    candidates.sort(key=lambda entry: entry.match_score, reverse=True)
    if candidates:
        return candidates[:5]

    keyword_filter = build_keyword_filter(keywords, include_url=False)
    fallback_results = list(
        UniversityData.objects
        .filter(keyword_filter)
        .exclude(title__iexact="acıbadem üniversitesi")
        .exclude(title__iexact="acibadem universitesi")
        .order_by("-scraped_at")[:6]
    )

    for entry in fallback_results:
        title_lower = entry.title.lower()
        entry.title_hit_count = sum(1 for kw in keywords if kw in title_lower)
        entry.match_score = (entry.title_hit_count * 0.2) + score_entry_for_intent(entry, intent)

    fallback_results.sort(key=lambda entry: entry.match_score, reverse=True)
    return fallback_results[:5]


def search_vector_chunks(user_msg, n_results=4):
    """Vektör aramayı parça düzeyinde yaparak daha doğru bağlam döndürür."""
    query_vector = get_embedding(user_msg, is_query=True)
    if not query_vector:
        return []

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["distances", "metadatas", "documents"],
    )

    documents = results.get("documents", [[]])
    metadatas = results.get("metadatas", [[]])
    distances = results.get("distances", [[]])

    chunks = []
    for document, metadata, distance in zip(documents[0], metadatas[0], distances[0]):
        if not document or not metadata:
            continue

        chunks.append(
            {
                "parent_id": metadata.get("parent_id"),
                "title": metadata.get("title", "Bilinmeyen Kaynak"),
                "content": document,
                "distance": distance,
            }
        )

    return chunks


def should_use_vector_search(pg_results, intent):
    """Keyword sonucu zayıfsa semantik aramayı ek bağlam olarak devreye alır."""
    if intent["is_location"] or intent["is_contact"] or intent["is_transport"]:
        return False

    if not pg_results:
        return True

    top_result = pg_results[0]
    top_score = getattr(top_result, "match_score", 0)
    strong_title_match = getattr(top_result, "title_hit_count", 0) >= 2

    if strong_title_match and top_score >= MIN_STRONG_KEYWORD_SCORE:
        return False

    return len(pg_results) < 2 or top_score < MIN_STRONG_KEYWORD_SCORE


def search_context(user_msg):
    """Hybrid arama: hızlı keyword arama + gerektiğinde parça bazlı vektör arar."""
    pg_results = search_keyword(user_msg)
    intent = detect_query_intent(user_msg)
    vector_results = search_vector_chunks(user_msg, n_results=5) if should_use_vector_search(pg_results, intent) else []

    return pg_results, vector_results


def build_context(keyword_entries, vector_chunks, user_msg, context_query=None):
    """Bulunan kayıt ve chunk'ları modelin kullanacağı kısa bir bağlam metnine dönüştürür."""
    if not keyword_entries and not vector_chunks:
        return ""

    retrieval_text = context_query or user_msg
    keywords = extract_keywords(retrieval_text)
    intent = detect_query_intent(retrieval_text)
    context_extractor = get_context_extractor(intent)

    parts = []
    seen_keys = set()
    seen_parent_ids = set()

    for entry in keyword_entries[:3]:
        relevant_text = (
            context_extractor(entry.content)
            if context_extractor
            else extract_relevant_paragraphs(entry.content, keywords, max_chars=1200)
        )
        if relevant_text:
            parts.append(f"Kaynak: {entry.title}\nURL: {entry.url}\n{relevant_text}")
            seen_keys.add(str(entry.id))
            seen_parent_ids.add(str(entry.id))

    for chunk in vector_chunks:
        parent_id = str(chunk.get("parent_id") or "")
        if parent_id and parent_id in seen_parent_ids:
            continue

        key = f"{chunk.get('parent_id')}:{chunk.get('content')[:80]}"
        if key in seen_keys:
            continue

        distance = chunk.get("distance")
        if distance is not None and distance > VECTOR_DISTANCE_LIMIT:
            continue

        if context_extractor:
            max_chars = 450 if intent["is_transport"] else 220
            snippet = context_extractor(chunk.get("content", ""), max_chars=max_chars)
        else:
            snippet = extract_relevant_paragraphs(chunk.get("content", ""), keywords, max_chars=500)
        if not snippet:
            continue

        parts.append(f"Kaynak: {chunk.get('title')}\n{snippet}")
        seen_keys.add(key)
        if parent_id:
            seen_parent_ids.add(parent_id)

        if len(parts) >= 4:
            break

    return "\n\n---\n\n".join(parts)


def build_extra_note(intent):
    """Bazı intent'ler için prompt'a eklenecek ek yönlendirme notunu döndürür."""
    if intent["is_fee"]:
        return INTENT_PROMPT_NOTES["fee"]
    if intent["is_transport"]:
        return INTENT_PROMPT_NOTES["transport"]
    if intent["is_location"]:
        return INTENT_PROMPT_NOTES["location"]
    return ""


def get_simple_chat_reply(user_msg):
    """Selamlama ve teşekkür gibi basit sohbetleri model çağırmadan yanıtla."""
    text = (user_msg or "").lower()

    if "teşekkür" in text or "tesekkur" in text or "sağ ol" in text or "sag ol" in text:
        return "Rica ederim."

    if "nasılsın" in text or "nasilsin" in text:
        return "İyiyim, teşekkür ederim. Size nasıl yardımcı olabilirim?"

    if "merhaba" in text or "selam" in text or text.strip() == "hey":
        return "Merhaba, nasıl yardımcı olabilirim?"

    if text.strip() in {"iyiyim", "iyi"}:
        return "Harika. Size nasıl yardımcı olabilirim?"

    return None


@csrf_exempt
def chat_api(request):
    """Kullanıcı mesajını işler, uygun RAG bağlamını kurar ve AI yanıtını JSON olarak döner."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"reply": "Geçersiz istek verisi gönderildi."}, status=400)

        user_msg = (data.get("message") or "").strip()
        if not user_msg:
            return JsonResponse({"reply": "Lütfen bir mesaj yazın."}, status=400)

        recent_history = list(get_message_queryset(request).order_by("-id")[:4])
        recent_history.reverse()

        is_chat_msg = any(kw in user_msg.lower() for kw in CHAT_KEYWORDS)
        simple_chat_reply = get_simple_chat_reply(user_msg) if is_chat_msg else None
        if simple_chat_reply:
            if request.user.is_authenticated:
                ChatMessage.objects.create(
                    user=request.user,
                    user_query=user_msg,
                    ai_response=simple_chat_reply,
                )
            return JsonResponse({"reply": simple_chat_reply})

        search_query = user_msg
        if not is_chat_msg and len(user_msg.split()) < 3 and recent_history:
            last_user_query = recent_history[-1].user_query
            search_query = f"{last_user_query} {user_msg}"

        intent = detect_query_intent(user_msg)

        if is_chat_msg:
            keyword_entries = []
            vector_chunks = []
            context_text = ""
        else:
            try:
                keyword_entries, vector_chunks = search_context(search_query)
                context_text = build_context(keyword_entries, vector_chunks, user_msg, context_query=search_query)
            except Exception as e:
                print(f"RAG Error: {e}")
                keyword_entries = []
                vector_chunks = []
                context_text = ""

        if is_chat_msg:
            user_content = (
                f"--- KULLANICI MESAJI ---\n{user_msg}\n\n"
                f"(Sistem Notu: Bu sadece bir nezaket/sohbet mesajı. Kendini tanıtmana gerek yok. "
                f"Teşekkürse sadece 'Rica ederim', selamsa sadece 'Sizi dinliyorum / Nasıl yardımcı olabilirim?' gibi çok kısa, doğal bir cevap ver.)"
            )
        elif context_text:
            extra_note = build_extra_note(intent)
            note_suffix = f"\n\n(Sistem Notu: {extra_note})" if extra_note else ""
            user_content = (
                f"--- BAĞLAM BİLGİSİ ---\n{context_text}\n\n"
                f"--- KULLANICI MESAJI ---\n{user_msg}"
                f"{note_suffix}"
            )
        else:
            user_content = (
                f"--- KULLANICI MESAJI ---\n{user_msg}\n\n"
                f"(Sistem Notu: Bu bir üniversite sorusu ancak veritabanında hiçbir bilgi yok. "
                f"SADECE 'Bu konuda elimde yeterli bilgi bulunmuyor.' de ve konuyu kapat.)"
            )

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for chat in recent_history[-2:]:
            messages.append({"role": "user", "content": chat.user_query})
            messages.append({"role": "assistant", "content": chat.ai_response})
        messages.append({"role": "user", "content": user_content})

        print("\n" + "=" * 50)
        print("💡 RAG BAĞLAM:")
        print(context_text[:200] + "..." if len(context_text) > 200 else context_text)
        print("=" * 50 + "\n")

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": False,
                    "options": OLLAMA_OPTIONS,
                },
                timeout=300,
            )

            response_json = response.json()
            print("\n" + "=" * 50)
            print(f"DEBUG - OLLAMA YANITI: {response_json}")
            print("=" * 50 + "\n")

            if "error" in response_json:
                ai_reply = f"Ollama Hatası: {response_json['error']}"
            else:
                ai_reply = response_json.get("message", {}).get("content", "").strip()

        except Exception as e:
            print(f"AI Error: {e}")
            ai_reply = "Yapay zeka servisi şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin."

        if request.user.is_authenticated:
            ChatMessage.objects.create(
                user=request.user,
                user_query=user_msg,
                ai_response=ai_reply,
            )
        return JsonResponse({"reply": ai_reply})


def fallback_title_from_question(question):
    """AI başlık üretemediğinde ilk sorudan güvenli bir başlık çıkarır."""
    title = re.sub(r"\s+", " ", question or "").strip()
    title = title.strip("\"'`“”‘’.,!?;:-")
    if not title:
        return "Yeni Sohbet"
    return title[:TITLE_MAX_LENGTH].strip()


def clean_generated_title(title, question):
    """AI'dan gelen başlığı temizler; geçersizse soru tabanlı başlığa döner."""
    title = re.sub(r"\s+", " ", title or "").strip()
    title = title.strip("\"'`“”‘’ ")
    title = re.sub(r"^(başlık|baslik|title)\s*:\s*", "", title, flags=re.IGNORECASE).strip()
    title = title.splitlines()[0].strip(" -•\t") if title else ""

    if not title or len(title) < 3:
        return fallback_title_from_question(question)

    return title[:TITLE_MAX_LENGTH].strip()


@csrf_exempt
def generate_title(request):
    """Verilen soru için kısa bir sohbet başlığı üretip JSON olarak döner."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"title": "Yeni Sohbet"}, status=400)

        question = data.get("question", "")
        title = fallback_title_from_question(question)

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "Verilen soruya dayanarak çok kısa bir sohbet başlığı oluştur. En fazla 4-5 kelime. Türkçe yaz. Sadece başlığı yaz."},
                        {"role": "user", "content": question},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.5, "num_ctx": 512, "num_predict": 20},
                },
                timeout=60,
            )
            response.raise_for_status()
            generated_title = response.json().get("message", {}).get("content", "")
            title = clean_generated_title(generated_title, question)
        except Exception:
            title = fallback_title_from_question(question)
        return JsonResponse({"title": title})


def home(request):
    stored_messages = []
    if request.user.is_authenticated:
        messages = list(get_message_queryset(request).order_by("-timestamp")[:20])
        messages.reverse()
        for message in messages:
            stored_messages.extend([
                {"text": message.user_query, "sender": "user"},
                {"text": message.ai_response, "sender": "bot"},
            ])

    return render(
        request,
        "chat/home.html",
        {
            "initial_messages": stored_messages,
            "storage_key": (
                f"claudey_chats_user_{request.user.id}"
                if request.user.is_authenticated
                else "claudey_chats_guest"
            ),
        },
    )
