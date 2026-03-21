import requests, json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ChatMessage, UniversityData
from django.shortcuts import render

@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        context_obj = UniversityData.objects.filter(content__icontains=user_msg).first()
        context_text = context_obj.content if context_obj else ""

        prompt = f"Context: {context_text}\nQuestion: {user_msg}\nAnswer:"

        try:
            response = requests.post("http://claudey_ai:5000/predict", json={"prompt": prompt}, timeout=300)
            ai_reply = response.json().get('reply')
        except Exception as e:
            print(f"AI Error occurred: {e}")
            ai_reply = "AI service is currently unavailable. Please try again later."

        ChatMessage.objects.create(user_query=user_msg, ai_response=ai_reply)
        return JsonResponse({"reply": ai_reply})

def home(request):
    return render(request, "chat/home.html")
