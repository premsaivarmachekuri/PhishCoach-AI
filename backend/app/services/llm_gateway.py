import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from app.services.config import get_settings
from app.services.db import DBProtocol


class LLMUnavailableError(RuntimeError):
    """The live LLM could not produce a usable answer. There is intentionally no canned substitute."""


@dataclass
class ModelBudgetState:
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    updated_at: float = 0.0


# Shared across requests (a new LLMGateway is built per request, so state must live at module level).
_BUDGETS: dict[str, ModelBudgetState] = {}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_reasoning_model(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


class LLMGateway:
    """Groq gateway: per-model rate tracking, bounded retry/backoff, DB telemetry, LLM model fallback chain."""

    GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, db: DBProtocol):
        self.db = db

    # ---- telemetry -------------------------------------------------------------------------
    def _update_budget_from_headers(self, model: str, headers: httpx.Headers) -> None:
        state = _BUDGETS.setdefault(model, ModelBudgetState())
        rem_req = headers.get("x-ratelimit-remaining-requests")
        rem_tok = headers.get("x-ratelimit-remaining-tokens")
        if rem_req is not None and rem_req.isdigit():
            state.remaining_requests = int(rem_req)
        if rem_tok is not None and rem_tok.isdigit():
            state.remaining_tokens = int(rem_tok)
        state.updated_at = time.time()

    def _log_call(
        self,
        model: str,
        purpose: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        status: str,
    ) -> None:
        try:
            self.db.insert(
                "llm_calls",
                {
                    "model": model,
                    "purpose": purpose,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "latency_ms": latency_ms,
                    "status": status,
                },
            )
        except Exception:
            pass  # telemetry must never break a user request

    # ---- request building ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        key = get_settings().groq_api_key.strip()
        if not key:
            raise LLMUnavailableError("GROQ_API_KEY is not configured")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    @staticmethod
    def _payload(
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        response_format: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if _is_reasoning_model(model):
            # Reasoning tokens count against max_tokens; keep effort low and leave headroom.
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = max_tokens + 800
        if response_format:
            payload["response_format"] = response_format
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _backoff_seconds(resp: httpx.Response | None, attempt: int) -> float:
        retry_after = resp.headers.get("retry-after") if resp is not None else None
        if retry_after:
            try:
                return min(float(retry_after), 8.0)
            except ValueError:
                pass
        return min(0.5 * (2**attempt), 8.0)

    # ---- model fallback chain (the ONLY fallback in the system: LLM -> next LLM) ----------------
    @staticmethod
    def _chain(model: str) -> list[str]:
        extra = [m.strip() for m in get_settings().model_fallbacks.split(",") if m.strip()]
        return [model] + [m for m in extra if m != model]

    async def complete(self, messages, model, purpose, **kw) -> tuple[str, str]:
        """Returns (content, model_used); tries each model in the chain before giving up."""
        errors: list[str] = []
        for m in self._chain(model):
            try:
                return await self._complete_one(messages, m, purpose, **kw)
            except LLMUnavailableError as exc:
                errors.append(f"{m}: {exc}")
        raise LLMUnavailableError("all models failed - " + " | ".join(errors))

    async def stream(self, messages, model, purpose, **kw) -> AsyncIterator[str]:
        """Streams tokens; fails over to the next model only if nothing was emitted yet."""
        errors: list[str] = []
        for m in self._chain(model):
            started = False
            try:
                async for tok in self._stream_one(messages, m, purpose, **kw):
                    started = True
                    yield tok
                return
            except LLMUnavailableError as exc:
                if started:
                    raise
                errors.append(f"{m}: {exc}")
        raise LLMUnavailableError("all models failed - " + " | ".join(errors))

    # ---- non-streaming ---------------------------------------------------------------------
    async def _complete_one(
        self,
        messages: list[dict[str, str]],
        model: str,
        purpose: str,
        max_tokens: int = 500,
        temperature: float = 0.4,
        response_format: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> tuple[str, str]:
        """Returns (content, model_used). Raises LLMUnavailableError when retries are exhausted."""
        headers = self._headers()
        payload = self._payload(model, messages, max_tokens, temperature, response_format)
        last_error = "unknown error"

        async with httpx.AsyncClient(timeout=45.0) as client:
            for attempt in range(max_retries + 1):
                t0 = time.perf_counter()
                resp: httpx.Response | None = None
                try:
                    resp = await client.post(self.GROQ_CHAT_URL, headers=headers, json=payload)
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    self._update_budget_from_headers(model, resp.headers)

                    if resp.status_code in RETRYABLE_STATUS:
                        tag = "rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}"
                        self._log_call(model, purpose, 0, 0, latency_ms, tag)
                        last_error = f"HTTP {resp.status_code} from Groq"
                        if attempt < max_retries:
                            await asyncio.sleep(self._backoff_seconds(resp, attempt))
                            continue
                        break
                    if resp.status_code >= 400:
                        self._log_call(model, purpose, 0, 0, latency_ms, f"http_{resp.status_code}")
                        detail = resp.text[:300]
                        raise LLMUnavailableError(f"Groq rejected the request (HTTP {resp.status_code}): {detail}")

                    data = resp.json()
                    usage = data.get("usage", {})
                    content = (data["choices"][0]["message"].get("content") or "").strip()
                    self._log_call(
                        model,
                        purpose,
                        int(usage.get("prompt_tokens", 0)),
                        int(usage.get("completion_tokens", 0)),
                        latency_ms,
                        "ok" if content else "empty",
                    )
                    if not content:
                        last_error = "model returned an empty response"
                        if attempt < max_retries:
                            continue
                        break
                    return content, model
                except LLMUnavailableError:
                    raise
                except (httpx.TransportError, ValueError, KeyError, IndexError) as exc:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    self._log_call(model, purpose, 0, 0, latency_ms, "error")
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < max_retries:
                        await asyncio.sleep(self._backoff_seconds(None, attempt))
                        continue
                    break

        raise LLMUnavailableError(f"LLM request failed after {max_retries + 1} attempts: {last_error}")

    # ---- streaming -------------------------------------------------------------------------
    async def _stream_one(
        self,
        messages: list[dict[str, str]],
        model: str,
        purpose: str,
        max_tokens: int = 350,
        temperature: float = 0.4,
        max_retries: int = 2,
    ) -> AsyncIterator[str]:
        """Streams tokens. Retries only before the first token; mid-stream failure raises."""
        headers = self._headers()
        payload = self._payload(model, messages, max_tokens, temperature, stream=True)
        last_error = "unknown error"

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            for attempt in range(max_retries + 1):
                t0 = time.perf_counter()
                yielded = False
                token_count = 0
                try:
                    async with client.stream("POST", self.GROQ_CHAT_URL, headers=headers, json=payload) as resp:
                        self._update_budget_from_headers(model, resp.headers)
                        if resp.status_code in RETRYABLE_STATUS:
                            tag = "rate_limited" if resp.status_code == 429 else f"http_{resp.status_code}"
                            self._log_call(model, purpose, 0, 0, int((time.perf_counter() - t0) * 1000), tag)
                            last_error = f"HTTP {resp.status_code} from Groq"
                            if attempt < max_retries:
                                await asyncio.sleep(self._backoff_seconds(resp, attempt))
                                continue
                            break
                        if resp.status_code >= 400:
                            body = (await resp.aread()).decode("utf-8", "replace")[:300]
                            self._log_call(model, purpose, 0, 0, int((time.perf_counter() - t0) * 1000), f"http_{resp.status_code}")
                            raise LLMUnavailableError(f"Groq rejected the request (HTTP {resp.status_code}): {body}")

                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            chunk = line[6:].strip()
                            if chunk == "[DONE]":
                                break
                            try:
                                delta = json.loads(chunk)["choices"][0].get("delta", {}).get("content")
                            except (ValueError, KeyError, IndexError):
                                continue
                            if delta:
                                token_count += 1
                                yielded = True
                                yield delta

                        self._log_call(
                            model,
                            purpose,
                            0,
                            token_count,
                            int((time.perf_counter() - t0) * 1000),
                            "ok" if yielded else "empty",
                        )
                        if yielded:
                            return
                        last_error = "model returned an empty stream"
                        if attempt < max_retries:
                            continue
                        break
                except LLMUnavailableError:
                    raise
                except httpx.TransportError as exc:
                    self._log_call(model, purpose, 0, token_count, int((time.perf_counter() - t0) * 1000), "error")
                    if yielded:
                        raise LLMUnavailableError(f"LLM stream interrupted: {exc}") from exc
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt < max_retries:
                        await asyncio.sleep(self._backoff_seconds(None, attempt))
                        continue
                    break

        raise LLMUnavailableError(f"LLM stream failed after {max_retries + 1} attempts: {last_error}")

    # ---- telemetry read model --------------------------------------------------------------
    def get_budget_status(self) -> dict[str, Any]:
        recent = self.db.select("llm_calls", order="ts", desc=True, limit=200)
        by_model: dict[str, dict[str, Any]] = {}
        for c in recent:
            m = by_model.setdefault(
                c["model"],
                {"calls": 0, "errors": 0, "rate_limited": 0, "tokens": 0, "_lat": []},
            )
            m["calls"] += 1
            m["tokens"] += int(c.get("prompt_tokens", 0)) + int(c.get("completion_tokens", 0))
            if c["status"] == "rate_limited":
                m["rate_limited"] += 1
            elif c["status"] not in ("ok",):
                m["errors"] += 1
            if c["status"] == "ok":
                m["_lat"].append(int(c.get("latency_ms", 0)))
        models: dict[str, dict[str, Any]] = {}
        for name, m in by_model.items():
            lat = m.pop("_lat")
            state = _BUDGETS.get(name)
            models[name] = {
                **m,
                "avg_latency_ms": round(sum(lat) / len(lat)) if lat else None,
                "remaining_requests": state.remaining_requests if state else None,
                "remaining_tokens": state.remaining_tokens if state else None,
            }
        return {"window_calls": len(recent), "models": models}
