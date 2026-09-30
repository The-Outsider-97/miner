"""Server-side TAO market pricing with bounded CoinGecko caching."""

from __future__ import annotations

import json
import os
import time

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx # type: ignore

from ..utils.config_loader import get_config_section
from ..utils.miner_helpers import PROJECT_ROOT

_SUPPORTED = ("USD", "EUR", "GBP", "BTC")


def _iso_timestamp(epoch: int | float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


def _settings() -> dict[str, Any]:
    config = get_config_section("market")
    currencies = tuple(str(item).upper() for item in config.get("currencies", _SUPPORTED))
    if currencies != _SUPPORTED:
        raise ValueError("market.currencies must be exactly USD, EUR, GBP, BTC")

    return {
        "provider": str(config.get("provider") or "coingecko"),
        "coin_id": str(config.get("coin_id") or "bittensor"),
        "currencies": currencies,
        "api_base_url": str(config.get("api_base_url") or "https://api.coingecko.com/api/v3").rstrip("/"),
        "api_key_env": str(config.get("api_key_env") or "COINGECKO_API_KEY"),
        "cache_seconds": int(config.get("cache_seconds") or 300),
        "request_timeout_seconds": float(config.get("request_timeout_seconds") or 10.0),
        "cache_path": (
            PROJECT_ROOT
            / str(config.get("cache_path") or "state/tao_market_cache.json")).resolve(),
    }


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(value, dict):
        return None

    prices = value.get("prices")

    if not isinstance(prices, dict):
        return None

    if any(currency not in prices for currency in _SUPPORTED):
        return None

    return value


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    os.replace(temporary, path)


def _public_state(payload: dict[str, Any], *, status: str, message: str | None) -> dict[str, Any]:
    return {
        "status": status,
        "provider": "coingecko",
        "asset": "TAO",
        "prices": {
            currency: str(payload["prices"][currency])
            for currency in _SUPPORTED
        },
        "updated_at": payload.get("updated_at"),
        "fetched_at": payload.get("fetched_at"),
        "message": message,
    }


def _parse_provider_response(text: str, *, coin_id: str) -> dict[str, Any]:
    try:
        document = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError("CoinGecko returned malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("CoinGecko response root is invalid")

    token = document.get(coin_id)
    if not isinstance(token, dict):
        raise ValueError("CoinGecko response does not contain Bittensor")

    prices: dict[str, str] = {}
    for currency in _SUPPORTED:
        raw = token.get(currency.lower())
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"CoinGecko response is missing {currency}") from exc

        if value <= 0:
            raise ValueError(f"CoinGecko returned invalid {currency} price")

        prices[currency] = format(value, "f")

    last_updated = token.get("last_updated_at")

    if isinstance(last_updated, Decimal):
        last_updated = int(last_updated)

    if not isinstance(last_updated, int):
        last_updated = int(time.time())

    now = int(time.time())

    return {
        "prices": prices,
        "updated_at": _iso_timestamp(last_updated),
        "fetched_at": _iso_timestamp(now),
        "fetched_epoch": now,
    }


def get_tao_market_state() -> dict[str, Any]:
    settings = _settings()
    cache_path: Path = settings["cache_path"]
    cache = _read_cache(cache_path)
    now = int(time.time())

    if cache is not None:
        fetched_epoch = cache.get("fetched_epoch")

        if (
            isinstance(fetched_epoch, int)
            and now - fetched_epoch
            < settings["cache_seconds"]
        ):
            return _public_state(cache, status="ready", message=None)

    api_key = os.getenv(settings["api_key_env"], "").strip()

    if not api_key:
        if cache is not None:
            return _public_state(
                cache,
                status="stale",
                message=("TAO market data is stale because CoinGecko credentials are unavailable."),
            )

        return {
            "status": "unavailable",
            "provider": "coingecko",
            "asset": "TAO",
            "prices": None,
            "updated_at": None,
            "fetched_at": None,
            "message": "TAO price unavailable.",
        }

    params = {"ids": settings["coin_id"], "vs_currencies": ",".join(item.lower() for item in settings["currencies"]), "include_last_updated_at": "true"}

    headers = {"x-cg-demo-api-key": api_key, "Accept": "application/json"}

    try:
        with httpx.Client(
            base_url=settings["api_base_url"],
            timeout=settings["request_timeout_seconds"],
            headers=headers,
        ) as client:
            response = client.get("/simple/price", params=params)
            response.raise_for_status()

        payload = _parse_provider_response(response.text, coin_id=settings["coin_id"])
        _write_cache(cache_path, payload)

        return _public_state(payload, status="ready", message=None)

    except (httpx.HTTPError, OSError, ValueError):
        if cache is not None:
            return _public_state(
                cache,
                status="stale",
                message=("TAO market data could not be refreshed; the displayed quote is stale."),
            )

        return {
            "status": "unavailable",
            "provider": "coingecko",
            "asset": "TAO",
            "prices": None,
            "updated_at": None,
            "fetched_at": None,
            "message": "TAO price unavailable.",
        }