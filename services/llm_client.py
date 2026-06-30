# services/llm_client.py
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from config import (
    LLM_PROVIDER,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_THINKING,
    LLM_REASONING_EFFORT,
    LLM_MAX_TOKENS,
)


def get_client() -> OpenAI:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is missing")

    return OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
    )


def _extra_body() -> dict[str, Any]:
    if LLM_PROVIDER == "deepseek":
        return {
            "thinking": {
                "type": LLM_THINKING
            }
        }

    return {}


def _reasoning_effort() -> str | None:
    if LLM_PROVIDER == "deepseek":
        return LLM_REASONING_EFFORT

    return None


def chat_text(
    prompt: str,
    temperature: float = 0.2,
    system_prompt: str | None = None,
    model: str | None = None,
) -> str:
    client = get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": LLM_MAX_TOKENS,
        "stream": False,
    }

    extra_body = _extra_body()
    if extra_body:
        kwargs["extra_body"] = extra_body

    reasoning_effort = _reasoning_effort()
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    resp = client.chat.completions.create(**kwargs)

    return resp.choices[0].message.content or ""


def chat_json(
    prompt: str,
    temperature: float = 0.1,
    system_prompt: str | None = None,
    model: str | None = None,
) -> Any:
    client = get_client()

    messages = [
        {
            "role": "system",
            "content": system_prompt
            or "你是一个严格的 JSON 生成器。只能输出合法 JSON object，不要输出 Markdown。",
        },
        {
            "role": "user",
            "content": (
                prompt
                + "\n\n请只输出一个合法 JSON object，不要输出 Markdown，不要输出解释。"
            ),
        },
    ]

    kwargs = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": LLM_MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "stream": False,
    }

    extra_body = _extra_body()
    if extra_body:
        kwargs["extra_body"] = extra_body

    reasoning_effort = _reasoning_effort()
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    resp = client.chat.completions.create(**kwargs)

    text = resp.choices[0].message.content or ""

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])

        raise ValueError(f"Model did not return valid JSON: {text[:500]}")
