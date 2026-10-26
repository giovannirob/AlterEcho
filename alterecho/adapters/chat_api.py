from ..i18n import message as t
"""Opt-in OpenAI/OpenRouter HTTP adapter; no credentials are persisted."""
import asyncio
import json
import os
import time

import httpx

from .base import Reply
from ..config import BridgeError
from ..history import ollama_history, now
from ..integrations import validate_profile, API_URLS


class ChatAPIAdapter:
    def __init__(self, config, profile, speaker, transport=None):
        validate_profile(profile)
        if profile["provider"] not in API_URLS:
            raise BridgeError(t('errors.chat_api.unsupported_api_provider'))
        self.config, self.profile, self.speaker = config, dict(profile), speaker
        self.client = httpx.AsyncClient(base_url=profile["url"] + "/", timeout=config.timeout,
                                        trust_env=False, follow_redirects=False, transport=transport)

    def headers(self):
        key = os.environ.get(self.profile["api_key_env"], "").strip()
        if not key:
            raise BridgeError(t('errors.chat_api.adapter_set_in_the_server_environment_before_startup' ,p0=self.profile['name'], p1=self.profile['api_key_env']))
        return {"Authorization": "Bearer " + key}

    async def models(self):
        try:
            response = await self.client.get("models", headers=self.headers())
            if response.status_code != 200:
                raise BridgeError(t('errors.chat_api.catalog_http_check_access_and_api_key' ,p0=self.profile['name'], p1=response.status_code))
            models = response.json().get("data", [])
            return sorted(m["id"] for m in models if isinstance(m, dict) and isinstance(m.get("id"), str))
        except (httpx.HTTPError, ValueError) as e:
            raise BridgeError(t('errors.chat_api.catalog_unreachable' ,p0=self.profile['name'], p1=type(e).__name__)) from e

    async def generate(self, conversation, checkpoint):
        cfg = self.config
        payload = {"model": self.profile["model"], "messages": ollama_history(cfg, conversation, self.speaker),
                   "stream": True, "stream_options": {"include_usage": True}}
        limit_key = "max_completion_tokens" if self.profile["provider"] == "openai" else "max_tokens"
        payload[limit_key] = cfg.api_max_output_tokens
        parts, usage = [], {}
        finish, done, returned_model = None, False, self.profile["model"]
        last_checkpoint = 0.0
        try:
            async with asyncio.timeout(cfg.timeout):
                async with self.client.stream("POST", "chat/completions", json=payload, headers=self.headers()) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise BridgeError(t('errors.chat_api.generation_http_check_access_quotas_and_model' ,p0=self.profile['name'], p1=response.status_code))
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        event = line[5:].strip()
                        if event == "[DONE]":
                            done = True
                            break
                        data = json.loads(event)
                        if data.get("error"):
                            raise BridgeError(t('errors.chat_api.generation_error_in_stream' ,p0=self.profile['name']))
                        if isinstance(data.get("model"), str):
                            returned_model = data["model"]
                        values = data.get("usage") or {}
                        for source, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
                            value = values.get(source)
                            if type(value) is int and value >= 0:
                                usage[target] = value
                        for choice in data.get("choices", []):
                            delta = choice.get("delta") or {}
                            if delta.get("tool_calls") or delta.get("function_call"):
                                raise BridgeError(t('errors.chat_api.api_tool_request_rejected_conversations_do_not_execute_commands'))
                            part = delta.get("content")
                            if isinstance(part, str) and part:
                                parts.append(part)
                                conversation.partial = {"speaker": self.speaker, "model": returned_model,
                                                        "text": "".join(parts), "timestamp": now()}
                                if hasattr(checkpoint, "delta"):
                                    checkpoint.delta(self.speaker, returned_model, part)
                                if time.monotonic() - last_checkpoint > .5:
                                    checkpoint()
                                    last_checkpoint = time.monotonic()
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
            if not done or finish != "stop":
                raise BridgeError(t('errors.chat_api.incomplete_response_or_limit_reached_partial_preserved' ,p0=self.profile['name'], p1=finish or 'stream interrupted'))
            text = "".join(parts)
            if not text.strip():
                raise BridgeError(t('errors.chat_api.empty_response' ,p0=self.profile['name']))
            return Reply(text, returned_model, usage)
        except (httpx.HTTPError, ValueError, TimeoutError) as e:
            raise BridgeError(t('errors.chat_api.generation_interrupted' ,p0=self.profile['name'], p1=type(e).__name__)) from e
        finally:
            if conversation.partial:
                checkpoint()

    async def close(self):
        await self.client.aclose()
