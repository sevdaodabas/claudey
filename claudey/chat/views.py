import requests, json
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ChatMessage
from scraper.models import UniversityData
from django.shortcuts import render

STOP_WORDS = {
    'bir', 'bu', 've', 'ile', 'de', 'da', 'mi', 'mu', 'ne', 'ben', 'sen',
    'the', 'is', 'are', 'what', 'how', 'can', 'about', 'hakkında', 'nedir',
    'nasıl', 'için', 'var', 'mı', 'kadar', 'daha', 'çok', 'bilgi', 'ver',
}

@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        keywords = [w for w in user_msg.split() if w.lower() not in STOP_WORDS and len(w) > 2]

        query = Q()
        for keyword in keywords:
            query |= Q(content__icontains=keyword)

        context_entries = UniversityData.objects.filter(query)[:3] if keywords else []
        context_text = "\n\n".join([f"{entry.title}: {entry.content[:2000]}" for entry in context_entries])

        prompt = (
            "You are Claudey, the AI assistant of Acibadem University. "
            "Answer questions using ONLY the provided context below. "
            "Always respond in the same language the user writes in. "
            "If the context does not contain relevant information, say you don't have that information.\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {user_msg}\n"
            "Answer:"
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
            ai_reply = "AI service is currently unavailable. Please try again later."

        ChatMessage.objects.create(user_query=user_msg, ai_response=ai_reply)
        return JsonResponse({"reply": ai_reply})

def home(request):
    return render(request, "chat/home.html")
