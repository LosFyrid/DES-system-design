"""
Shared retry policy for LLM calls.

The OpenAI SDK has its own small retry loop, but it does not expose the full
backoff curve or a long max elapsed window. This module provides a single
project-owned policy so ReasoningBank, CoreRAG, and LargeRAG behave consistently.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")


DEFAULT_RETRYABLE_STATUS_CODES: Tuple[int, ...] = (
    408,
    409,
    429,
    500,
    502,
    503,
    504,
)


@dataclass(frozen=True)
class LLMRetryPolicy:
    """Configuration for project-level LLM retry behavior."""

    enabled: bool = True
    max_elapsed_seconds: float = 600.0
    max_attempts: int = 12
    initial_delay_seconds: float = 2.0
    max_delay_seconds: float = 120.0
    exponential_base: float = 2.0
    jitter: float = 0.25
    respect_retry_after: bool = True
    retryable_status_codes: Sequence[int] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_STATUS_CODES
    )
    # Disable SDK retries by default so our 600s window is the single source of truth.
    sdk_max_retries: Optional[int] = 0

    def openai_client_kwargs(self) -> Dict[str, Any]:
        """Return kwargs to pass to OpenAI-compatible SDK clients."""
        if self.sdk_max_retries is None:
            return {}
        return {"max_retries": int(self.sdk_max_retries)}


def _parse_bool(raw: Any, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(raw: Any, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_int(raw: Any, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _parse_status_codes(raw: Any, default: Sequence[int]) -> Sequence[int]:
    if raw is None or raw == "":
        return tuple(default)
    if isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = str(raw).replace(";", ",").split(",")

    parsed = []
    for value in values:
        try:
            parsed.append(int(str(value).strip()))
        except (TypeError, ValueError):
            continue
    return tuple(parsed) or tuple(default)


def _env_value(env: Mapping[str, str], *names: str) -> Optional[str]:
    for name in names:
        value = env.get(name)
        if value is not None:
            return value
    return None


def coerce_retry_policy(
    config: Optional[Mapping[str, Any]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> LLMRetryPolicy:
    """
    Build an LLMRetryPolicy from config plus environment overrides.

    Environment variables are intentionally generic because CoreRAG/LargeRAG are
    loaded through separate config systems:
    - LLM_RETRY_MAX_ELAPSED_SECONDS
    - LLM_RETRY_MAX_ATTEMPTS
    - LLM_RETRY_INITIAL_DELAY_SECONDS
    - LLM_RETRY_MAX_DELAY_SECONDS
    - LLM_RETRY_EXPONENTIAL_BASE
    - LLM_RETRY_JITTER
    - LLM_RETRY_SDK_MAX_RETRIES
    """
    cfg: Mapping[str, Any] = config or {}
    environment = env if env is not None else os.environ
    default = LLMRetryPolicy()

    sdk_max_retries_raw = _env_value(
        environment,
        "LLM_RETRY_SDK_MAX_RETRIES",
        "OPENAI_SDK_MAX_RETRIES",
    )
    sdk_max_retries_cfg = cfg.get("sdk_max_retries", default.sdk_max_retries)
    if sdk_max_retries_raw is not None:
        default_sdk_max_retries = (
            0
            if sdk_max_retries_cfg is None
            else _parse_int(sdk_max_retries_cfg, 0)
        )
        sdk_max_retries: Optional[int] = _parse_int(
            sdk_max_retries_raw,
            default_sdk_max_retries,
        )
    elif sdk_max_retries_cfg is None:
        sdk_max_retries = None
    else:
        sdk_max_retries = _parse_int(sdk_max_retries_cfg, 0)

    return LLMRetryPolicy(
        enabled=_parse_bool(
            _env_value(environment, "LLM_RETRY_ENABLED"),
            _parse_bool(cfg.get("enabled"), default.enabled),
        ),
        max_elapsed_seconds=max(
            0.0,
            _parse_float(
                _env_value(environment, "LLM_RETRY_MAX_ELAPSED_SECONDS"),
                _parse_float(cfg.get("max_elapsed_seconds"), default.max_elapsed_seconds),
            ),
        ),
        max_attempts=max(
            1,
            _parse_int(
                _env_value(environment, "LLM_RETRY_MAX_ATTEMPTS"),
                _parse_int(cfg.get("max_attempts"), default.max_attempts),
            ),
        ),
        initial_delay_seconds=max(
            0.0,
            _parse_float(
                _env_value(environment, "LLM_RETRY_INITIAL_DELAY_SECONDS"),
                _parse_float(cfg.get("initial_delay_seconds"), default.initial_delay_seconds),
            ),
        ),
        max_delay_seconds=max(
            0.0,
            _parse_float(
                _env_value(environment, "LLM_RETRY_MAX_DELAY_SECONDS"),
                _parse_float(cfg.get("max_delay_seconds"), default.max_delay_seconds),
            ),
        ),
        exponential_base=max(
            1.0,
            _parse_float(
                _env_value(environment, "LLM_RETRY_EXPONENTIAL_BASE"),
                _parse_float(cfg.get("exponential_base"), default.exponential_base),
            ),
        ),
        jitter=max(
            0.0,
            _parse_float(
                _env_value(environment, "LLM_RETRY_JITTER"),
                _parse_float(cfg.get("jitter"), default.jitter),
            ),
        ),
        respect_retry_after=_parse_bool(
            _env_value(environment, "LLM_RETRY_RESPECT_RETRY_AFTER"),
            _parse_bool(cfg.get("respect_retry_after"), default.respect_retry_after),
        ),
        retryable_status_codes=_parse_status_codes(
            _env_value(environment, "LLM_RETRY_STATUS_CODES"),
            _parse_status_codes(
                cfg.get("retryable_status_codes"),
                default.retryable_status_codes,
            ),
        ),
        sdk_max_retries=sdk_max_retries,
    )


def publish_retry_config_to_env(
    config: Optional[Mapping[str, Any]],
    *,
    overwrite: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> None:
    """Expose a config dict to env-only tool stacks such as CoreRAG/LargeRAG."""
    if not config:
        return

    target = env if env is not None else os.environ
    key_map = {
        "enabled": "LLM_RETRY_ENABLED",
        "max_elapsed_seconds": "LLM_RETRY_MAX_ELAPSED_SECONDS",
        "max_attempts": "LLM_RETRY_MAX_ATTEMPTS",
        "initial_delay_seconds": "LLM_RETRY_INITIAL_DELAY_SECONDS",
        "max_delay_seconds": "LLM_RETRY_MAX_DELAY_SECONDS",
        "exponential_base": "LLM_RETRY_EXPONENTIAL_BASE",
        "jitter": "LLM_RETRY_JITTER",
        "respect_retry_after": "LLM_RETRY_RESPECT_RETRY_AFTER",
        "sdk_max_retries": "LLM_RETRY_SDK_MAX_RETRIES",
    }
    for cfg_key, env_key in key_map.items():
        if cfg_key not in config or config[cfg_key] is None:
            continue
        if overwrite or env_key not in target:
            target[env_key] = str(config[cfg_key])

    if "retryable_status_codes" in config and (
        overwrite or "LLM_RETRY_STATUS_CODES" not in target
    ):
        codes = config.get("retryable_status_codes") or DEFAULT_RETRYABLE_STATUS_CODES
        if isinstance(codes, str):
            target["LLM_RETRY_STATUS_CODES"] = codes
        else:
            target["LLM_RETRY_STATUS_CODES"] = ",".join(str(c) for c in codes)


def _get_status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _get_headers(exc: BaseException) -> Mapping[str, Any]:
    headers = getattr(exc, "headers", None)
    if headers is not None:
        return headers
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    return headers or {}


def _header_get(headers: Mapping[str, Any], name: str) -> Optional[str]:
    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        if value is None:
            value = headers.get(name.title())
        if value is not None:
            return str(value)
    lower_name = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == lower_name:
                return str(value)
    except Exception:
        return None
    return None


def _parse_retry_after_seconds(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    value = raw.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _retry_after_delay(exc: BaseException) -> Optional[float]:
    headers = _get_headers(exc)
    retry_after_ms = _header_get(headers, "retry-after-ms")
    if retry_after_ms:
        try:
            return max(0.0, float(retry_after_ms) / 1000.0)
        except ValueError:
            pass
    return _parse_retry_after_seconds(_header_get(headers, "retry-after"))


def is_retryable_exception(
    exc: BaseException,
    policy: LLMRetryPolicy,
) -> bool:
    """Return True for transient LLM/API failures worth retrying."""
    if isinstance(exc, (TypeError, ValueError, KeyError, AttributeError)):
        return False

    status_code = _get_status_code(exc)
    if status_code is not None:
        return int(status_code) in set(int(c) for c in policy.retryable_status_codes)

    exc_name = type(exc).__name__.lower()
    exc_module = type(exc).__module__.lower()
    text = str(exc).lower()
    transient_markers = (
        "timeout",
        "timed out",
        "connection",
        "connect",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "service unavailable",
        "too many requests",
        "rate limit",
        "ratelimit",
        "server disconnected",
    )
    if any(marker in exc_name for marker in ("timeout", "connection")):
        return True
    if any(marker in exc_module for marker in ("httpx", "urllib3", "requests", "openai")):
        return any(marker in text for marker in transient_markers)
    return any(marker in text for marker in transient_markers)


def _compute_delay(
    exc: BaseException,
    policy: LLMRetryPolicy,
    failed_attempts: int,
    remaining_window: float,
) -> float:
    if policy.respect_retry_after:
        retry_after = _retry_after_delay(exc)
        if retry_after is not None and retry_after > 0:
            return max(0.0, min(retry_after, policy.max_delay_seconds, remaining_window))

    raw_delay = policy.initial_delay_seconds * (
        policy.exponential_base ** max(0, failed_attempts - 1)
    )
    delay = min(raw_delay, policy.max_delay_seconds, remaining_window)
    if policy.jitter > 0 and delay > 0:
        multiplier = 1.0 + random.uniform(-policy.jitter, policy.jitter)
        delay = min(max(0.0, delay * multiplier), remaining_window)
    return max(0.0, delay)


def call_with_retry(
    fn: Callable[[], T],
    *,
    policy: Optional[LLMRetryPolicy] = None,
    operation_name: str = "LLM call",
    logger: Optional[logging.Logger] = None,
    sleep_func: Optional[Callable[[float], None]] = None,
    monotonic_func: Optional[Callable[[], float]] = None,
) -> T:
    """Run a synchronous LLM operation with exponential backoff."""
    retry_policy = policy or LLMRetryPolicy()
    if not retry_policy.enabled:
        return fn()

    log = logger or logging.getLogger(__name__)
    sleep = sleep_func or time.sleep
    monotonic = monotonic_func or time.monotonic
    start = monotonic()
    attempt = 0

    while True:
        attempt += 1
        try:
            return fn()
        except Exception as exc:
            elapsed = max(0.0, monotonic() - start)
            remaining = retry_policy.max_elapsed_seconds - elapsed
            can_retry = (
                attempt < retry_policy.max_attempts
                and remaining > 0
                and is_retryable_exception(exc, retry_policy)
            )
            if not can_retry:
                log.error(
                    "%s failed after %s attempt(s), elapsed=%.1fs: %s",
                    operation_name,
                    attempt,
                    elapsed,
                    exc,
                )
                raise

            delay = _compute_delay(exc, retry_policy, attempt, remaining)
            log.warning(
                "%s failed with retryable error on attempt %s/%s; "
                "retrying in %.1fs (elapsed=%.1fs, window=%.1fs): %s",
                operation_name,
                attempt,
                retry_policy.max_attempts,
                delay,
                elapsed,
                retry_policy.max_elapsed_seconds,
                exc,
            )
            if delay > 0:
                sleep(delay)


async def async_call_with_retry(
    fn: Callable[[], Any],
    *,
    policy: Optional[LLMRetryPolicy] = None,
    operation_name: str = "LLM async call",
    logger: Optional[logging.Logger] = None,
) -> Any:
    """Run an async LLM operation with exponential backoff."""
    retry_policy = policy or LLMRetryPolicy()
    if not retry_policy.enabled:
        return await fn()

    log = logger or logging.getLogger(__name__)
    start = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        try:
            return await fn()
        except Exception as exc:
            elapsed = max(0.0, time.monotonic() - start)
            remaining = retry_policy.max_elapsed_seconds - elapsed
            can_retry = (
                attempt < retry_policy.max_attempts
                and remaining > 0
                and is_retryable_exception(exc, retry_policy)
            )
            if not can_retry:
                log.error(
                    "%s failed after %s attempt(s), elapsed=%.1fs: %s",
                    operation_name,
                    attempt,
                    elapsed,
                    exc,
                )
                raise

            delay = _compute_delay(exc, retry_policy, attempt, remaining)
            log.warning(
                "%s failed with retryable error on attempt %s/%s; "
                "retrying in %.1fs (elapsed=%.1fs, window=%.1fs): %s",
                operation_name,
                attempt,
                retry_policy.max_attempts,
                delay,
                elapsed,
                retry_policy.max_elapsed_seconds,
                exc,
            )
            if delay > 0:
                await asyncio.sleep(delay)
