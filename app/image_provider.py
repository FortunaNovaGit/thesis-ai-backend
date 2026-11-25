"""Image API adapter. No calls during mock/unit tests. No arbitrary URLs.

Costs depend on the provider; consent + per-site quota precede calling it.
"""
from __future__ import annotations
import base64
import httpx

async def generate_concept(prompt: str, size: str, *, api_key: str, model: str,
                           safety_identifier: str = "") -> bytes:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for image generation")
    if size not in {"1024x1024", "1536x1024", "1024x1536"}:
        raise ValueError("Unsupported image dimensions")
    payload = {"model": model, "prompt": prompt, "n": 1, "size": size,
               "quality": "medium", "output_format": "webp"}
    if safety_identifier:
        payload["safety_identifier"] = safety_identifier
    async with httpx.AsyncClient(timeout=httpx.Timeout(110.0, connect=10.0)) as client:
        response = await client.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload)
        response.raise_for_status()
        payload = response.json()
    raw = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
    if len(raw) < 100 or len(raw) > 5_000_000 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        raise ValueError("Image provider returned unexpected format or size")
    return raw
