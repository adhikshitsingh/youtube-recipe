"""
FastAPI backend for youtube_transcript pipeline (Lovable / frontend).

Run (dev):
    uvicorn api:app --reload --port 8000

Tighten CORS (allow_origins) before production.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from youtube_transcript import load_env_file, run_recipe_pipeline

# Load secret.env from project root (same directory as this file by default).
_env_path = Path(__file__).resolve().parent / "secret.env"
load_env_file(str(_env_path))

app = FastAPI(title="YouTube Recipe API", version="1.0.0")

# Dev: allow any origin. For production, set allow_origins to your Lovable / app URLs only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RecipeRequest(BaseModel):
    youtube_url: str = Field(..., min_length=1, description="YouTube watch, shorts, or youtu.be URL")
    servings: int | None = Field(
        default=None,
        ge=1,
        description="Optional; if omitted, recipe default servings are used",
    )


def _http_status_for_pipeline_error(message: str) -> int:
    """Map pipeline error text to HTTP status."""
    if "Invalid YouTube URL" in message:
        return 400
    return 502


@app.post("/api/recipe")
def post_recipe(body: RecipeRequest):
    """Run transcript → AI recipe → optional scale → Spoonacular calories."""
    url = body.youtube_url.strip()
    if not url:
        return JSONResponse(
            status_code=400,
            content={
                "title": "",
                "servings_original": 2,
                "servings_requested": 2,
                "ingredients_display": [],
                "steps": [],
                "calorie_lines": [],
                "subtotal_calories": 0,
                "total_calories": 0,
                "error": "youtube_url is required",
            },
        )

    result = run_recipe_pipeline(url, body.servings)
    if result.get("error"):
        code = _http_status_for_pipeline_error(result["error"])
        return JSONResponse(status_code=code, content=result)
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
