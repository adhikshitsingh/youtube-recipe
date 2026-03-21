# YouTube Recipe API (FastAPI)

Minimal HTTP API around `youtube_transcript.py` for a Lovable (or any) frontend.

## Setup

1. Create `secret.env` in this folder with `OPENAI_*`, `SPOONACULAR_API_KEY`, etc. (same as the CLI script).
2. Install dependencies:

```bash
pip install -r requirements-api.txt
```

## Run (development)

```bash
uvicorn api:app --reload --port 8000
```

- API docs: <http://127.0.0.1:8000/docs>
- Health: `GET /health`

## Example: create recipe

```bash
curl -X POST "http://127.0.0.1:8000/api/recipe" ^
  -H "Content-Type: application/json" ^
  -d "{\"youtube_url\": \"https://www.youtube.com/watch?v=VIDEO_ID\", \"servings\": 4}"
```

(PowerShell: use `curl.exe` or `Invoke-RestMethod`.)

**Linux / macOS:**

```bash
curl -s -X POST "http://127.0.0.1:8000/api/recipe" \
  -H "Content-Type: application/json" \
  -d '{"youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID", "servings": 4}'
```

Omit `servings` to use the recipe’s default from the AI.

## Response shape (success)

```json
{
  "title": "...",
  "servings_original": 2,
  "servings_requested": 4,
  "ingredients_display": ["..."],
  "steps": ["..."],
  "calorie_lines": [
    { "ingredient": "2 eggs", "calories": 140, "status": "ok" },
    { "ingredient": "salt", "calories": null, "status": "not_available" }
  ],
  "subtotal_calories": 500,
  "total_calories": 1000,
  "error": null
}
```

On failure, `error` is a string and HTTP status is **400** (bad URL) or **502** (transcript / AI / etc.).

## CORS

`api.py` allows all origins for development. Before production, change `allow_origins` in `CORSMiddleware` to your real frontend URLs.

## Frontend (Lovable)

Point your app at `VITE_API_URL` (or similar) and `POST` to `/api/recipe` with JSON `{ "youtube_url", "servings?" }`.
