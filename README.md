# YouTube → Recipe Extractor

Turn a **YouTube cooking video** into a structured **recipe** (title, ingredients, steps, servings), optionally **rescale for more or fewer servings**, and estimate **calories** with Spoonacular.

## Features

- Parse YouTube watch, Shorts, and `youtu.be` URLs
- Fetch transcripts via **Supadata** (avoids direct YouTube scraping)
- Extract recipe JSON with an **OpenAI-compatible** API (OpenAI, Groq, local Ollama, etc.)
- Scale ingredient quantities by servings
- Calorie breakdown via **Spoonacular** `parseIngredients` (approximate; some lines may show as not available)

## Requirements

- Python 3.10+
- API keys / env as below

## Environment variables

Create **`secret.env`** in the project folder (do **not** commit it):

| Variable | Required | Purpose |
|----------|----------|---------|
| `SUPADATA_API_KEY` | Yes (transcript) | Supadata transcript API |
| `OPENAI_API_KEY` | Yes (cloud LLM) | Groq / OpenAI / etc. |
| `OPENAI_BASE_URL` | Optional | e.g. `https://api.groq.com/openai/v1` |
| `OPENAI_MODEL` | Optional | e.g. Groq model id |
| `SPOONACULAR_API_KEY` | Optional | Calorie estimates |

For **Ollama** locally: set `OPENAI_BASE_URL` to `http://localhost:11434/v1` and you can omit `OPENAI_API_KEY`.

Example `secret.env`:

```env
SUPADATA_API_KEY=...
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=your-model-id
SPOONACULAR_API_KEY=...
```

## Install

```bash
pip install -r requirements.txt
```

For the HTTP API:

```bash
pip install -r requirements-api.txt
```

## CLI usage

```bash
python youtube_transcript.py
```

You will be prompted for a YouTube URL and optional servings. Output is printed in the terminal.

## HTTP API (FastAPI)

Start the server:

```bash
uvicorn api:app --reload --port 8000
```

- Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health: `GET /health`

### `POST /api/recipe`

**Body (JSON):**

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "servings": 4
}
```

`"servings"` is optional; if omitted, the recipe default from the AI is used.

**Success response** includes `title`, `servings_original`, `servings_requested`, `ingredients_display`, `steps`, `calorie_lines`, `subtotal_calories`, `total_calories`, and `error: null`.

**Errors:** `error` is a string; HTTP status is **400** for invalid YouTube URL and **502** for transcript / LLM failures.

### Example `curl`

```bash
curl -s -X POST "http://127.0.0.1:8000/api/recipe" \
  -H "Content-Type: application/json" \
  -d '{"youtube_url":"https://www.youtube.com/watch?v=VIDEO_ID","servings":4}'
```

**CORS** is set to `*` for development. Restrict `allow_origins` in `api.py` before production.

## Frontend

`index.html` can be used as a static UI; point it at your API base URL (e.g. via a config or build-time variable).

## Project layout

| File | Role |
|------|------|
| `youtube_transcript.py` | Core pipeline, CLI `main()`, `run_recipe_pipeline()` |
| `api.py` | FastAPI app |
| `secret.env` | Local secrets (gitignored recommended) |
| `requirements.txt` | `requests` |
| `requirements-api.txt` | App + FastAPI / uvicorn |
| `SESSION_LOG.md` | Change log |

## License

Use and modify as needed for your own project.
