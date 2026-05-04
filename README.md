# Claudey — Acıbadem Üniversitesi AI Asistanı

Claudey, Acıbadem Üniversitesi hakkındaki soruları yanıtlayan Türkçe bir RAG (Retrieval-Augmented Generation) sohbet uygulamasıdır. Üniversitenin kurumsal sitesi ve Bologna bilgi sisteminden taranmış verileri PostgreSQL (full-text search) + ChromaDB (vektör arama) üzerinde tutar; Ollama üzerinde çalışan **Qwen2.5-3B** modeline akış (streaming) modunda cevap ürettirir.

## Özellikler

- **Streaming yanıtlar** — `chat_api` artık `StreamingHttpResponse` döner, Ollama'dan gelen her token üretildiği anda tarayıcıya akar; kullanıcı cevabın oluşmasını canlı izler.
- **Hibrit RAG** — Önce niyet (intent) sınıflandırması, ardından PostgreSQL FTS; zayıf eşleşmelerde ChromaDB vektör araması ile takviye.
- **Profilli LLM çağrıları** — Bilgi cevapları için geniş bağlamlı profil (`num_ctx=3072`, `num_predict=700`), selamlama / "bilgim yok" gibi yollar için küçük ve hızlı profil (`num_ctx=512`, `num_predict=80`).
- **Model RAM'de tutuluyor** — `keep_alive=30m` ile model bellekten boşaltılmıyor; ardışık isteklerde ilk-token gecikmesi (TTFT) ciddi düşüyor.
- **Akıllı sohbet başlığı** — Selamlama / teşekkür mesajlarında LLM'e gitmeden "Genel Sohbet"; bilgi sorularında few-shot prompt'la Title Case başlık (ör. "Burs İmkânları").
- **Üniversite adı kilidi** — Sistem promptu modelin başka üniversite adı (Akdeniz, İstanbul vb.) üretmesini engelliyor.
- **Auth ile sohbet geçmişi** — Kayıtlı kullanıcılar için `ChatMessage` tablosuna kayıt; misafirler için yalnız `localStorage`.
- **Polished UI** — Mesaj baloncuklarına giriş animasyonu, input focus halkası, koyu temaya uygun ince scrollbar, aktif sohbet vurgusu.

## Mimari

```
┌────────────────────────────────────────────────────────────┐
│                       Docker Compose                       │
│                                                            │
│  ┌────────────┐   ┌────────────┐   ┌────────────────────┐  │
│  │  Django    │   │ PostgreSQL │   │ Ollama (claudey_ai)│  │
│  │  (web)     │──▶│   (db)     │   │  Qwen2.5-3B        │  │
│  │  :8000     │   │   :5432    │◀──│  :11434            │  │
│  │            │   │            │   │                    │  │
│  │ Chat API ──┼───┼─ FTS arama │   │ /api/chat (stream) │  │
│  │ ChromaDB   │   │ Scraper DB │   │ nomic-embed-text   │  │
│  │ Vector RAG │   │ Chat hist. │   │                    │  │
│  └────────────┘   └────────────┘   └────────────────────┘  │
│                                                            │
│  Volumes: postgres_data · ollama_data · chroma_db_data     │
└────────────────────────────────────────────────────────────┘
```

### Servisler

| Servis      | Container       | Teknoloji                           | Görevi                                  |
|-------------|-----------------|-------------------------------------|-----------------------------------------|
| `web`       | `acu_chat_app`  | Django 5.x, Python 3.12             | UI, REST API, RAG, scraper komutları    |
| `db`        | `acuchat_db`    | PostgreSQL 15 Alpine                | Veri + full-text search                 |
| `ai_engine` | `claudey_ai`    | Ollama + Qwen2.5-3B + nomic-embed   | Sohbet LLM'i + embedding modeli         |

Host portları:
- **8500** → web (`docker-compose.yml` içinde `8500:8000`)
- **11434** → Ollama API
- DB containera özel ağda kalır, host'a expose edilmez.

## İlk Kurulum (Sıfırdan)

### Gereksinimler

- Docker Desktop / Docker Engine + Docker Compose v2
- En az **4 GB boş RAM** (Qwen2.5-3B + embedding modeli için)
- İlk çalıştırmada model indirmek için internet (~1.9 GB Qwen + ~270 MB nomic-embed-text)

### Adım adım

```bash
# 1) Repo'yu klonla
git clone https://github.com/sevdaodabas/claudey.git
cd claudey

# 2) .env dosyasını proje kök dizininde oluştur (içeriği aşağıda)

# 3) Container'ları build et + ayağa kaldır
docker compose up -d --build

# 4) Model hazır mı bekle (ilk çalıştırmada ~1.9 GB indirme)
docker logs claudey_ai --tail 5
#    "Model is ready." mesajını gör

# 5) Veritabanı migration'larını uygula
docker exec acu_chat_app python manage.py migrate

# 6) Admin kullanıcısı oluştur (.env içindeki DJANGO_SUPERUSER_* değerlerini kullanır)
docker exec acu_chat_app python manage.py createsuperuser --noinput

# 7) Veritabanını doldur (scraper'lar)
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

Aç:
- Web: <http://localhost:8500>
- Admin: <http://localhost:8500/admin/>

### `.env` örneği

Proje kök dizinine (`claudey/.env`) şu içerik:

```env
DEBUG=True
SECRET_KEY=buraya-guclu-bir-anahtar-yazin
ALLOWED_HOSTS=*

POSTGRES_NAME=claudey_db
POSTGRES_USER=claudey_db
POSTGRES_PASSWORD=claudeyy123
POSTGRES_HOST=db
POSTGRES_PORT=5432

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@claudey.com
DJANGO_SUPERUSER_PASSWORD=claudey2026
```

> **Port notu:** Container içinde Django 8000'de çalışır; host tarafında **8500'e** maplenmiştir (Windows 11'in 7980-8079 aralığını Hyper-V için rezerv etmesi nedeniyle). Linux/macOS'ta isterseniz `docker-compose.yml` içindeki `"8500:8000"` satırını `"8000:8000"` yapabilirsiniz.

## Günlük Kullanım (Build Sonrası Başlatma)

Repo bir kez build edildikten sonra her gün aşağıdaki tek komut yeterli:

```bash
docker compose up -d
```

Tüm servisler arka planda başlar. Birkaç saniye sonra:

```bash
# (opsiyonel) Servislerin ayakta olduğunu doğrula
docker compose ps

# (opsiyonel) Model henüz yüklendi mi diye bak
docker logs claudey_ai --tail 5
```

Tarayıcı: <http://localhost:8500>

### Yeni migration eklenmişse

```bash
docker exec acu_chat_app python manage.py migrate
```

### Veriyi tazelemek istersen

```bash
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

### Servisleri durdurma / kaldırma

```bash
docker compose stop          # durdur (veri/volume kalır)
docker compose down          # container'ları kaldır (volume kalır)
docker compose down -v       # DİKKAT: volume'ları da siler — DB ve model gider
```

## Sık Kullanılan Komutlar

```bash
docker compose ps                                # servislerin durumu
docker compose logs -f web                       # Django canlı log
docker compose logs -f ai_engine                 # Ollama canlı log
docker compose restart web                       # Django'yu yeniden başlat
docker exec -it acu_chat_app python manage.py shell    # Django shell
docker exec claudey_ai ollama list               # yüklü modelleri listele
docker exec acuchat_db psql -U claudey_db -d claudey_db \
  -c "SELECT COUNT(*) FROM scraper_universitydata"     # taranan kayıt sayısı
```

## Sorun Giderme

| Belirti | Çözüm |
|--------|-------|
| `bind: An attempt was made to access a socket in a way forbidden...` | Host portu kullanılıyor / Windows tarafından rezerve. `docker-compose.yml`'de host portunu değiştirin (örn. `"8600:8000"`). |
| Cevap gelmiyor / çok yavaş | `docker logs claudey_ai --tail 20` ile model durumunu kontrol et. Soğuk başlatmada model RAM'e ~30 sn'de yüklenir. `keep_alive=30m` sonrasında ardışık istekler hızlı olur. |
| `relation "scraper_universitydata" does not exist` | `docker exec acu_chat_app python manage.py migrate` çalıştırılmadı. |
| Boş yanıt veya "Bu konuda elimde yeterli bilgi bulunmuyor." | Veritabanı boş. Kurulumdaki scraper komutlarını çalıştırın. |
| Tarayıcıda akış görünmüyor (cevap birden geliyor) | Eski JS cache'i. `Ctrl+Shift+R` ile hard reload yapın. |
| Sidebar başlığı "Merhaba Sohbet İste..." gibi geliyor | Selamlama tespiti devre dışı kalmış olabilir. Hard reload sonrası `merhaba` yazınca anında "Genel Sohbet" görünmeli. |

## Hibrit RAG Akışı

Kullanıcı mesajı geldiğinde `chat_api` şu adımları izler:

1. **Sohbet kontrolü** — Mesaj `CHAT_KEYWORDS`'te bir selamlama/teşekkür içeriyorsa RAG atlanır, mini profil ile direkt cevap üretilir.
2. **Niyet (intent) sınıflandırması** — `detect_query_intent` mesajı `is_location / is_contact / is_transport / is_admission / is_program / is_life / is_fee / is_scholarship` etiketlerine kabaca böler. `is_fee` algılanırsa `is_admission` da otomatik açılır; "burs" başlıklı sayfalar ücret sorgusunda negatif puan alır (öğrenim ücreti yerine burs sayfasının dönmemesi için).
3. **Öncelikli PostgreSQL filtresi** — Niyete göre yüksek olasılıklı kayıt alt kümesi (ör. ulaşım sorularında `ulasim`/`iletisim` URL'leri).
4. **Tam metin arama** — `SearchVector` (title:A, content:B) + `SearchRank` ile aday kayıtlar.
5. **Niyet tabanlı puanlama** — `score_entry_for_intent` URL/title/içerik kalıplarıyla aday sıralamasını rafine eder; ücret intent'inde "öğrenim ücret" başlıklı sayfalar +3.0, sırf "burs" sayfaları -2.2 puan alır.
6. **Vektör takviyesi** — `should_use_vector_search` helper'ı karar verir:
   - Konum/iletişim/ulaşım intent'i → vektör atlanır.
   - Güçlü başlık eşleşmesi (≥2 hit) **ve** `match_score ≥ 1.6` → vektör atlanır.
   - Aksi halde ChromaDB'de embedding araması ile chunk'lar çekilir, `VECTOR_DISTANCE_LIMIT = 1.4` ile filtrelenir.
7. **Bağlam derleme** — `build_context(..., context_query=search_query)` ile kaynaklardan en fazla 4 parça toplar; her kaynak için `Kaynak: ... / URL: ...` etiketi yazılır, `seen_parent_ids` ile aynı sayfa tekrarı engellenir. Uzun paragraflar `extract_keyword_window` ile sayfa başı yerine eşleşen terimlerin çevresinden kesilir; tablo başlıkları (`|` içeren ilk satır) korunur.
8. **Prompt'a yerleştirme** — `--- BAĞLAM BİLGİSİ ---` bloğu ve gerekiyorsa intent'e özel sistem notuyla (ücret/ulaşım/konum) birlikte Ollama'ya `stream=True` gönderilir.

### Embedding katmanı

`chat/vector_service.py`:
- ChromaDB persistent client (`./chroma_db_data`).
- Embedding modeli: **`nomic-embed-text`** (Ollama üzerinden, 768 boyut).
- Sorgu/doküman ayrımı için `search_query: ` / `search_document: ` prefix'leri.
- `chunk_size=900`, `overlap=180` örtüşmeli parçalama.
- Embedding çağrıları `lru_cache(maxsize=256)` ile önbelleklenir.

## LLM ve Cevap Üretimi

### Sistem promptu kuralları (`chat/views.py::SYSTEM_PROMPT`)

1. **Öz ve tam:** Tekrar/dolgu yok; başlanan cümle MUTLAKA tamamlanır. Liste varsa en fazla 5 madde.
2. **Sohbet:** Teşekkür/selamlamaya tek cümleyle karşılık ver, kendini tanıtma.
3. **Bilgi:** Üniversite sorularında SADECE verilen bağlamı kullan; uydurma yok.
4. **Kalite:** Bağlamdaki bilgileri birleştir; bağlamda olmayan tarih/ücret/kontenjan/hat/kişi adı uydurma. Markdown başlığı (`#`, `##`) kullanma; düz metin veya kısa madde.
5. **Adres:** Yalnız adres soruluyorsa sadece adres ver; telefon/ulaşım ekleme.
6. **Bilinmeyen:** Bağlam yoksa yalnız `"Bu konuda elimde yeterli bilgi bulunmuyor."` cümlesi.
7. **Üniversite adı kilidi:** Üniversitenin adı her zaman "Acıbadem Üniversitesi". Başka isim (Akdeniz, İstanbul vb.) yasak.

### Ollama profilleri

| Profil | Kullanım | `num_ctx` | `num_predict` | `temperature` | `top_p` |
|--------|----------|-----------|---------------|---------------|---------|
| `OLLAMA_OPTIONS`      | Bağlamlı bilgi yanıtları           | 3072 | 700 | 0.2 | 0.85 |
| `CHAT_OLLAMA_OPTIONS` | Selamlama / "bilgim yok" yolu      | 512  | 80  | 0.3 | 0.9  |

Her iki profil de `keep_alive: "30m"` ile çağrılır; model 30 dk RAM'de tutulur.

## Streaming Uçtan Uca

**Backend** — `chat/views.py::chat_api`:
- `StreamingHttpResponse(stream_reply(), content_type="text/plain; charset=utf-8")` döner.
- `requests.post(..., stream=True)` ile Ollama'ya bağlanır, `iter_lines` üzerinden NDJSON parçalarını okur.
- Her chunk'ın `message.content` alanı `yield` edilir; toplam metin `collected` listesinde birikir.
- Akış bittiğinde (kayıtlı kullanıcıysa) `ChatMessage.objects.create(...)` ile DB'ye kaydedilir.
- `Cache-Control: no-cache` ve `X-Accel-Buffering: no` başlıkları proxy/middleware tamponlamasını kapatır.

**Frontend** — `chat/templates/chat/home.html::sendMessage`:
- `fetch('/chat-api/')` → `response.body.getReader()` + `TextDecoder('utf-8')`.
- İlk parça gelince typing göstergesi kapanır, boş bir bot baloncuğu açılır.
- Her parça `botBodyEl.textContent`'e eklenir, alan otomatik kaydırılır.
- Bağlantı kesilirse mevcut metin korunur, sona `[Bağlantı kesildi]` notu eklenir.

## Sohbet Başlığı Üretimi

İlk kullanıcı mesajından sonra sohbet için bir başlık üretilir. İki yol var:

**Hızlı yol (LLM yok)** — Mesaj `merhaba`, `selam`, `teşekkür`, `hi` gibi nezaket sözcükleriyle ≤ 4 kelime ise:
- Frontend `isGreetingMessage(text)` ile yakalar, doğrudan **"Genel Sohbet"** atar.
- Backend `is_greeting_question` aynı kontrolü yapar; başka istemcilerden gelen istekler için de güvende kalınır.

> Aynı şekilde **`chat_api`** içinde `get_simple_chat_reply` selamlama/teşekkür mesajına LLM çağırmadan sabit bir cevabı (örn. *"Merhaba, nasıl yardımcı olabilirim?"*, *"Rica ederim."*) tek-parça stream olarak döndürür. Frontend yine `ReadableStream` ile okur — kırılma yok, ama yanıt anında gelir.

**LLM yolu (`generate_title` view)** — Asıl bilgi sorusu için:
- Few-shot örneklerle prompt: `4 kelime, Title Case, "Merhaba/Sohbet/Soru/Hakkında" yasak, tırnak yok`.
- `temperature=0.2`, `top_p=0.8`, `num_predict=20`, `keep_alive=30m`.
- Cevap `clean_generated_title` içinde temizlenir: `Konu:`, `Başlık -`, çift tırnaklar, baş `Merhaba/Selam/Hi/Hello` kelimeleri sıyrılır.
- Frontend gelen başlığı **tekrar temizlemez**, sadece `truncateAtWord(title, 50)` ile kısaltır.

## UI Detayları

- Mesaj baloncukları 220 ms `fade + slide` (`@keyframes msgIn`) ile belirir.
- Kullanıcı baloncuğunda subtle mavi gölge; "Claudey" başlığı 600 weight, açık ton.
- Bot mesaj gövdesinde `pre-wrap` + `word-wrap` — uzun yanıtlarda paragraf/satır boşlukları korunur.
- Input wrapper'a `:focus-within` turuncu border + soft glow.
- Send butonu hover'da koyu turuncu, active'de hafif `scale(0.94)`; disabled'da `opacity 0.7`.
- "Yeni Sohbet" butonuna soft turuncu glow.
- Aktif sohbet öğesinin sol kenarında 3px turuncu inset border.
- Topbar başlığı boşken italik, silikleştirilmiş "Yeni Sohbet" hayalet placeholder.
- Webkit + Firefox için 8 px ince scrollbar (track şeffaf, thumb `#334155`).

## Scraper

İki Django management komutu:

**`scrape_acu`** — Ana site BFS tarayıcısı:
- Seed URL'lerden başlar, sayfa içindeki linkleri takip eder.
- Gereksiz sayfaları eler (PDF, görsel, EN sayfaları, login).
- İçerik temizleme: cookie banner / nav / footer kaldırılır.
- URL'den otomatik kategori tahmini.
- Varsayılan: 100 sayfa, 1 sn bekleme.

```bash
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
```

**`scrape_bologna`** — Bologna bilgi sistemi:
- Genel bilgi sayfaları (yönetim, kampüs, spor, konaklama vb.).
- Tüm seviyelerdeki program ve detay sayfaları (Ön Lisans, Lisans, Yüksek Lisans, Doktora).

```bash
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

## API Uçları

| Endpoint                             | Method | Açıklama                                                |
|--------------------------------------|--------|---------------------------------------------------------|
| `/`                                  | GET    | Sohbet arayüzü                                          |
| `/chat-api/`                         | POST   | **Streaming** sohbet yanıtı (`text/plain; charset=utf-8`) |
| `/generate-title/`                   | POST   | İlk kullanıcı sorusundan kısa başlık                    |
| `/admin/`                            | GET    | Django admin                                            |
| `/accounts/login/`                   | GET/POST | Giriş ekranı                                          |
| `/accounts/register/`                | GET/POST | Kayıt ekranı                                          |
| `/accounts/logout/`                  | POST   | Çıkış                                                   |

### `POST /chat-api/`

```jsonc
// Request
{ "message": "Burs imkanları nelerdir?" }

// Response: text/plain, parça parça (NDJSON değil — düz UTF-8 metin akışı)
"Acıbadem Üniversitesi'nde " ⇨ "başarı bursu, indirim ve sosyal " ⇨ ...
```

Frontend `ReadableStream` ile okur; tüm gövde birleştirildiğinde nihai cevap elde edilir.

### `POST /generate-title/`

```jsonc
// Request
{ "question": "Burs imkanları nelerdir?" }

// Response
{ "title": "Burs İmkânları" }

// Selamlama mesajı durumunda LLM'e gidilmeden:
// Request: { "question": "merhaba" }
// Response: { "title": "Genel Sohbet" }
```

## Veri Modelleri

**`scraper.UniversityData`**

| Alan        | Tip                    | Açıklama                                                     |
|-------------|------------------------|--------------------------------------------------------------|
| `url`       | URLField (unique)      | Kaynak sayfa                                                 |
| `title`     | CharField(300)         | Sayfa başlığı                                                |
| `content`   | TextField              | Temizlenmiş içerik                                           |
| `category`  | CharField              | program / course / general / admission / staff / contact / other |
| `source`    | CharField              | `main_site` veya `bologna`                                   |
| `level`     | CharField              | Lisans / Yüksek Lisans / Ön Lisans / Doktora                 |
| `scraped_at`| DateTimeField          | Taranma zamanı                                               |

**`chat.ChatMessage`** — Yalnızca kayıtlı kullanıcılar için saklanır.

| Alan          | Tip          | Açıklama                  |
|---------------|--------------|---------------------------|
| `user`        | ForeignKey   | Sahibi olan kullanıcı     |
| `user_query`  | TextField    | Kullanıcının sorusu       |
| `ai_response` | TextField    | AI'ın tam yanıtı          |
| `timestamp`   | DateTimeField| Mesaj zamanı              |

## Proje Yapısı

```
claudey/
├── docker-compose.yml
├── .env                                # gitignore'da
├── README.md
└── claudey/
    ├── manage.py · Dockerfile · requirements.txt
    ├── config/                         # Django ayarları, kök URL'ler
    │   ├── settings.py
    │   ├── urls.py · wsgi.py · asgi.py
    ├── chat/
    │   ├── views.py                    # chat_api (streaming), generate_title, home
    │   ├── rag_config.py               # CHAT_KEYWORDS, INTENT_HINTS, NOISY_URL_HINTS, ...
    │   ├── vector_service.py           # ChromaDB embedding + arama
    │   ├── models.py                   # ChatMessage
    │   ├── urls.py
    │   └── templates/chat/home.html    # Streaming UI + sohbet başlığı + polished CSS
    ├── scraper/
    │   ├── models.py                   # UniversityData
    │   └── management/commands/
    │       ├── scrape_acu.py
    │       └── scrape_bologna.py
    ├── users/                          # Auth (kayıt / giriş / çıkış)
    ├── chroma_db_data/                 # Vector store (volume)
    └── ai_model/
        └── entrypoint.sh               # Ollama başlat + Qwen + nomic-embed indir
```

## Teknolojiler

- **Backend:** Django 5.x, Python 3.12
- **DB:** PostgreSQL 15 (Full-Text Search), ChromaDB (vektör arama)
- **LLM:** Ollama + Qwen2.5-3B-Instruct (chat, streaming) + `nomic-embed-text` (embedding)
- **Scraping:** BeautifulSoup4, lxml, Requests
- **Frontend:** Vanilla HTML / CSS / JS + `ReadableStream` ile token akışı
- **Container:** Docker, Docker Compose
