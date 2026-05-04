# Claudey — Acıbadem Üniversitesi AI Asistanı

Claudey, Acıbadem Üniversitesi hakkındaki soruları yanıtlayan Türkçe bir RAG (Retrieval-Augmented Generation) sohbet uygulamasıdır. Üniversitenin web sitesi ve Bologna bilgi sisteminden taranmış verileri PostgreSQL + ChromaDB üzerinde tutar; Ollama üzerinde çalışan **Qwen2.5-7B** modeline akış (streaming) modunda cevap ürettirir.

> **Yenilikler**
> - **Streaming yanıtlar:** Cevaplar tamamlanmasını beklemeden token bazlı olarak ekrana yazılır.
> - **Daha kısa, kaliteli cevaplar:** Sıkılaştırılmış sistem yönergeleri (3-4 cümle / en fazla 4 madde) ve daha düşük `num_predict` ile tekrar/dolgu azaltıldı.
> - **Hızlandırma:** Sohbet (selamlama/teşekkür) ve "bilgim yok" yolları için ayrı, daha küçük bağlamlı (`num_ctx=512`) Ollama profili.

## Hızlı Başlangıç (Build sonrası çalıştırma)

`docker compose build` veya `docker compose up -d --build` zaten çalıştırıldıysa, çalıştırmak için:

```bash
# 1) Servisleri başlat (web + db + ai_engine)
docker compose up -d

# 2) Model hazır mı kontrol et — ilk açılışta ~4.7 GB indirme olabilir
docker logs claudey_ai --tail 5
#    "Model is ready." görünene kadar bekle

# 3) Veritabanı migration'larını uygula (sadece ilk çalıştırmada veya yeni migration eklendiğinde)
docker exec acu_chat_app python manage.py migrate

# 4) Admin kullanıcısı oluştur (sadece ilk kez; .env'deki DJANGO_SUPERUSER_* değerlerini kullanır)
docker exec acu_chat_app python manage.py createsuperuser --noinput

# 5) (İsteğe bağlı) Veritabanı boşsa scraper'ları çalıştır
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

Sonra tarayıcıdan aç:

- Web arayüzü: <http://localhost:8500>
- Admin paneli: <http://localhost:8500/admin/>

> **Port notu:** Container içinde Django 8000'de çalışır; host tarafında 8500'e maplenmiştir (Windows 11'in 7980-8079 aralığını Hyper-V için rezerv etmesi nedeniyle). Linux/macOS'ta isterseniz `docker-compose.yml` içinde `"8500:8000"` satırını `"8000:8000"` yapabilirsiniz.

### Sık ihtiyaç duyulan komutlar

```bash
docker compose ps                        # servislerin durumu
docker compose logs -f web               # Django canlı log
docker compose stop                      # servisleri durdur (veriyi siler değil)
docker compose down                      # container'ları kaldır (volume kalır)
docker compose down -v                   # volume'lar dahil her şeyi sıfırla (DİKKAT: veri silinir)
docker compose restart web               # Django'yu yeniden başlat
docker exec -it acu_chat_app python manage.py shell     # Django shell
```

### Sorun giderme

| Belirti | Çözüm |
|--------|-------|
| `bind: An attempt was made to access a socket in a way forbidden...` | Host portu kullanılıyor/rezerve. `docker-compose.yml`'de host portunu değiştirin (örn. `"8600:8000"`). |
| Cevap gelmiyor / çok yavaş | `docker logs claudey_ai --tail 20` ile model durumunu kontrol et. İlk istekte model RAM'e yükleniyor (~30 sn). `keep_alive=30m` ile sonraki istekler hızlı olur. |
| `relation "scraper_universitydata" does not exist` | `docker exec acu_chat_app python manage.py migrate` çalıştırılmadı. |
| Boş yanıt / "Bu konuda elimde yeterli bilgi bulunmuyor" | Veritabanı boş. 5. adımdaki scraper komutlarını çalıştırın. |
| Tarayıcıda akış görünmüyor (cevap birden geliyor) | Eski JS cache'i. `Ctrl+Shift+R` ile hard reload yapın. |

## Mimari

```
┌────────────────────────────────────────────────────────────┐
│                       Docker Compose                       │
│                                                            │
│  ┌────────────┐   ┌────────────┐   ┌────────────────────┐  │
│  │  Django    │   │ PostgreSQL │   │ Ollama (claudey_ai)│  │
│  │  (web)     │──▶│   (db)     │   │  Qwen2.5-7B        │  │
│  │  :8000     │   │   :5432    │◀──│  :11434            │  │
│  │            │   │            │   │                    │  │
│  │ Chat API ──┼───┼─ FTS arama │   │ /api/chat (stream) │  │
│  │ ChromaDB   │   │ Scraper DB │   │                    │  │
│  │ Vector RAG │   │ Chat hist. │   │                    │  │
│  └────────────┘   └────────────┘   └────────────────────┘  │
│                                                            │
│  Volumes: postgres_data · ollama_data · chroma_db_data     │
└────────────────────────────────────────────────────────────┘
```

### Servisler

| Servis      | Container       | Teknoloji                      | Görevi |
|-------------|-----------------|--------------------------------|--------|
| `web`       | `acu_chat_app`  | Django 5.x, Python 3.12        | UI, REST API, RAG, scraper komutları |
| `db`        | `acuchat_db`    | PostgreSQL 15 Alpine           | Veri + full-text search |
| `ai_engine` | `claudey_ai`    | Ollama + Qwen2.5-7B-Instruct   | LLM yanıt (streaming) |

### Django uygulamaları
- **chat** — Sohbet UI'ı, streaming `chat_api`, başlık üretici
- **scraper** — `UniversityData` modeli ve `scrape_acu`, `scrape_bologna` komutları
- **users** — Kullanıcı yönetimi (kayıt, giriş, çıkış)
- **config** — Django ayarları, URL yönlendirmeleri

### Veri modelleri

**UniversityData** (scraper)
| Alan | Tip | Açıklama |
|------|-----|----------|
| url | URLField (unique) | Kaynak sayfa |
| title | CharField(300) | Sayfa başlığı |
| content | TextField | Temizlenmiş içerik |
| category | CharField | program/course/general/admission/staff/contact/other |
| source | CharField | `main_site` veya `bologna` |
| level | CharField | Lisans / Yüksek Lisans / Ön Lisans / Doktora |
| scraped_at | DateTimeField | Taranma zamanı |

**ChatMessage** (chat) — kullanıcı mesajı + AI yanıtı + zaman damgası (yalnızca kayıtlı kullanıcılar için saklanır).

## RAG akışı

1. Kullanıcı mesajı önce **intent** sınıflandırmasından geçer (konum, iletişim, ulaşım, başvuru, program, üniversite yaşamı).
2. Intent'e göre yüksek öncelikli **PostgreSQL filtresi** kurulur (örn. ulaşım sorularında `ulasim`/`iletisim` URL'leri).
3. Tam metin arama (`SearchVector` + `SearchRank`, başlık ağırlığı A, içerik B) ile aday kayıtlar çekilir.
4. Aday yoksa veya niyet belirsizse **ChromaDB üzerinde vektör arama** (`vector_service.py`) devreye girer.
5. Her kaynaktan, sorguyla en alakalı paragraflar `extract_relevant_paragraphs` ile süzülür; konum/ulaşım için ayrı dar süzgeçler kullanılır.
6. Hazırlanan bağlam `--- BAĞLAM BİLGİSİ ---` bloğu olarak prompt'a eklenir, Ollama'ya `stream=True` ile gönderilir.

### Cevap kalitesi yönergeleri (sistem prompt'u)
- En fazla 3-4 cümle, listelerde en fazla 4 madde.
- Selamlama/teşekküre tek cümle ile karşılık ver, kendini tanıtma.
- Yalnız üniversite bilgilerinde verilen bağlamı kullan; bağlam boşsa "Bu konuda elimde yeterli bilgi bulunmuyor." de.
- Adres soruluyorsa sadece adres ver; ulaşım/telefon ekleme.

### Ollama profilleri
| Profil | Kullanım | `num_ctx` | `num_predict` | `temperature` |
|--------|----------|-----------|---------------|---------------|
| `OLLAMA_OPTIONS` | Bağlamlı bilgi yanıtları | 2048 | 180 | 0.2 |
| `CHAT_OLLAMA_OPTIONS` | Selamlama / "bilgim yok" yolu | 512 | 60 | 0.3 |

## Streaming uçtan uca

**Backend** — `chat/views.py::chat_api`, `StreamingHttpResponse` döner:
- Ollama'ya `stream=True` ile bağlanır, dönen NDJSON satırlarını parça parça okur.
- Her parçanın `message.content` alanı anında yanıtın gövdesine yazılır.
- Akış bittiğinde (kullanıcı oturum açmışsa) toplam metin `ChatMessage` olarak kaydedilir.
- `Cache-Control: no-cache` ve `X-Accel-Buffering: no` başlıklarıyla ara katman tampotlamaları kapatılır.

**Frontend** — `home.html::sendMessage`:
- `fetch('/chat-api/')` çağrısının `response.body.getReader()`'ı ile UTF-8 akışı okunur.
- İlk parça gelince typing göstergesi kapanır, boş bir bot baloncuğu açılır.
- Her yeni parça `textContent`'e eklenir, alan otomatik kaydırılır.
- Bağlantı kesilirse mevcut metin korunur ve `[Bağlantı kesildi]` notu eklenir.

## Scraper

**`scrape_acu`** — Ana site BFS tarayıcısı. Seed URL'lerden başlar, gereksiz sayfaları (PDF, görsel, EN sayfaları, login) eler, içerik temizleme uygular, URL'den kategori tahmini yapar. Varsayılan: 100 sayfa, 1 sn bekleme.

**`scrape_bologna`** — Bologna bilgi sisteminden genel bilgi sayfaları + tüm seviyelerdeki program ve detay sayfalarını toplar.

## API uçları

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/` | GET | Sohbet arayüzü |
| `/chat-api/` | POST | **Streaming** sohbet yanıtı (`text/plain; charset=utf-8`) |
| `/generate-title/` | POST | İlk kullanıcı sorusundan kısa başlık |
| `/admin/` | GET | Django admin |
| `/accounts/login/`, `/accounts/register/`, `/accounts/logout/` | — | Auth ekranları |

**`POST /chat-api/`**
```jsonc
// Request
{ "message": "Burs imkanları nelerdir?" }

// Response (text/plain, parça parça)
"Acıbadem Üniversitesi'nde başarı bursu, " ⇨ "indirim ve sosyal sorumluluk bursları " ⇨ ...
```
İstemci tarafında `ReadableStream` ile okunmalıdır; tüm gövde birleştirildiğinde nihai cevap elde edilir.

## Kurulum

### Gereksinimler
- Docker + Docker Compose
- En az 8 GB RAM (LLM için)
- İlk açılışta ~4.7 GB model indirimi için internet

### Adımlar

1. **Repo'yu al**
   ```bash
   git clone <repo-url>
   cd claudey
   ```

2. **`.env`** oluştur (proje kök dizini):
   ```env
   DEBUG=True
   SECRET_KEY=guclu-bir-anahtar
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

3. **Container'ları başlat**
   ```bash
   docker compose up -d --build
   docker logs claudey_ai --tail 5   # "Model is ready." görünene dek bekle
   ```

4. **Migrate + superuser**
   ```bash
   docker exec acu_chat_app python manage.py migrate
   docker exec acu_chat_app python manage.py createsuperuser --noinput
   ```

5. **Veriyi doldur**
   ```bash
   docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
   docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
   ```

6. **Aç**
   - Web: <http://localhost:8000>
   - Admin: <http://localhost:8000/admin/>

### Faydalı komutlar
```bash
docker compose logs -f                         # tüm loglar
docker logs acu_chat_app --tail 50             # Django logları
docker exec claudey_ai ollama list             # yüklü modeller
docker exec acuchat_db psql -U claudey_db -d claudey_db \
  -c "SELECT COUNT(*) FROM scraper_universitydata"
docker exec -it acu_chat_app python manage.py shell
```

## Proje yapısı

```
claudey/
├── docker-compose.yml
├── .env
├── README.md
└── claudey/
    ├── manage.py · Dockerfile · requirements.txt
    ├── config/                 # Django ayarları, URL'ler
    ├── chat/
    │   ├── views.py            # streaming chat_api, generate_title, home
    │   ├── rag_config.py       # CHAT_KEYWORDS, INTENT_HINTS, NOISY_URL_HINTS, ...
    │   ├── vector_service.py   # ChromaDB embedding + arama
    │   ├── models.py           # ChatMessage
    │   └── templates/chat/home.html   # Streaming UI
    ├── scraper/
    │   ├── models.py           # UniversityData
    │   └── management/commands/{scrape_acu,scrape_bologna}.py
    ├── users/                  # Auth
    ├── chroma_db_data/         # Vector store (volume)
    └── ai_model/entrypoint.sh  # Ollama başlat + model indir
```

## Teknolojiler
- **Backend:** Django 5.x, Python 3.12
- **DB:** PostgreSQL 15 (Full-Text Search), ChromaDB (vector store)
- **LLM:** Ollama + Qwen2.5-7B-Instruct (streaming)
- **Scraping:** BeautifulSoup4, lxml, Requests
- **Frontend:** Vanilla HTML/CSS/JS + `ReadableStream` ile akış
- **Container:** Docker, Docker Compose
