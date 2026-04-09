# Claudey - Acibadem University AI Assistant

Claudey, Acibadem Universitesi hakkinda sorulara yanit veren yapay zeka destekli bir sohbet uygulamasidir. Universite web sitesinden ve Bologna bilgi sisteminden toplanan verileri kullanarak ogrencilere, aday ogrencilere ve ziyaretcilere anlik bilgi sunar.

## Teknik Mimari

Proje uc Docker container uzerinde calisir:

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                       │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │   Django     │  │  PostgreSQL  │  │    Ollama     │  │
│  │  (web)       │──│  (db)        │  │  (ai_engine)  │  │
│  │  port:8000   │  │  port:5432   │  │  port:11434   │  │
│  │              │  │              │  │               │  │
│  │  - Chat API  │  │  - Scraper   │  │  - Qwen2.5   │  │
│  │  - Scraper   │  │    verileri  │  │    7B model   │  │
│  │  - UI        │  │  - Chat      │  │               │  │
│  │              │  │    gecmisi   │  │               │  │
│  └──────┬───────┘  └──────────────┘  └───────┬───────┘  │
│         │          HTTP /api/chat             │          │
│         └────────────────────────────────────┘          │
│                                                         │
│  Volumes:                                               │
│    - postgres_data  (veritabani kaliciligi)              │
│    - ollama_data    (AI model kaliciligi)                │
└─────────────────────────────────────────────────────────┘
```

### Servisler

| Servis | Container | Teknoloji | Gorev |
|--------|-----------|-----------|-------|
| **web** | `acu_chat_app` | Django 5.x, Python 3.12 | Web arayuzu, API, scraper komutlari |
| **db** | `acuchat_db` | PostgreSQL 15 Alpine | Veri depolama, full-text search |
| **ai_engine** | `claudey_ai` | Ollama + Qwen2.5-7B | Dogal dil isleme, soru yanit |

### Django Uygulamalari

- **chat** — Sohbet arayuzu ve API endpointleri
- **scraper** — Web scraping komutlari ve UniversityData modeli
- **users** — Kullanici yonetimi (gelistirme asamasinda)
- **config** — Django yapilandirmasi

### Veritabani Modelleri

**UniversityData** (scraper app):
| Alan | Tip | Aciklama |
|------|-----|----------|
| url | URLField | Sayfa URL'si (unique) |
| title | CharField(300) | Sayfa basligi |
| content | TextField | Temizlenmis sayfa icerigi |
| category | CharField | program, course, general, admission, staff, contact, other |
| source | CharField | main_site veya bologna |
| level | CharField | Lisans, Yuksek Lisans, On Lisans, Doktora |
| scraped_at | DateTimeField | Taranma zamani |

**ChatMessage** (chat app):
| Alan | Tip | Aciklama |
|------|-----|----------|
| user_query | TextField | Kullanicinin sorusu |
| ai_response | TextField | AI'in yaniti |
| timestamp | DateTimeField | Mesaj zamani |

### AI Entegrasyonu

**Model:** Qwen2.5-7B-Instruct (~4.7 GB)
- Ollama uzerinde CPU modunda calisir
- `/api/chat` endpoint'i ile system/user mesaj formati kullanilir
- Parametreler: `temperature=0.2`, `num_ctx=3072`, `num_predict=300`

**Context Arama Stratejisi:**

1. Kullanicinin sorusu PostgreSQL full-text search ile `SearchVector` ve `SearchRank` kullanilarak aranir
2. Baslik eslesmelerine yuksek agirlik (weight A), icerik eslesmellerine dusuk agirlik (weight B) verilir
3. Sonuclar relevans sirasina gore siralanir, en iyi 3 sonuc secilir
4. Her sonuctan sorguyla en ilgili paragraflar cikarilir (ilk N karakter yerine akilli paragraf secimi)
5. Full-text search sonuc vermezse keyword-based fallback aramasi devreye girer
6. Hazirlanan context, system prompt ile birlikte Ollama'ya gonderilir

**Prompt Yapisi:**
```
System: Sen Claudey'sin, Acibadem Universitesi'nin resmi yapay zeka asistanisin...
User: Asagidaki bilgileri kullanarak soruyu yanitla:
      [Kaynak 1 basligi]
      ilgili paragraflar...
      ---
      [Kaynak 2 basligi]
      ilgili paragraflar...

      Soru: kullanicinin sorusu
```

### Scraper Sistemi

Iki ayri Django management komutu:

**`scrape_acu`** — Ana site tarayicisi (BFS algoritmasi):
- Seed URL'lerden baslar, sayfa icerisindeki linkleri takip eder
- Gereksiz sayfalari atlar (PDF, resim, Ingilizce sayfalar, login vb.)
- Icerik temizleme: cookie banner, navigation, footer kaldirilir
- URL'den otomatik kategori tahmini
- Varsayilan limit: 100 sayfa, 1 saniye bekleme

**`scrape_bologna`** — Bologna bilgi sistemi tarayicisi:
- Genel bilgi sayfalari (14 sayfa: yonetim, kampus, spor, konaklama vb.)
- Program sayfalari: On Lisans, Lisans, Yuksek Lisans, Doktora
- Her program icin detay sayfasi

### Kullanici Arayuzu

- **Sohbet Alani:** Mesaj gonderme, AI yanitlarini goruntuleme
- **Yaziyor Gostergesi:** AI yanit olustururken animasyonlu uc nokta
- **Sohbet Yonetimi:** Yeni sohbet olusturma, sohbetler arasi gecis
- **Otomatik Baslik:** Ilk soruya dayanarak AI sohbet basligi olusturur
- **Duzenlenebilir Baslik:** Sidebar'da sohbet ismine cift tiklayarak degistirebilirsiniz
- **LocalStorage:** Sohbet gecmisi tarayicida saklanir

## Kurulum ve Calistirma

### Gereksinimler

- [Docker](https://docs.docker.com/get-docker/) ve Docker Compose
- En az 8 GB RAM (AI modeli icin)
- Internet baglantisi (ilk model indirmesi icin)

### Adim Adim Kurulum

**1. Repoyu klonlayin:**
```bash
git clone https://github.com/sevdaodabas/claudey.git
cd claudey
```

**2. `.env` dosyasi olusturun** (proje kok dizininde):
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

**3. Docker container'larini baslatin:**
```bash
docker compose up -d --build
```
> Ilk calistirmada AI modeli (~4.7 GB) indirilir. Internet hiziniza bagli olarak birka dakika surebilir.

**4. Model indirmesinin tamamlanmasini bekleyin:**
```bash
docker logs claudey_ai --tail 5
# "Model is ready." mesajini gorene kadar bekleyin
```

**5. Veritabani migration'larini calistirin:**
```bash
docker exec acu_chat_app python manage.py migrate
```

**6. Superuser olusturun:**
```bash
docker exec acu_chat_app python manage.py createsuperuser --noinput
```

**7. Scraper'lari calistirarak veritabanini doldurun:**
```bash
# Ana site (BFS tarama)
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0

# Bologna bilgi sistemi
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

**8. Uygulamayi acin:**
- Web arayuzu: [http://localhost:8000](http://localhost:8000)
- Admin paneli: [http://localhost:8000/admin/](http://localhost:8000/admin/)

### Uygulama Nasil Kullanilir

1. Tarayicinizda `http://localhost:8000` adresine gidin
2. Sol taraftaki sidebar'da **"+ Yeni Sohbet"** butonuna tiklayin
3. Alt kisimdaki metin kutusuna sorunuzu yazin ve **Enter** tuslayarak veya **Gonder** butonuna tiklayarak gonderin
4. AI yanit olustururken "yaziyor" animasyonu gorursunuz
5. Ilk sorunuzdan sonra sohbet ismi otomatik olarak olusturulur
6. Sohbet ismine **cift tiklayarak** duzenleyebilirsiniz
7. Sidebar'dan farkli sohbetler arasinda gecis yapabilirsiniz
8. Admin paneline `http://localhost:8000/admin/` adresinden erisebilirsiniz

**Ornek sorular:**
- "Bilgisayar muhendisligi bolumu hakkinda bilgi ver"
- "Tip fakultesi kac yil suruyor?"
- "Burs imkanlari nelerdir?"
- "Kampuse nasil ulasabilirim?"
- "Erasmus programina nasil basvurabilirim?"

### Yararli Docker Komutlari

```bash
# Container'lari baslat
docker compose up -d

# Container'lari durdur
docker compose down

# Loglari izle
docker compose logs -f

# Django loglarini gor
docker logs acu_chat_app --tail 50

# AI model durumunu kontrol et
docker exec claudey_ai ollama list

# Veritabanindaki kayit sayisini gor
docker exec acuchat_db psql -U claudey_db -d claudey_db -c "SELECT COUNT(*) FROM scraper_universitydata"

# Django shell
docker exec -it acu_chat_app python manage.py shell
```

## API Endpointleri

| Endpoint | Method | Aciklama |
|----------|--------|----------|
| `/` | GET | Ana sayfa (sohbet arayuzu) |
| `/chat-api/` | POST | Sohbet mesaji gonder, AI yaniti al |
| `/generate-title/` | POST | Sohbet basligi olustur |
| `/admin/` | GET | Django admin paneli |

**POST `/chat-api/`**
```json
// Request
{ "message": "Bilgisayar muhendisligi hakkinda bilgi ver" }

// Response
{ "reply": "Acibadem Universitesi Bilgisayar Muhendisligi Bolumu..." }
```

**POST `/generate-title/`**
```json
// Request
{ "question": "Burs imkanlari nelerdir?" }

// Response
{ "title": "Burs Imkanlari" }
```

## Proje Yapisi

```
claudey/
├── docker-compose.yml          # Docker servisleri tanimi
├── .env                        # Ortam degiskenleri (git'e eklenmez)
├── .gitignore
├── README.md
└── claudey/                    # Django projesi
    ├── manage.py
    ├── Dockerfile
    ├── requirements.txt
    ├── config/                 # Django ayarlari
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── asgi.py
    ├── chat/                   # Sohbet uygulamasi
    │   ├── models.py           # ChatMessage modeli
    │   ├── views.py            # chat_api, generate_title, home
    │   ├── urls.py
    │   ├── templates/
    │   │   └── chat/
    │   │       └── home.html   # Sohbet arayuzu
    │   └── migrations/
    ├── scraper/                # Web scraping uygulamasi
    │   ├── models.py           # UniversityData modeli
    │   ├── management/
    │   │   └── commands/
    │   │       ├── scrape_acu.py      # Ana site BFS tarayici
    │   │       └── scrape_bologna.py  # Bologna sistemi tarayici
    │   └── migrations/
    ├── users/                  # Kullanici yonetimi
    └── ai_model/               # AI motor yapilandirmasi
        └── entrypoint.sh       # Ollama baslat + model indir
```

## Teknolojiler

- **Backend:** Django 5.x, Python 3.12
- **Veritabani:** PostgreSQL 15
- **AI:** Ollama + Qwen2.5-7B-Instruct
- **Arama:** PostgreSQL Full-Text Search (SearchVector, SearchRank)
- **Scraping:** BeautifulSoup4, lxml, Requests
- **Frontend:** Vanilla HTML/CSS/JavaScript
- **Container:** Docker, Docker Compose
