"""
YouTube Transcript -> Recipe Extractor (Beginner-Friendly)

Install dependencies:
    pip install youtube-transcript-api requests

Set environment variables before running:
    # Paid cloud (OpenAI-compatible):
    $env:OPENAI_API_KEY="your_api_key_here"
    $env:OPENAI_MODEL="gpt-4o-mini"                # Optional
    $env:OPENAI_BASE_URL="https://api.openai.com/v1"  # Optional

    # Or store them in a local env file (example: secret.env):
    # OPENAI_API_KEY=...
    # OPENAI_BASE_URL=https://api.groq.com/openai/v1
    # OPENAI_MODEL=llama3-70b-8192
    # SPOONACULAR_API_KEY=your_spoonacular_api_key

    # Free local option with Ollama (no API key required):
    # 1) Install Ollama and run a model, for example:
    #    ollama run llama3.1
    # 2) Then set:
    #    $env:OPENAI_MODEL="llama3.1"
    #    $env:OPENAI_BASE_URL="http://localhost:11434/v1"
"""

import json
import os
import re
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

# Keep transcript short enough for API requests.
MAX_TRANSCRIPT_CHARS = 12000

# Default servings when the AI omits the field or it cannot be parsed.
DEFAULT_SERVINGS = 2

# Exact prompt string used for the AI call.
RECIPE_PROMPT = (
    "You are a recipe extraction assistant. "
    "Read the transcript and extract one recipe if present. "
    "Return STRICT JSON only. "
    "Do not use markdown. Do not add explanation. Do not add extra text. "
    'Return exactly this JSON shape: {"title":"","ingredients":[],"steps":[],"servings":2}. '
    "Rules: "
    "1) title is a short string. "
    "2) ingredients is an array of strings (one ingredient per line of text). "
    "3) steps is an array of strings in order. "
    "4) servings is a positive integer: how many people or portions the recipe is for. "
    "If the transcript does not say, use a sensible guess or 2. "
    "5) If no recipe exists, return exactly: "
    '{"title":"","ingredients":[],"steps":[],"servings":2}.'
)


def load_env_file(file_path: str = "secret.env") -> None:
    """
    Load KEY=VALUE pairs from a local env file into environment variables.
    Existing variables are kept as-is.
    """
    if not os.path.exists(file_path):
        return

    with open(file_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()

            # Skip empty lines and comments.
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            # Do not overwrite variables already set by terminal/host.
            if key and key not in os.environ:
                os.environ[key] = value


def extract_video_id(youtube_url: str) -> str:
    """
    Extract the YouTube video ID from common URL formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    Returns the video ID string, or raises ValueError for invalid URLs.
    """
    parsed = urlparse(youtube_url.strip())
    host = parsed.netloc.lower().replace("www.", "")
    path_parts = [part for part in parsed.path.split("/") if part]

    # youtu.be/<video_id>
    if host == "youtu.be" and path_parts:
        return path_parts[0]

    # youtube.com/watch?v=<video_id>
    if host in {"youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        query = parse_qs(parsed.query)
        video_ids = query.get("v")
        if video_ids and video_ids[0]:
            return video_ids[0]

    # youtube.com/shorts/<video_id>
    if host in {"youtube.com", "m.youtube.com"} and len(path_parts) >= 2 and path_parts[0] == "shorts":
        return path_parts[1]

    raise ValueError("Invalid YouTube URL. Please provide a watch, shorts, or youtu.be link.")


def get_transcript(video_id: str) -> str:
    """
    Fetch transcript segments for a video ID and return one clean paragraph.
    Raises RuntimeError if no transcript is available.
    """
    try:
        # Support both older and newer versions of youtube-transcript-api.
        # Old API: YouTubeTranscriptApi.get_transcript(video_id)
        # New API: YouTubeTranscriptApi().fetch(video_id)
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            transcript_data = YouTubeTranscriptApi().fetch(video_id)

        text_parts = []
        for segment in transcript_data:
            # Old API returns dicts: {"text": "..."}
            if isinstance(segment, dict):
                piece = segment.get("text", "").strip()
            else:
                # New API may return objects with ".text"
                piece = str(getattr(segment, "text", "")).strip()

            if piece:
                text_parts.append(piece)

        clean_text = " ".join(text_parts)
        return " ".join(clean_text.split())  # remove extra spaces/newlines
    except (NoTranscriptFound, TranscriptsDisabled):
        raise RuntimeError("No transcript available for this video.")
    except Exception as error:
        raise RuntimeError(f"Failed to fetch transcript: {error}")


def extract_json_text(raw_text: str) -> str:
    """
    Clean model output and keep only the JSON object text.
    Steps:
    1) Remove markdown code fences if present.
    2) Keep content between first '{' and last '}'.
    """
    text = raw_text.strip()
    # Remove code fences like ```json and ```
    lines = text.splitlines()
    lines = [line for line in lines if not line.strip().startswith("```")]
    text = "\n".join(lines).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
        return text[first_brace : last_brace + 1].strip()

    # If braces are missing, return cleaned text (json.loads will handle error).
    return text


def extract_recipe_with_ai(transcript_text: str) -> dict:
    """
    Send transcript to OpenAI-compatible API and return recipe JSON.
    Expected return format:
    {
      "title": "",
      "ingredients": [],
      "steps": [],
      "servings": 2
    }
    """
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    # Local OpenAI-compatible servers (like Ollama) usually do not need an API key.
    is_local_base_url = "localhost" in base_url or "127.0.0.1" in base_url
    if not api_key and not is_local_base_url:
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Set it for cloud APIs, or use a local base URL (for example Ollama)."
        )

    # Truncate very long transcripts to reduce token/cost issues.
    truncated_transcript = transcript_text[:MAX_TRANSCRIPT_CHARS]

    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    def call_chat_api(messages: list) -> str:
        """Send one chat completion request and return message text."""
        payload = {
            "model": model,
            "temperature": 0,
            "messages": messages,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    try:
        # First attempt: ask for recipe JSON from transcript.
        first_messages = [
            {"role": "system", "content": RECIPE_PROMPT},
            {
                "role": "user",
                "content": (
                    "Transcript:\n"
                    f"{truncated_transcript}\n\n"
                    "Extract the recipe now."
                ),
            },
        ]
        raw_content = call_chat_api(first_messages)
        json_text = extract_json_text(raw_content)
        recipe = json.loads(json_text)
    except requests.RequestException as error:
        error_details = ""
        if hasattr(error, "response") and error.response is not None:
            try:
                error_details = error.response.text.strip()
            except Exception:
                error_details = ""

        if error_details:
            raise RuntimeError(f"API request failed: {error}. Details: {error_details}")
        raise RuntimeError(f"API request failed: {error}")
    except (KeyError, IndexError, json.JSONDecodeError):
        # Second attempt: ask model to repair JSON only once.
        try:
            repair_prompt = (
                "Fix this into valid JSON only. "
                "Do not add markdown or explanation. "
                'Use exactly this shape: {"title":"","ingredients":[],"steps":[],"servings":2}. '
                "Input:\n"
                f"{raw_content if 'raw_content' in locals() else ''}"
            )
            retry_messages = [
                {"role": "system", "content": RECIPE_PROMPT},
                {"role": "user", "content": repair_prompt},
            ]
            retry_content = call_chat_api(retry_messages)
            retry_json_text = extract_json_text(retry_content)
            recipe = json.loads(retry_json_text)
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
            # Safe fallback: never crash because of bad JSON.
            return {"title": "", "ingredients": [], "steps": [], "servings": DEFAULT_SERVINGS}

    # Validate and normalize output keys for safety.
    if not isinstance(recipe, dict):
        raise RuntimeError("AI output is not a JSON object.")

    title = recipe.get("title", "")
    ingredients = recipe.get("ingredients", [])
    steps = recipe.get("steps", [])
    servings = recipe.get("servings", DEFAULT_SERVINGS)

    if not isinstance(title, str):
        title = ""
    if not isinstance(ingredients, list):
        ingredients = []
    if not isinstance(steps, list):
        steps = []
    # Servings: must be a positive integer; default to 2.
    try:
        servings_int = int(servings)
        if servings_int <= 0:
            servings_int = DEFAULT_SERVINGS
    except (TypeError, ValueError):
        servings_int = DEFAULT_SERVINGS

    clean_recipe = {
        "title": title.strip(),
        "ingredients": [str(item).strip() for item in ingredients if str(item).strip()],
        "steps": [str(item).strip() for item in steps if str(item).strip()],
        "servings": servings_int,
    }
    return clean_recipe


def print_recipe(recipe: dict) -> None:
    """Print recipe result in a clear, beginner-friendly format."""
    title = recipe.get("title", "")
    ingredients = recipe.get("ingredients", [])
    steps = recipe.get("steps", [])
    servings = recipe.get("servings", DEFAULT_SERVINGS)

    if not title and not ingredients and not steps:
        print("\nNo recipe found in the transcript.")
        return

    print("\nExtracted Recipe:\n")
    print(f"Title: {title or 'Untitled Recipe'}")
    print(f"Servings: {servings}")

    print("\nIngredients:")
    if ingredients:
        for ingredient in ingredients:
            print(f"- {ingredient}")
    else:
        print("- (none)")

    print("\nSteps:")
    if steps:
        for index, step in enumerate(steps, start=1):
            print(f"{index}. {step}")
    else:
        print("1. (none)")


# Words we treat as measurement units (first word after the number).
_MEASUREMENT_UNITS = {
    "cup",
    "cups",
    "tbsp",
    "tsp",
    "tbs",
    "tablespoon",
    "tablespoons",
    "teaspoon",
    "teaspoons",
    "oz",
    "ounce",
    "ounces",
    "lb",
    "lbs",
    "pound",
    "pounds",
    "g",
    "kg",
    "ml",
    "l",
    "clove",
    "cloves",
    "piece",
    "pieces",
    "slice",
    "slices",
    "can",
    "cans",
    "pinch",
    "dash",
    "bunch",
    "bunches",
    "head",
    "heads",
    "stalk",
    "stalks",
    "packet",
    "packets",
    "stick",
    "sticks",
    "inch",
    "inches",
    "quart",
    "quarts",
    "pint",
    "pints",
    "gram",
    "grams",
    "liter",
    "liters",
    "litre",
    "litres",
}


def parse_ingredient(ingredient: str):
    """
    Extract quantity (float), unit (string), and ingredient name (string).
    If parsing fails, return (None, None, ingredient) so callers can fall back.
    """
    original = str(ingredient).strip()
    if not original:
        return None, None, ingredient

    # Leading number: integer, decimal, or simple fraction like 1/2
    match = re.match(r"^\s*(\d+(?:\.\d+)?|\d+/\d+)\s+", original)
    if not match:
        return None, None, ingredient

    qty_str = match.group(1)
    rest = original[match.end() :].strip()
    if not rest:
        return None, None, ingredient

    try:
        if "/" in qty_str:
            num, den = qty_str.split("/", 1)
            qty = float(num) / float(den)
        else:
            qty = float(qty_str)
    except (ValueError, ZeroDivisionError):
        return None, None, ingredient

    parts = rest.split(None, 1)
    first_word = parts[0].lower()
    # "1 cup milk" → unit + name; "2 eggs" → no unit, full rest is name
    if first_word in _MEASUREMENT_UNITS and len(parts) == 2:
        return qty, parts[0], parts[1].strip()
    return qty, "", rest


def scale_ingredient(ingredient: str, multiplier: float) -> str:
    """Multiply quantity by multiplier; round to 2 decimals. On parse failure, return original."""
    qty, unit, name = parse_ingredient(ingredient)
    if qty is None:
        return ingredient

    new_qty = round(qty * multiplier, 2)
    if new_qty == int(new_qty):
        qty_display = str(int(new_qty))
    else:
        qty_display = f"{new_qty:.2f}".rstrip("0").rstrip(".")

    if unit:
        return f"{qty_display} {unit} {name}".strip()
    return f"{qty_display} {name}".strip()


def scale_recipe(ingredients: list, original_servings: int, new_servings: int) -> list:
    """Apply scale_ingredient to each line using multiplier = new_servings / original_servings."""
    if original_servings <= 0 or new_servings <= 0:
        return list(ingredients)
    multiplier = new_servings / original_servings
    return [scale_ingredient(str(item), multiplier) for item in ingredients]


def _calories_from_nutrients(item: dict) -> int | None:
    """
    Find Calories in item['nutrition']['nutrients'].
    Returns None if missing, invalid, or 0 (treat 0 as unreliable / not available).
    """
    nutrition = item.get("nutrition") or {}
    for nutrient in nutrition.get("nutrients") or []:
        if str(nutrient.get("name", "")).strip().lower() != "calories":
            continue
        amount = nutrient.get("amount")
        if amount is None:
            return None
        try:
            value = float(amount)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return int(round(value))
    return None


def calculate_calories_data(ingredients: list) -> dict:
    """
    Call Spoonacular parseIngredients and return structured calorie data (no printing).

    Returns:
        {
            "lines": [{"ingredient": str, "calories": int | None, "status": "ok" | "not_available"}],
            "subtotal": int,
            "error": str | None,  # e.g. missing API key or HTTP failure
        }
    """
    empty_result = {"lines": [], "subtotal": 0, "error": None}
    api_key = os.getenv("SPOONACULAR_API_KEY", "").strip()
    if not api_key:
        return {**empty_result, "error": "SPOONACULAR_API_KEY not set"}

    lines_in = [str(i).strip() for i in ingredients if str(i).strip()]
    if not lines_in:
        return {**empty_result, "error": None}

    ingredient_list = "\n".join(lines_in)
    url = "https://api.spoonacular.com/recipes/parseIngredients"
    params = {
        "apiKey": api_key,
        "includeNutrition": "true",
    }
    form_data = {
        "ingredientList": ingredient_list,
        "servings": 1,
    }

    try:
        response = requests.post(url, params=params, data=form_data, timeout=45)
        response.raise_for_status()
        parsed = response.json()

        if not isinstance(parsed, list):
            return {
                **empty_result,
                "error": f"Unexpected Spoonacular response type: {type(parsed).__name__}",
            }

        out_lines = []
        subtotal = 0
        for item in parsed:
            if not isinstance(item, dict):
                continue
            label = item.get("original") or item.get("name") or "ingredient"
            cals = _calories_from_nutrients(item)
            if cals is None:
                out_lines.append(
                    {"ingredient": label, "calories": None, "status": "not_available"}
                )
            else:
                out_lines.append({"ingredient": label, "calories": cals, "status": "ok"})
                subtotal += cals

        return {"lines": out_lines, "subtotal": subtotal, "error": None}
    except requests.RequestException as error:
        detail = ""
        if hasattr(error, "response") and error.response is not None:
            try:
                detail = error.response.text.strip()
            except Exception:
                detail = ""
        msg = f"{error}"
        if detail:
            msg = f"{msg}: {detail}"
        return {**empty_result, "error": msg}


def calculate_calories(ingredients: list) -> int:
    """
    CLI helper: print calorie breakdown and return subtotal (same as calculate_calories_data subtotal).
    """
    data = calculate_calories_data(ingredients)
    if data.get("error") and not data["lines"]:
        print("\nSpoonacular:", data["error"])
        return 0

    print("\nCalorie breakdown (Spoonacular parseIngredients):")
    for row in data["lines"]:
        label = row["ingredient"]
        if row["status"] == "not_available":
            print(f"{label} → not available")
        else:
            print(f"{label} → {row['calories']} kcal")

    subtotal = data["subtotal"]
    print(f"\nSubtotal (known lines only, for recipe amounts as extracted): {subtotal} kcal")
    if data.get("error") and data["lines"]:
        print(f"(Note: {data['error']})")
    return subtotal


def run_recipe_pipeline(youtube_url: str, requested_servings: int | None) -> dict:
    """
    Full pipeline for API use (no input()). Returns a JSON-serializable dict.

    On failure (bad URL, transcript, AI): sets "error" and uses empty defaults for other fields.
    """
    base_error = {
        "title": "",
        "servings_original": DEFAULT_SERVINGS,
        "servings_requested": DEFAULT_SERVINGS,
        "ingredients_display": [],
        "steps": [],
        "calorie_lines": [],
        "subtotal_calories": 0,
        "total_calories": 0,
        "error": None,
    }

    try:
        video_id = extract_video_id(youtube_url)
    except ValueError as exc:
        return {**base_error, "error": str(exc)}

    try:
        transcript = get_transcript(video_id)
        recipe = extract_recipe_with_ai(transcript)
    except RuntimeError as exc:
        return {**base_error, "error": str(exc)}

    try:
        original_servings = int(recipe.get("servings", DEFAULT_SERVINGS))
    except (TypeError, ValueError):
        original_servings = DEFAULT_SERVINGS
    if original_servings <= 0:
        original_servings = DEFAULT_SERVINGS

    if requested_servings is not None and requested_servings > 0:
        effective_servings = int(requested_servings)
    else:
        effective_servings = original_servings

    ingredients_orig = list(recipe.get("ingredients", []))
    if effective_servings != original_servings:
        ingredients_display = scale_recipe(
            ingredients_orig, original_servings, effective_servings
        )
    else:
        ingredients_display = list(ingredients_orig)

    cal_data = calculate_calories_data(ingredients_orig)
    calorie_lines = cal_data.get("lines", [])
    subtotal = int(cal_data.get("subtotal", 0))

    if original_servings > 0:
        serving_multiplier = effective_servings / original_servings
    else:
        serving_multiplier = 1.0
    total_calories = int(round(subtotal * serving_multiplier))

    return {
        "title": recipe.get("title", ""),
        "servings_original": original_servings,
        "servings_requested": effective_servings,
        "ingredients_display": ingredients_display,
        "steps": list(recipe.get("steps", [])),
        "calorie_lines": calorie_lines,
        "subtotal_calories": subtotal,
        "total_calories": total_calories,
        "error": None,
    }


def main() -> None:
    """Ask for a URL, fetch transcript, call AI, and print recipe."""
    # Load values from secret.env if present (useful for Groq/OpenAI keys).
    load_env_file("secret.env")

    youtube_url = input("Enter YouTube video URL: ").strip()

    try:
        video_id = extract_video_id(youtube_url)
        transcript = get_transcript(video_id)
        recipe = extract_recipe_with_ai(transcript)
        print_recipe(recipe)

        original_servings = recipe.get("servings", DEFAULT_SERVINGS)
        new_servings = original_servings

        servings_input = input(
            "\nEnter number of servings (or press Enter to keep default): "
        ).strip()

        if servings_input:
            try:
                parsed_servings = int(servings_input)
                if parsed_servings <= 0:
                    print("\nServings must be a positive number; keeping default servings.")
                else:
                    new_servings = parsed_servings
                    if new_servings != original_servings:
                        scaled = scale_recipe(
                            recipe.get("ingredients", []),
                            original_servings,
                            new_servings,
                        )
                        print(f"\nOriginal Servings: {original_servings}")
                        print(f"New Servings: {new_servings}")
                        print("\nUpdated Ingredients:")
                        for ing in scaled:
                            print(f"- {ing}")
            except ValueError:
                print("\nInvalid number; keeping default servings.")

        # Calories: always use original ingredient lines so Spoonacular matches the extracted recipe.
        # Scale the total by (new_servings / original_servings) so totals track requested servings.
        base_calories = calculate_calories(recipe.get("ingredients", []))
        if original_servings > 0:
            serving_multiplier = new_servings / original_servings
        else:
            serving_multiplier = 1.0
        total_calories = int(round(base_calories * serving_multiplier))

        print("\n--- Calorie total ---")
        if abs(serving_multiplier - 1.0) < 1e-9:
            print(f"Total Calories: {total_calories} kcal")
        else:
            print(f"Total Calories (for {new_servings} serving(s)): {total_calories} kcal")
    except ValueError as error:
        print(f"\nError: {error}")
    except RuntimeError as error:
        print(f"\nError: {error}")


if __name__ == "__main__":
    main()
