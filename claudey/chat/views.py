import requests
import json

from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from .models import ChatMessage
from scraper.models import UniversityData

STOP_WORDS = {
    'bir', 'bu', 've', 'ile', 'de', 'da', 'mi', 'mu', 'ne', 'ben', 'sen',
    'the', 'is', 'are', 'what', 'how', 'can', 'about', 'hakkında', 'nedir',
    'nasıl', 'için', 'var', 'mı', 'kadar', 'daha', 'çok', 'bilgi', 'ver',
    'bana', 'söyle', 'anlat', 'hangi', 'neler', 'olan', 'lütfen', 'merhaba',
}


@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        keywords = [w for w in user_msg.split() if w.lower() not in STOP_WORDS and len(w) > 2]

        query = Q()
        for keyword in keywords:
            query |= Q(content__icontains=keyword) | Q(title__icontains=keyword)

        context_entries = UniversityData.objects.filter(query)[:3] if keywords else []
        context_text = "\n\n".join([f"{entry.title}: {entry.content[:2000]}" for entry in context_entries])

        prompt = (
            "Sen Claudey'sin, Acıbadem Üniversitesi'nin yapay zeka asistanısın. "
            "Soruları YALNIZCA aşağıda verilen bağlam bilgisini kullanarak yanıtla. "
            "Her zaman akıcı ve doğal bir Türkçe ile yanıt ver. "
            "Yanıtlarında İngilizce kelimeler kullanma. "
            "Bağlamda ilgili bilgi yoksa, bu konuda bilgin olmadığını kibarca belirt.\n\n"
            f"Bağlam:\n{context_text}\n\n"
            f"Soru: {user_msg}\n"
            "Yanıt:"
        )

        try:
            response = requests.post(
                "http://claudey_ai:11434/api/generate",
                json={"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False},
                timeout=300
            )
            ai_reply = response.json().get('response', '').strip()
        except Exception as e:
            print(f"AI Error occurred: {e}")
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
                "http://claudey_ai:11434/api/generate",
                json={
                    "model": "qwen2.5:1.5b",
                    "prompt": (
                        "Aşağıdaki soruya dayanarak çok kısa bir sohbet başlığı oluştur. "
                        "En fazla 4-5 kelime olsun. Türkçe yaz. "
                        "Sadece başlığı yaz, başka bir şey yazma.\n\n"
                        f"Soru: {question}\n"
                        "Başlık:"
                    ),
                    "stream": False
                },
                timeout=30
            )
            title = response.json().get('response', '').strip()
            title = title.strip('"\'').split('\n')[0][:50]
        except Exception:
            title = question[:30]
        return JsonResponse({"title": title})


def home(request):
    return render(request, "chat/home.html")
