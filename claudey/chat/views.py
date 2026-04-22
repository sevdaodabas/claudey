import re
import requests
import json

from .vector_service import get_embedding, collection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from .models import ChatMessage
from scraper.models import UniversityData

OLLAMA_URL = "http://claudey_ai:11434/api/chat"
MODEL_NAME = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "Sen Acıbadem Üniversitesi asistanı Claudey'sin. Kısa, net ve doğal Türkçe kullan.\n\n"
    "KURALLAR:\n"
    "1. SOHBET: Teşekkür veya selamlama mesajlarına çok kısa, doğal bir karşılık ver (Örn: 'Rica ederim', 'Sizi dinliyorum.'). Sohbetin başında kendini zaten tanıttın, bu yüzden kendini tekrar tanıtma veya uzun uzun selam verme.\n"
    "2. BİLGİ: Üniversite sorularında SADECE verilen BAĞLAM BİLGİSİ'ni kullan.\n"
    "3. BİLİNMEYEN: Bağlamda cevap yoksa sadece 'Bu konuda elimde yeterli bilgi bulunmuyor.' de."
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


def search_keyword(user_msg):
    """PostgreSQL üzerinde keyword arama yap.

    Önce title'da arama yapar (daha spesifik sayfalar için).
    Sonra content'te arar ama navigasyon sayfalarını filtreler.
    """

    # Stop words ve noktalama temizleme
    stop_words = {'nasıl', 'nedir', 'mi', 'mu', 'mı', 'var', 'için', 'ile', 've', 'bu', 'bir', 'kim', 'nerede', 'ne', 'hakkında', 'hakkinda'}
    clean_msg = re.sub(r'[^\w\s]', ' ', user_msg.lower())
    keywords = [w for w in clean_msg.split() if len(w) > 2 and w not in stop_words]

    if not keywords:
        return []

    from django.db.models import Q

    title_filter = Q()
    for kw in keywords:
        title_filter |= Q(title__icontains=kw)

    title_results = list(
        UniversityData.objects
        .filter(title_filter)
        .exclude(title__iexact='acıbadem üniversitesi')
        .exclude(title__iexact='acibadem universitesi')
        .order_by('-scraped_at')[:10]
    )

    def score_title(entry):
        title_lower = entry.title.lower()
        score = sum(2 if kw in title_lower else 0 for kw in keywords)
        if len(entry.content) > 1000:
            score += 1
        return score

    title_results.sort(key=score_title, reverse=True)

    if title_results:
        return title_results[:5]
    
    content_filter = Q()
    for kw in keywords:
        content_filter |= Q(content__icontains=kw)

    content_results = list(
        UniversityData.objects
        .filter(content_filter)
        .exclude(title__iexact='acıbadem üniversitesi')
        .exclude(title__iexact='acibadem universitesi')
       # .filter(content__length__gt=500)
        .order_by('-scraped_at')[:10]
    )

    if content_results:
        return content_results[:5]

    return []


def search_context(user_msg):
    """Hybrid arama: ChromaDB + PostgreSQL keyword arama."""

    pg_results = search_keyword(user_msg)
    query_vector = get_embedding(user_msg, is_query=True)
    chroma_results = []

    if query_vector:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=5,
            include=['distances', 'metadatas']
        )

        ids_result = results.get('ids', [])
        if ids_result and isinstance(ids_result, list) and len(ids_result) > 0:
            found_ids = ids_result[0] if isinstance(ids_result[0], list) else ids_result
            chroma_entries = UniversityData.objects.filter(id__in=found_ids)
            chroma_results = list(chroma_entries)
 
    seen_ids = set()
    combined_results = []

    for entry in pg_results:
        if entry.id not in seen_ids:
            combined_results.append(entry)
            seen_ids.add(entry.id)

    for entry in chroma_results:
        if entry.id not in seen_ids:
            combined_results.append(entry)
            seen_ids.add(entry.id)

    return combined_results
    


def build_context(entries, user_msg):
    """Bulunan kayıtlardan akıllı context oluştur."""
    if not entries:
        return ""

    stop = {'bir', 'bu', 've', 'ile', 'de', 'da', 'mi', 'mu', 'ne', 'mı', 'var', 'ben', 'sen', 'the', 'is', 'are', 'ver', 'nedir', 'nasıl', 'kaç', 'kim'}
    clean_msg = re.sub(r'[^\w\s]', ' ', user_msg.lower())
    keywords = [w for w in clean_msg.split() if w not in stop and len(w) > 2]

    parts = []
    for entry in entries[:3]:
        relevant_text = extract_relevant_paragraphs(entry.content, keywords, max_chars=800)
        if relevant_text:
            parts.append(f"Kaynak: {entry.title}\n{relevant_text}")

    return "\n\n---\n\n".join(parts)


@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_msg = data.get('message')

        recent_history = list(ChatMessage.objects.order_by('-id')[:4])
        recent_history.reverse() 

        chat_keywords = ['merhaba', 'selam', 'hey', 'teşekkürler', 'teşekkür ederim', 'nasılsın', 'iyiyim']
        is_chat_msg = any(kw in user_msg.lower() for kw in chat_keywords)

        search_query = user_msg

        if not is_chat_msg and len(user_msg.split()) < 3 and recent_history:
            last_user_query = recent_history[-1].user_query
            search_query = f"{last_user_query} {user_msg}"

        if  is_chat_msg:
            entries = []
            context_text = ""
        else:
            entries = search_context(search_query)
            context_text = build_context(entries, user_msg)

        
        if is_chat_msg:
            user_content = (
                f"--- KULLANICI MESAJI ---\n{user_msg}\n\n"
                f"(Sistem Notu: Bu sadece bir nezaket/sohbet mesajı. Kendini tanıtmana gerek yok. "
                f"Teşekkürse sadece 'Rica ederim', selamsa sadece 'Sizi dinliyorum / Nasıl yardımcı olabilirim?' gibi çok kısa, doğal bir cevap ver.)"
            )
        elif context_text:
            user_content = (
                f"--- BAĞLAM BİLGİSİ ---\n{context_text}\n\n"
                f"--- KULLANICI MESAJI ---\n{user_msg}"
            )
        else:
            user_content = (
                f"--- KULLANICI MESAJI ---\n{user_msg}\n\n"
                f"(Sistem Notu: Bu bir üniversite sorusu ancak veritabanında hiçbir bilgi yok. "
                f"SADECE 'Bu konuda elimde yeterli bilgi bulunmuyor.' de ve konuyu kapat.)"
            )


        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        for chat in recent_history:
            messages.append({"role": "user", "content": chat.user_query})
            messages.append({"role": "assistant", "content": chat.ai_response})

        messages.append({"role": "user", "content": user_content})

        print("\n" + "="*50)
        print("💡 RAG BAĞLAM:")
        print(context_text[:200] + "..." if len(context_text) > 200 else context_text)
        print("="*50 + "\n")

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

            response_json = response.json()
            print("\n" + "="*50)
            print(f"DEBUG - OLLAMA YANITI: {response_json}")
            print("="*50 + "\n")

            if "error" in response_json:
                ai_reply = f"Ollama Hatası: {response_json['error']}"
            else:
                ai_reply = response_json.get('message', {}).get('content', '').strip()

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
