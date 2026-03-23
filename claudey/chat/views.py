import re
import requests
import json

from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from .models import ChatMessage
from scraper.models import UniversityData

OLLAMA_URL = "http://claudey_ai:11434/api/chat"
MODEL_NAME = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "Sen Claudey'sin, Acıbadem Üniversitesi'nin resmi yapay zeka asistanısın.\n\n"
    "KESİN KURALLAR:\n"
    "1. YALNIZCA sana verilen bağlam bilgisini kullan. Bağlamda olmayan bilgiyi ASLA uydurma.\n"
    "2. Her zaman akıcı, doğal Türkçe kullan.\n"
    "3. Yanıtını kısa ve net tut.\n"
    "4. Bağlamda bilgi yoksa şunu söyle: 'Bu konuda elimde yeterli bilgi bulunmuyor.'\n"
)

OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.85,
    "num_ctx": 3072,
    "num_predict": 300,
}


def extract_relevant_paragraphs(content, keywords, max_chars=800):
    """İçerikten sorguyla en ilgili paragrafları çıkar."""
    # Satır veya çift newline ile paragraf ayır
    paragraphs = re.split(r'\n+', content)
    # Kısa satırları birleştir
    merged = []
    buffer = []
    for line in paragraphs:
        line = line.strip()
        if not line:
            if buffer:
                merged.append(' '.join(buffer))
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        merged.append(' '.join(buffer))

    if not keywords or not merged:
        return content[:max_chars]

    scored = []
    for para in merged:
        if len(para) < 15:
            continue
        score = sum(1 for kw in keywords if kw.lower() in para.lower())
        if score > 0:
            scored.append((score, para))

    scored.sort(key=lambda x: -x[0])

    if not scored:
        return content[:max_chars]

    result = []
    total = 0
    for _, para in scored:
        if total + len(para) > max_chars:
            remaining = max_chars - total
            if remaining > 80:
                result.append(para[:remaining])
            break
        result.append(para)
        total += len(para)

    return '\n\n'.join(result)


def search_context(user_msg):
    """PostgreSQL full-text search + keyword fallback ile en ilgili içerikleri bul."""
    search_query = SearchQuery(user_msg, search_type='plain', config='simple')

    vector = (
        SearchVector('title', weight='A', config='simple') +
        SearchVector('content', weight='B', config='simple')
    )

    results = list(
        UniversityData.objects
        .annotate(rank=SearchRank(vector, search_query))
        .filter(rank__gte=0.01)
        .order_by('-rank')[:5]
    )

    if not results:
        keywords = [w for w in user_msg.split() if len(w) > 1]
        if keywords:
            query = Q()
            for kw in keywords[:5]:
                query |= Q(title__icontains=kw) | Q(content__icontains=kw)
            results = list(UniversityData.objects.filter(query)[:5])

    return results


def build_context(entries, user_msg):
    """Bulunan kayıtlardan akıllı context oluştur."""
    if not entries:
        return ""

    stop = {'bir', 'bu', 've', 'ile', 'de', 'da', 'mi', 'mu', 'ne', 'mı', 'var', 'ben', 'sen', 'the', 'is', 'are', 'ver', 'nedir', 'nasıl', 'kaç'}
    keywords = [w for w in user_msg.split() if w.lower() not in stop and len(w) > 1]

    parts = []
    for entry in entries[:3]:
        relevant_text = extract_relevant_paragraphs(entry.content, keywords, max_chars=600)
        parts.append(f"[{entry.title}]\n{relevant_text}")

    return "\n\n---\n\n".join(parts)


@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        entries = search_context(user_msg)
        context_text = build_context(entries, user_msg)

        if context_text:
            user_content = (
                f"Aşağıdaki bilgileri kullanarak soruyu yanıtla:\n\n"
                f"{context_text}\n\n"
                f"Soru: {user_msg}"
            )
        else:
            user_content = f"Soru: {user_msg}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": False,
                    "options": OLLAMA_OPTIONS,
                },
                timeout=300
            )
            ai_reply = response.json().get('message', {}).get('content', '').strip()
        except Exception as e:
            print(f"AI Error: {e}")
            ai_reply = "Yapay zeka servisi şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin."

        ChatMessage.objects.create(user_query=user_msg, ai_response=ai_reply)
        return JsonResponse({"reply": ai_reply})


@csrf_exempt
def generate_title(request):
    if request.method == "POST":
        data = json.loads(request.body)
        question = data.get('question', '')
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
                timeout=60
            )
            title = response.json().get('message', {}).get('content', '').strip()
            title = title.strip('"\'').split('\n')[0][:50]
        except Exception:
            title = question[:30]
        return JsonResponse({"title": title})


def home(request):
    return render(request, "chat/home.html")
