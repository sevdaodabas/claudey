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
MODEL_NAME = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "Sen Claudey'sin, Acıbadem Üniversitesi'nin resmi yapay zeka asistanısın.\n"
    "Görevin üniversite hakkında sorulan soruları doğru ve anlaşılır şekilde yanıtlamaktır.\n\n"
    "Kurallar:\n"
    "- Yalnızca sana verilen bağlam bilgisini kullan.\n"
    "- Her zaman akıcı, doğal ve anlaşılır Türkçe ile yanıt ver.\n"
    "- Kısa ve öz yanıtlar ver, gereksiz uzatma.\n"
    "- Bağlamda ilgili bilgi yoksa 'Bu konuda elimde bilgi bulunmuyor.' de.\n"
    "- Asla bilgi uydurma.\n"
)

OLLAMA_OPTIONS = {
    "temperature": 0.3,
    "top_p": 0.9,
    "num_ctx": 2048,
    "num_predict": 256,
}


def search_context(user_msg):
    """PostgreSQL full-text search ile en ilgili içerikleri bul."""
    search_query = SearchQuery(user_msg, search_type='plain', config='simple')

    vector = (
        SearchVector('title', weight='A', config='simple') +
        SearchVector('content', weight='B', config='simple')
    )

    results = (
        UniversityData.objects
        .annotate(rank=SearchRank(vector, search_query))
        .filter(rank__gte=0.01)
        .order_by('-rank')[:3]
    )

    if not results:
        keywords = [w for w in user_msg.split() if len(w) > 2]
        if keywords:
            query = Q()
            for kw in keywords[:5]:
                query |= Q(title__icontains=kw) | Q(content__icontains=kw)
            results = UniversityData.objects.filter(query)[:3]

    return results


def build_context_text(entries):
    """Bulunan kayıtlardan yapılandırılmış context metni oluştur."""
    if not entries:
        return ""

    parts = []
    for entry in entries:
        content = entry.content[:500]
        parts.append(f"[{entry.title}]\n{content}")

    return "\n\n---\n\n".join(parts)


@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        entries = search_context(user_msg)
        context_text = build_context_text(entries)

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
                    "options": {"temperature": 0.5, "num_ctx": 512},
                },
                timeout=30
            )
            title = response.json().get('message', {}).get('content', '').strip()
            title = title.strip('"\'').split('\n')[0][:50]
        except Exception:
            title = question[:30]
        return JsonResponse({"title": title})


def home(request):
    return render(request, "chat/home.html")
