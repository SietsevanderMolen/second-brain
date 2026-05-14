#!/usr/bin/env python3
"""LLM client abstraction for Anthropic, OpenAI-compatible, and OpenClaw endpoints."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


class LLMClient:
    """Simple unified chat-completion client interface."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.api_config = self.config.get("api", {})
        self.provider = self.api_config.get("provider", "anthropic").lower()
        self.model = self.api_config.get("model", "claude-sonnet-4-20250514")

        if self.provider == "anthropic":
            self._init_anthropic()
        elif self.provider in ("openai", "openai_compatible", "openai-compatible"):
            self._init_openai_compatible()
        elif self.provider == "openclaw":
            self._init_openclaw()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _init_anthropic(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from exc

        api_key = resolve_api_key(self.api_config, "anthropic")
        if not api_key:
            raise ValueError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY or configure api.key/api.key_env."
            )

        self._anthropic = Anthropic(api_key=api_key)

    def _init_openai_compatible(self) -> None:
        base_url = self.api_config.get("base_url", "http://127.0.0.1:1234")
        self._openai_url = f"{base_url.rstrip('/')}/v1/chat/completions"
        self._openai_api_key = resolve_api_key(self.api_config, "openai")

    def _init_openclaw(self) -> None:
        openclaw_cfg = self.api_config.get("openclaw", {})
        chat_url = openclaw_cfg.get("chat_url") or self.api_config.get("chat_url")
        if not chat_url:
            raise ValueError(
                "OpenClaw provider requires api.openclaw.chat_url (or api.chat_url) in config.yaml"
            )

        self._openclaw_url = chat_url
        self._openclaw_agent = openclaw_cfg.get("agent") or self.api_config.get("agent")
        self._openclaw_api_key = resolve_api_key(openclaw_cfg, "openclaw") or resolve_api_key(self.api_config, "openclaw")

    def generate(self, prompt: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
        if self.provider == "anthropic":
            response = self._anthropic.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            parts = []
            for block in getattr(response, "content", []):
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            return "".join(parts).strip()

        if self.provider in ("openai", "openai_compatible", "openai-compatible"):
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            data = _post_json(self._openai_url, payload, bearer_token=self._openai_api_key)
            return _extract_openai_style_text(data)

        if self.provider == "openclaw":
            payload: Dict[str, Any] = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if self.model:
                payload["model"] = self.model
            if self._openclaw_agent:
                payload["agent"] = self._openclaw_agent

            data = _post_json(self._openclaw_url, payload, bearer_token=self._openclaw_api_key)

            if isinstance(data.get("content"), str):
                return data["content"].strip()
            return _extract_openai_style_text(data)

        raise ValueError(f"Unsupported provider: {self.provider}")


def _post_json(url: str, payload: Dict[str, Any], bearer_token: Optional[str] = None) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc


def _extract_openai_style_text(response_json: Dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices in response: {response_json}")

    message = choices[0].get("message", {})
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "".join(text_parts).strip()

    raise RuntimeError(f"Unsupported response content format: {content}")


def resolve_api_key(config: Dict[str, Any], provider: str) -> Optional[str]:
    """Resolve API key from config or env vars, with OpenClaw auth-profile fallback for Anthropic."""
    direct_key = config.get("key")
    if direct_key:
        return direct_key

    key_env = config.get("key_env")
    if key_env:
        env_val = os.environ.get(key_env)
        if env_val:
            return env_val

    provider_env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openclaw": "OPENCLAW_API_KEY",
    }
    default_env = provider_env_map.get(provider)
    if default_env:
        env_val = os.environ.get(default_env)
        if env_val:
            return env_val

    if provider == "anthropic":
        auth_profiles_path = Path.home() / ".openclaw/agents/main/agent/auth-profiles.json"
        try:
            if auth_profiles_path.exists():
                data = json.loads(auth_profiles_path.read_text())
                profiles = data.get("profiles", data)
                if "anthropic:default" in profiles:
                    return profiles["anthropic:default"].get("token")
        except Exception:
            return None

    return None


def create_llm_client(config: Dict[str, Any]) -> LLMClient:
    """Factory helper for call sites."""
    return LLMClient(config)
