import requests, json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ChatMessage
from scraper.models import UniversityData
from django.shortcuts import render

@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        context_obj = UniversityData.objects.filter(content__icontains=user_msg).first()
        context_text = context_obj.content if context_obj else ""

        prompt = (
            "You are a helpful university assistant. "
            "Answer the question based on the provided context. "
            "If the context is empty, answer based on your general knowledge.\n\n"
            f"Context: {context_text}\n"
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
