"""Client for the local llama.cpp server (OpenAI-compatible API)."""

import base64
import json
import re

import httpx

from . import config


class LLMError(Exception):
    """Raised when the llama.cpp server is unreachable or returns an error."""


SYSTEM_PROMPT = (
    "You are a precise wine-label identification assistant for a personal "
    "wine-fridge inventory. Read the label in the photo carefully. Do not "
    "invent information that is not visible or strongly implied by the label. "
    "Respond with a single JSON object and nothing else."
)

USER_PROMPT = (
    "Identify the wine in this label photo. For wine, give the full name as the "
    "label presents it (estate/brand + cuvee + variety when that is how the "
    "label reads, e.g. 'Le Petit Salvard Sauvignon Blanc'). Also return the "
    "primary grape variety or blend, the vintage year "
    "(empty string if non-vintage or not visible), and the most useful "
    "producer/vineyard/estate name. The user will review and edit the result "
    "before saving, so note any uncertainty in notes. Respond with JSON only, "
    'using exactly these keys: {"wine": string, "variety": string, '
    '"vintage": string, "vineyardProducer": string, '
    '"confidence": "high" | "medium" | "low", "notes": string}.'
)


def server_status() -> dict:
    """Report whether the llama.cpp server is reachable and which models are loaded."""
    status = {
        "reachable": False,
        "model_loaded": False,
        "models": [],
        "error": None,
    }
    try:
        resp = httpx.get(f"{config.LLAMA_SERVER_URL}/v1/models", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("id", "") for m in data.get("data", [])]
        status.update(
            reachable=True,
            models=models,
            model_loaded=config.LLAMA_MODEL in models,
        )
    except Exception as exc:  # noqa: BLE001 - any failure is reported to the UI
        status["error"] = str(exc)
    return status


def analyze_image(data_url: str) -> dict:
    """Send a label photo (base64 data URL) to the model and return cleaned wine fields."""
    match = re.match(r"^data:([^;]+);base64,(.+)$", data_url or "", re.DOTALL)
    if not match:
        raise ValueError("No image was provided.")
    mime = match.group(1)
    if not mime.startswith("image/"):
        raise ValueError("The provided image type is not supported.")
    raw_length = len(base64.b64decode(match.group(2), validate=False))
    if raw_length > config.MAX_IMAGE_BYTES:
        raise ValueError("The photo is too large. Please retake it smaller.")

    payload = {
        "model": config.LLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": USER_PROMPT},
                ],
            },
        ],
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": config.LLM_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = httpx.post(
            f"{config.LLAMA_SERVER_URL}/v1/chat/completions",
            json=payload,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise LLMError(
            f"The model took longer than {config.LLM_TIMEOUT_SECONDS}s to respond. "
            "Try again, or check that the llama.cpp server is not busy."
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(
            f"Could not reach the llama.cpp server at {config.LLAMA_SERVER_URL}: {exc}"
        ) from exc

    if resp.status_code != 200:
        detail = _error_detail(resp)
        hint = ""
        lowered = detail.lower()
        if "image" in lowered and any(
            word in lowered for word in ("not supported", "no clip", "vision", "multimodal")
        ):
            hint = (
                " The loaded model does not appear to support image input — "
                "load a vision (VL) model in llama.cpp."
            )
        raise LLMError(f"llama.cpp error ({resp.status_code}): {detail}.{hint}")

    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("The model returned an unexpected response format.") from exc

    try:
        result = _extract_json(content)
    except ValueError as exc:
        raise LLMError("The model did not return valid JSON. Please try the photo again.") from exc

    return {
        "wine": _clean(result.get("wine")),
        "variety": _clean(result.get("variety")),
        "vintage": _clean_vintage(result.get("vintage")),
        "vineyardProducer": _clean(result.get("vineyardProducer")),
        "confidence": _clean(result.get("confidence")).lower(),
        "notes": _clean(result.get("notes")),
    }


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
    except ValueError:
        pass
    text = resp.text.strip()
    return text[:300] if text else "no error details"


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    text = _strip_code_fences(text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        result = json.loads(text[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("Model JSON was not an object.")
    return result


def _clean(value) -> str:
    return str(value if value is not None else "").strip()


def _clean_vintage(value) -> str:
    text = _clean(value)
    match = re.search(r"\b(18|19|20|21)\d{2}\b", text)
    return match.group(0) if match else text
