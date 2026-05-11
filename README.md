# Claudey

Claudey is a Turkish RAG chat assistant for Acibadem University. It answers questions about the university by combining data scraped from the official website and Bologna information system with PostgreSQL full-text search, ChromaDB vector search, and an Ollama-hosted **Qwen2.5-3B** model.

The app is built with Django and runs through Docker Compose. The main chat endpoint streams tokens to the browser as soon as Ollama produces them, while simple greetings and thanks are answered instantly without calling the model.

## Features

- **Streaming chat responses:** `chat_api` returns a `StreamingHttpResponse`, so browser output updates token by token.
- **Fast small-talk path:** greetings such as `merhaba`, `selam`, `tesekkurler`, `nasilsin`, and `tamam` return fixed replies without an LLM call.
- **Hybrid retrieval:** intent detection, PostgreSQL full-text search, intent-aware scoring, and ChromaDB fallback for weak keyword matches.
- **Smart context trimming:** long pages are trimmed around query terms while table-like content such as tuition and quota rows is preserved.
- **Tuition intent handling:** fee questions prioritize tuition pages and avoid letting generic scholarship pages outrank actual tuition data.
- **LLM profiles:** information answers use a larger context profile (`num_ctx=3072`, `num_predict=700`) and `keep_alive=30m`.
- **Defensive output cleanup:** accidental opening salutations such as "Sevgili..." or "Sayin..." are removed from the stream.
- **University-name guardrail:** the system prompt keeps answers tied to Acibadem University.
- **Authenticated chat history:** signed-in users get persisted `ChatMessage` history; guests use browser `localStorage`.
- **Polished vanilla UI:** animated message bubbles, active-chat highlighting, dark theme styling, and streaming-aware message rendering.

## Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                       Docker Compose                       │
│                                                            │
│  ┌────────────┐   ┌────────────┐   ┌────────────────────┐  │
│  │  Django    │   │ PostgreSQL │   │ Ollama (claudey_ai)│  │
│  │  (web)     │──▶│   (db)     │   │  Qwen2.5-3B        │  │
│  │  :8000     │   │   :5432    │◀──│  :11434            │  │
│  │            │   │            │   │                    │  │
│  │ Chat API ──┼───┼─ FTS search│   │ /api/chat stream   │  │
│  │ ChromaDB   │   │ Scraper DB │   │ nomic-embed-text   │  │
│  │ Vector RAG │   │ Chat hist. │   │                    │  │
│  └────────────┘   └────────────┘   └────────────────────┘  │
│                                                            │
│  Storage: postgres_data · ollama_data · app bind mount      │
└────────────────────────────────────────────────────────────┘
```

| Service | Container | Stack | Purpose |
| --- | --- | --- | --- |
| `web` | `acu_chat_app` | Django 5.x, Python 3.12 | UI, REST API, RAG, scraper commands |
| `db` | `acuchat_db` | PostgreSQL 15 Alpine | Scraped data, chat history, full-text search |
| `ai_engine` | `claudey_ai` | Ollama | Chat model and embedding model |

Host ports:

- `8500` -> Django web app
- `11434` -> Ollama API
- PostgreSQL is only available inside the Docker network.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2
- At least 4 GB free RAM for Qwen2.5-3B and the embedding model
- Internet access on first startup to download the Ollama models

## Setup

1. Clone the repository.

```bash
git clone https://github.com/sevdaodabas/claudey.git
cd claudey
```

2. Create a `.env` file in the repository root.

```env
DEBUG=True
SECRET_KEY=replace-this-with-a-strong-secret-key
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

3. Build and start the services.

```bash
docker compose up -d --build
```

4. Wait for the Ollama model to become ready.

```bash
docker logs claudey_ai --tail 5
```

In the `claudey_ai` logs, look for `Model hazır.` and `Embedding modeli hazır.` These messages are container logs, not frontend UI messages. The first run may download the Qwen and embedding models.

5. Apply migrations and create the admin user.

```bash
docker exec acu_chat_app python manage.py migrate
docker exec acu_chat_app python manage.py createsuperuser --noinput
```

6. Populate the database.

```bash
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

The scraper commands automatically trigger vector reindexing at the end. On a fresh database, embedding all pages may take several minutes.

Open:

- App: <http://localhost:8500>
- Admin: <http://localhost:8500/admin/>

## Daily Usage

After the first setup, this is usually enough:

```bash
docker compose up -d
```

Check service health:

```bash
docker compose ps
docker logs claudey_ai --tail 5
docker logs acu_chat_app --tail 5
```

Run new migrations:

```bash
docker exec acu_chat_app python manage.py migrate
```

Refresh scraped data:

```bash
docker exec acu_chat_app python manage.py scrape_acu --max-pages 100 --delay 1.0
docker exec acu_chat_app python manage.py scrape_bologna --delay 1.5
```

Skip automatic reindexing when scraping:

```bash
docker exec acu_chat_app python manage.py scrape_acu --no-reindex
```

## Tests

The project uses Django's built-in test runner. Run the tests inside the Docker container so the same dependencies and PostgreSQL settings are used as the app.

Start the services first:

```bash
docker compose up -d
```

Run all tests:

```bash
docker exec acu_chat_app python manage.py test
```

Run tests for a specific app:

```bash
docker exec acu_chat_app python manage.py test chat
docker exec acu_chat_app python manage.py test users
```

Run with more detailed output:

```bash
docker exec acu_chat_app python manage.py test --verbosity 2
```

Current test coverage includes vector-service helpers, chat helper logic, chat API validation, streaming quick replies, title generation fallback behavior, keyword scoring, context deduplication, and registration flows. External Ollama calls are mocked where needed, so the unit tests do not require a live model response.

## Vector Index Management

Update only missing or changed records:

```bash
docker exec acu_chat_app python manage.py reindex_vectors
```

Rebuild the full vector index:

```bash
docker exec acu_chat_app python manage.py reindex_vectors --full
```

Remove ChromaDB chunks for rows that no longer exist in PostgreSQL:

```bash
docker exec acu_chat_app python manage.py reindex_vectors --prune
```

Limit reindexing to one source or a small batch:

```bash
docker exec acu_chat_app python manage.py reindex_vectors --source bologna
docker exec acu_chat_app python manage.py reindex_vectors --limit 10
```

The legacy command still works as a deprecated alias:

```bash
docker exec acu_chat_app python manage.py migrate_chroma
```

## Useful Commands

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f ai_engine
docker compose restart web
docker exec -it acu_chat_app python manage.py shell
docker exec claudey_ai ollama list
docker exec acuchat_db psql -U claudey_db -d claudey_db -c "SELECT COUNT(*) FROM scraper_universitydata"
```

Stop or remove services:

```bash
docker compose stop
docker compose down
docker compose down -v
```

`docker compose down -v` deletes volumes, including the database and downloaded model data.

Rebuild after dependency or Dockerfile changes:

```bash
docker compose up -d --build
```

Python code changes under `claudey/` are mounted into the container and are normally picked up by Django's autoreloader. A rebuild is only needed for Dockerfile or dependency changes.

## RAG Flow

When a message reaches `chat_api`, Claudey runs this pipeline:

1. `get_simple_chat_reply` handles greetings and thanks without calling Ollama.
2. `detect_query_intent` identifies location, contact, transport, admission, program, life, fee, and scholarship signals.
3. Intent-specific filters narrow likely PostgreSQL records.
4. PostgreSQL full-text search ranks candidates with weighted title and content fields.
5. `score_entry_for_intent` refines ordering using URL, title, and content patterns.
6. `should_use_vector_search` decides whether ChromaDB fallback is needed.
7. `build_context` assembles up to four context blocks and deduplicates keyword and vector matches from the same page.
8. The context, user question, and intent-specific notes are sent to Ollama with streaming enabled.
9. The response stream is cleaned, yielded to the browser, and saved for authenticated users.

## API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/` | GET | Chat UI |
| `/chat-api/` | POST | Streaming chat response as `text/plain; charset=utf-8` |
| `/generate-title/` | POST | Short chat title from the first user question |
| `/admin/` | GET | Django admin |
| `/accounts/login/` | GET, POST | Login |
| `/accounts/register/` | GET, POST | Registration |
| `/accounts/logout/` | POST | Logout |

Example chat request:

```json
{
  "message": "Burs imkanlari nelerdir?"
}
```

Example title request:

```json
{
  "question": "Burs imkanlari nelerdir?"
}
```

Example title response:

```json
{
  "title": "Burs Imkanlari"
}
```

## Data Models

### `scraper.UniversityData`

| Field | Type | Description |
| --- | --- | --- |
| `url` | URLField | Source page URL |
| `title` | CharField | Page title |
| `content` | TextField | Cleaned page content |
| `category` | CharField | Program, course, general, admission, staff, contact, or other |
| `source` | CharField | `main_site` or `bologna` |
| `level` | CharField | Associate, undergraduate, graduate, or doctorate level when available |
| `scraped_at` | DateTimeField | Scrape timestamp |
| `content_hash` | CharField | Hash used to skip unchanged vector reindexing |

### `chat.ChatMessage`

| Field | Type | Description |
| --- | --- | --- |
| `user` | ForeignKey | Owner of the message |
| `user_query` | TextField | User question |
| `ai_response` | TextField | Full assistant response |
| `timestamp` | DateTimeField | Message timestamp |

## Project Structure

```text
claudey/
├── docker-compose.yml
├── README.md
└── claudey/
    ├── Dockerfile
    ├── manage.py
    ├── requirements.txt
    ├── ai_model/
    │   └── entrypoint.sh
    ├── chat/
    │   ├── models.py
    │   ├── rag_config.py
    │   ├── tests.py
    │   ├── urls.py
    │   ├── vector_service.py
    │   ├── views.py
    │   └── templates/chat/home.html
    ├── config/
    │   ├── settings.py
    │   └── urls.py
    ├── scraper/
    │   ├── models.py
    │   └── management/commands/
    │       ├── reindex_vectors.py
    │       ├── scrape_acu.py
    │       └── scrape_bologna.py
    └── users/
        ├── tests.py
        ├── urls.py
        └── views.py
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Port binding fails | Change the host port in `docker-compose.yml`, for example from `"8500:8000"` to `"8600:8000"`. |
| Responses are slow after startup | Check `docker logs claudey_ai --tail 20`. Cold model loading can take around 20 seconds. |
| `relation "scraper_universitydata" does not exist` | Run `docker exec acu_chat_app python manage.py migrate`. |
| The assistant says it does not have enough information | Run the scraper commands and make sure the database contains scraped pages. |
| Browser receives the response all at once | Hard refresh the page to clear old JavaScript cache. |
| Chat titles look stale | Hard refresh the page so the latest title-generation JavaScript is loaded. |

## Tech Stack

- **Backend:** Django 5.x, Python 3.12
- **Database:** PostgreSQL 15 full-text search
- **Vector store:** ChromaDB
- **LLM runtime:** Ollama
- **Models:** `qwen2.5:3b`, `nomic-embed-text`
- **Scraping:** BeautifulSoup4, lxml, Requests
- **Frontend:** Vanilla HTML, CSS, JavaScript, `ReadableStream`
- **Runtime:** Docker Compose
