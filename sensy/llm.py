"""Free LLM providers.

SensyGent speaks the OpenAI-compatible chat format and ships adapters for the
providers that offer a genuinely free tier. Keys are read from Streamlit
secrets, environment variables, or the sidebar — whichever you prefer.

No key? Then :mod:`sensy.localcare` takes over and the app keeps working.

    Provider        Where to get a free key                Notes
    --------------  -------------------------------------  -------------------
    Groq            console.groq.com/keys                  fastest, generous
    Google Gemini   aistudio.google.com/apikey             long context
    OpenRouter      openrouter.ai/keys                     has :free models
    Ollama          (local, no key)                        fully offline
    DeepSeek        platform.deepseek.com                  cheap/free credit
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

import requests

TIMEOUT = 45


@dataclass
class Provider:
    key: str
    label: str
    endpoint: str
    default_model: str
    models: List[str] = field(default_factory=list)
    docs: str = ""
    style: str = "openai"          # "openai" | "gemini"
    needs_key: bool = True
    note: str = ""


PROVIDERS: Dict[str, Provider] = {
    "groq": Provider(
        key="groq",
        label="Groq",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        default_model="llama-3.3-70b-versatile",
        models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "qwen/qwen3-32b",
            "openai/gpt-oss-120b",
        ],
        docs="https://console.groq.com/keys",
        note="Free tier, very fast. Best default choice.",
    ),
    "gemini": Provider(
        key="gemini",
        label="Google Gemini",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        default_model="gemini-2.0-flash",
        models=["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
        docs="https://aistudio.google.com/apikey",
        style="gemini",
        note="Free tier with a daily quota, very warm tone.",
    ),
    "openrouter": Provider(
        key="openrouter",
        label="OpenRouter",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        default_model="meta-llama/llama-3.3-70b-instruct:free",
        models=[
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "mistralai/mistral-small-3.2-24b-instruct:free",
        ],
        docs="https://openrouter.ai/keys",
        note="Models ending in :free cost nothing.",
    ),
    "deepseek": Provider(
        key="deepseek",
        label="DeepSeek",
        endpoint="https://api.deepseek.com/chat/completions",
        default_model="deepseek-chat",
        models=["deepseek-chat"],
        docs="https://platform.deepseek.com/api_keys",
        note="Very inexpensive; free credit on signup.",
    ),
    "ollama": Provider(
        key="ollama",
        label="Ollama (local)",
        endpoint="http://localhost:11434/v1/chat/completions",
        default_model="llama3.2",
        models=["llama3.2", "qwen2.5:7b", "gemma3:4b", "phi4"],
        docs="https://ollama.com/download",
        needs_key=False,
        note="Runs on your own computer. Nothing leaves the machine.",
    ),
    "custom": Provider(
        key="custom",
        label="Custom OpenAI-compatible",
        endpoint="",
        default_model="",
        models=[],
        docs="",
        needs_key=True,
        note="Point this at any /chat/completions endpoint (LM Studio, vLLM…).",
    ),
}


class LLMError(RuntimeError):
    pass


def _clean(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [m for m in messages if m.get("content")]


# --------------------------------------------------------------------------- #
# OpenAI-compatible chat
# --------------------------------------------------------------------------- #

def _openai_payload(model: str, messages, temperature, max_tokens, stream):
    return {
        "model": model,
        "messages": _clean(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def _openai_headers(provider: Provider, api_key: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider.key == "openrouter":
        headers["HTTP-Referer"] = "https://sensygent.streamlit.app"
        headers["X-Title"] = "SensyGent"
    return headers


def stream_openai_compatible(
    provider: Provider,
    model: str,
    messages: List[Dict[str, str]],
    api_key: str,
    temperature: float = 0.8,
    max_tokens: int = 700,
    endpoint: Optional[str] = None,
) -> Iterator[str]:
    url = (endpoint or provider.endpoint).strip()
    if not url:
        raise LLMError("No endpoint configured for the custom provider.")
    payload = _openai_payload(model, messages, temperature, max_tokens, True)
    try:
        response = requests.post(
            url,
            headers=_openai_headers(provider, api_key),
            json=payload,
            timeout=TIMEOUT,
            stream=True,
        )
    except requests.RequestException as exc:  # pragma: no cover - network
        raise LLMError(f"Could not reach {provider.label}: {exc}") from exc

    if response.status_code >= 400:
        detail = _error_detail(response)
        raise LLMError(f"{provider.label} returned {response.status_code}: {detail}")

    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        if raw_line.startswith("data:"):
            raw_line = raw_line[5:].strip()
        if raw_line == "[DONE]":
            break
        try:
            chunk = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if not piece and choice.get("text"):
                piece = choice["text"]
            if piece:
                yield piece


# --------------------------------------------------------------------------- #
# Google Gemini
# --------------------------------------------------------------------------- #

def _gemini_convert(messages: List[Dict[str, str]]):
    system_parts, contents = [], []
    for message in _clean(messages):
        role = message["role"]
        text = message["content"]
        if role == "system":
            system_parts.append(text)
        else:
            contents.append({
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": text}],
            })
    return system_parts, contents


def stream_gemini(
    provider: Provider,
    model: str,
    messages: List[Dict[str, str]],
    api_key: str,
    temperature: float = 0.8,
    max_tokens: int = 700,
    endpoint: Optional[str] = None,
) -> Iterator[str]:
    url = (endpoint or provider.endpoint).format(model=model)
    system_parts, contents = _gemini_convert(messages)
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    try:
        response = requests.post(
            url,
            params={"key": api_key, "alt": "sse"},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT,
            stream=True,
        )
    except requests.RequestException as exc:  # pragma: no cover - network
        raise LLMError(f"Could not reach Gemini: {exc}") from exc

    if response.status_code >= 400:
        raise LLMError(f"Gemini returned {response.status_code}: {_error_detail(response)}")

    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line or not raw_line.startswith("data:"):
            continue
        body = raw_line[5:].strip()
        if not body or body == "[DONE]":
            continue
        try:
            chunk = json.loads(body)
        except json.JSONDecodeError:
            continue
        for candidate in chunk.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text"):
                    yield part["text"]


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] or "no details"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message", error))[:200]
        if isinstance(error, str):
            return error[:200]
        if "detail" in payload:
            return str(payload["detail"])[:200]
    return str(payload)[:200]


def complete(
    provider: Provider,
    model: str,
    messages: List[Dict[str, str]],
    api_key: str,
    temperature: float = 0.8,
    max_tokens: int = 700,
    endpoint: Optional[str] = None,
) -> str:
    """Non-streaming convenience wrapper."""
    if provider.style == "gemini":
        chunks = stream_gemini(provider, model, messages, api_key, temperature, max_tokens, endpoint)
    else:
        chunks = stream_openai_compatible(provider, model, messages, api_key, temperature, max_tokens, endpoint)
    return "".join(chunks).strip()


def stream(
    provider: Provider,
    model: str,
    messages: List[Dict[str, str]],
    api_key: str,
    temperature: float = 0.8,
    max_tokens: int = 700,
    endpoint: Optional[str] = None,
) -> Iterator[str]:
    if provider.style == "gemini":
        yield from stream_gemini(provider, model, messages, api_key, temperature, max_tokens, endpoint)
    else:
        yield from stream_openai_compatible(provider, model, messages, api_key, temperature, max_tokens, endpoint)


# --------------------------------------------------------------------------- #
# Key discovery
# --------------------------------------------------------------------------- #

ENV_KEYS = {
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "ollama": (),
    "custom": ("SENSYGENT_API_KEY", "OPENAI_API_KEY"),
}


def find_key(provider_key: str, secrets: Optional[object] = None) -> str:
    """Look for an API key in st.secrets, then in the environment."""
    names = ENV_KEYS.get(provider_key, ())
    if secrets is not None:
        for name in names:
            try:
                value = secrets.get(name)  # type: ignore[union-attr]
            except Exception:
                value = None
            if value:
                return str(value).strip()
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""
