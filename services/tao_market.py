"""Server-side TAO market pricing with rotating, cached providers."""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import httpx  # type: ignore

from ..utils.config_loader import get_config_section  # type: ignore
from ..utils.miner_helpers import PROJECT_ROOT  # type: ignore

_SUPPORTED = ("USD", "EUR", "GBP",
              # "BTC"
              )
_PROVIDER_ORDER = ("cryptoapis", "freecryptoapi", "coinapi")


def _iso(epoch: int | float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _decimal(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} is missing or invalid") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return parsed


def _json(text: str, provider: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text, parse_float=Decimal, parse_int=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{provider} returned malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{provider} response root is invalid")
    return value


def _settings() -> dict[str, Any]:
    config = get_config_section("market")
    currencies = tuple(str(item).upper() for item in config.get("currencies", _SUPPORTED))
    if currencies != _SUPPORTED:
        raise ValueError("market.currencies must be exactly USD, EUR, GBP")

    refresh_min = int(config.get("refresh_min_seconds") or 180)
    refresh_max = int(config.get("refresh_max_seconds") or 300)
    if not 180 <= refresh_min <= refresh_max <= 300:
        raise ValueError("market refresh window must remain between 180 and 300 seconds")

    raw_providers = config.get("providers")
    if not isinstance(raw_providers, Sequence) or isinstance(raw_providers, (str, bytes, bytearray)):
        raise ValueError("market.providers must be a sequence")

    providers: list[dict[str, str]] = []
    for raw in raw_providers:
        if not isinstance(raw, Mapping):
            raise ValueError("each market provider must be a mapping")
        providers.append(
            {
                "name": str(raw.get("name") or "").strip().lower(),
                "api_base_url": str(raw.get("api_base_url") or "").rstrip("/"),
                "api_key_env": str(raw.get("api_key_env") or "").strip(),
            }
        )

    if tuple(item["name"] for item in providers) != _PROVIDER_ORDER:
        raise ValueError("market.providers must be ordered as cryptoapis, freecryptoapi, coinapi")
    if any(not item["api_base_url"] or not item["api_key_env"] for item in providers):
        raise ValueError("every market provider requires api_base_url and api_key_env")

    return {
        "asset_symbol": str(config.get("asset_symbol") or "TAO").upper(),
        "currencies": currencies,
        "providers": providers,
        "refresh_min_seconds": refresh_min,
        "refresh_max_seconds": refresh_max,
        "request_timeout_seconds": float(config.get("request_timeout_seconds") or 10.0),
        "cache_path": (PROJECT_ROOT / str(config.get("cache_path") or "state/tao_market_cache.json")).resolve(),
    }


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("prices"), dict):
        return None
    try:
        for currency in _SUPPORTED:
            _decimal(value["prices"].get(currency), f"cached {currency} price")
    except ValueError:
        return None
    return value


def _write_cache(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _state(payload: Mapping[str, Any], *, status: str, message: str | None) -> dict[str, Any]:
    next_refresh = payload.get("next_refresh_epoch")
    return {
        "status": status,
        "provider": str(payload.get("provider") or "provider-rotation"),
        "asset": "TAO",
        "prices": {currency: str(_mapping(payload.get("prices"))[currency]) for currency in _SUPPORTED},
        "updated_at": payload.get("updated_at"),
        "fetched_at": payload.get("fetched_at"),
        "next_refresh_at": _iso(next_refresh) if isinstance(next_refresh, (int, float)) and not isinstance(next_refresh, bool) else None,
        "message": message,
    }


def _unavailable(message: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "provider": "provider-rotation",
        "asset": "TAO",
        "prices": None,
        "updated_at": None,
        "fetched_at": None,
        "next_refresh_at": None,
        "message": message,
    }


def _parse_cryptoapis(text: str, currency: str) -> tuple[str, int | None]:
    item = _mapping(_mapping(_json(text, "Crypto APIs").get("data")).get("item"))
    rate = format(_decimal(item.get("rate"), f"Crypto APIs {currency} rate"), "f")
    timestamp = item.get("calculationTimestamp")
    if isinstance(timestamp, Decimal):
        timestamp = int(timestamp)
    return rate, timestamp if isinstance(timestamp, int) and not isinstance(timestamp, bool) else None


def _freecrypto_number(value: object) -> Decimal | None:
    if isinstance(value, Mapping):
        for key in ("converted_amount", "convertedAmount", "result", "conversion", "converted", "rate", "price", "value"):
            candidate = value.get(key)
            if candidate is None:
                continue
            if isinstance(candidate, (Mapping, list, tuple)):
                nested = _freecrypto_number(candidate)
                if nested is not None:
                    return nested
            else:
                try:
                    return _decimal(candidate, f"FreeCryptoAPI {key}")
                except ValueError:
                    pass
        for key in ("data", "item"):
            nested = _freecrypto_number(value.get(key))
            if nested is not None:
                return nested
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            nested = _freecrypto_number(item)
            if nested is not None:
                return nested
    return None


def _parse_freecrypto(text: str, currency: str) -> str:
    value = _freecrypto_number(_json(text, "FreeCryptoAPI"))
    if value is None:
        raise ValueError(f"FreeCryptoAPI response is missing the TAO/{currency} conversion")
    return format(value, "f")


def _parse_coinapi(text: str, currencies: Sequence[str]) -> tuple[dict[str, str], str | None]:
    rates = _json(text, "CoinAPI").get("rates")
    if not isinstance(rates, Sequence) or isinstance(rates, (str, bytes, bytearray)):
        raise ValueError("CoinAPI response does not contain rates")

    prices: dict[str, str] = {}
    timestamps: list[datetime] = []
    wanted = set(currencies)
    for raw in rates:
        if not isinstance(raw, Mapping):
            continue
        quote = str(raw.get("asset_id_quote") or "").upper()
        if quote not in wanted:
            continue
        prices[quote] = format(_decimal(raw.get("rate"), f"CoinAPI {quote} rate"), "f")
        raw_time = raw.get("time")
        if isinstance(raw_time, str):
            try:
                timestamps.append(datetime.fromisoformat(raw_time.replace("Z", "+00:00")))
            except ValueError:
                pass

    missing = [currency for currency in currencies if currency not in prices]
    if missing:
        raise ValueError("CoinAPI response is missing " + ", ".join(missing))
    updated = min(timestamps).astimezone(timezone.utc).isoformat() if timestamps else None
    return prices, updated


def _fetch_cryptoapis(provider: Mapping[str, str], api_key: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    prices: dict[str, str] = {}
    timestamps: list[int] = []
    with httpx.Client(
        base_url=provider["api_base_url"],
        timeout=float(settings["request_timeout_seconds"]),
        headers={"X-API-Key": api_key, "Accept": "application/json"},
    ) as client:
        for currency in settings["currencies"]:
            response = client.get(f"/market-data/exchange-rates/by-symbol/{settings['asset_symbol']}/{currency}")
            response.raise_for_status()
            prices[currency], timestamp = _parse_cryptoapis(response.text, currency)
            if timestamp is not None:
                timestamps.append(timestamp)
    now = int(time.time())
    return _payload("cryptoapis", prices, min(timestamps) if timestamps else now, now)


def _fetch_freecryptoapi(provider: Mapping[str, str], api_key: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    prices: dict[str, str] = {}
    with httpx.Client(
        base_url=provider["api_base_url"],
        timeout=float(settings["request_timeout_seconds"]),
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    ) as client:
        for currency in settings["currencies"]:
            response = client.get(
                "/getConversion",
                params={"from": settings["asset_symbol"], "to": currency, "amount": "1"},
            )
            response.raise_for_status()
            prices[currency] = _parse_freecrypto(response.text, currency)
    now = int(time.time())
    return _payload("freecryptoapi", prices, now, now)


def _fetch_coinapi(provider: Mapping[str, str], api_key: str, settings: Mapping[str, Any]) -> dict[str, Any]:
    with httpx.Client(
        base_url=provider["api_base_url"],
        timeout=float(settings["request_timeout_seconds"]),
        headers={"X-CoinAPI-Key": api_key, "Accept": "application/json"},
    ) as client:
        response = client.get(
            f"/v1/exchangerate/{settings['asset_symbol']}",
            params={"filter_asset_id": ",".join(settings["currencies"])},
        )
        response.raise_for_status()
    prices, updated_at = _parse_coinapi(response.text, settings["currencies"])
    now = int(time.time())
    return {
        "provider": "coinapi",
        "prices": prices,
        "updated_at": updated_at or _iso(now),
        "fetched_at": _iso(now),
        "fetched_epoch": now,
    }


def _payload(provider: str, prices: Mapping[str, str], updated_epoch: int, fetched_epoch: int) -> dict[str, Any]:
    return {
        "provider": provider,
        "prices": dict(prices),
        "updated_at": _iso(updated_epoch),
        "fetched_at": _iso(fetched_epoch),
        "fetched_epoch": fetched_epoch,
    }


_FETCHERS: dict[str, Callable[[Mapping[str, str], str, Mapping[str, Any]], dict[str, Any]]] = {
    "cryptoapis": _fetch_cryptoapis,
    "freecryptoapi": _fetch_freecryptoapi,
    "coinapi": _fetch_coinapi,
}


def _next_provider_index(cache: Mapping[str, Any] | None, count: int) -> int:
    if not cache or count <= 0:
        return 0
    raw = cache.get("next_provider_index")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw % count
    provider = str(cache.get("provider") or "")
    return (_PROVIDER_ORDER.index(provider) + 1) % count if provider in _PROVIDER_ORDER else 0


def _cache_is_fresh(cache: Mapping[str, Any], now: int, refresh_max: int) -> bool:
    next_refresh = cache.get("next_refresh_epoch")
    if isinstance(next_refresh, int) and not isinstance(next_refresh, bool):
        return now < next_refresh
    fetched = cache.get("fetched_epoch")
    return isinstance(fetched, int) and not isinstance(fetched, bool) and now - fetched < refresh_max


def get_tao_market_state() -> dict[str, Any]:
    settings = _settings()
    cache_path: Path = settings["cache_path"]
    cache = _read_cache(cache_path)
    now = int(time.time())

    if cache is not None and _cache_is_fresh(cache, now, settings["refresh_max_seconds"]):
        return _state(cache, status="ready", message=None)

    providers: list[Mapping[str, str]] = list(settings["providers"])
    start = _next_provider_index(cache, len(providers))
    attempted: list[str] = []

    for offset in range(len(providers)):
        index = (start + offset) % len(providers)
        provider = providers[index]
        name = provider["name"]
        api_key = os.getenv(provider["api_key_env"], "").strip()
        if not api_key:
            attempted.append(f"{name}:missing-key")
            continue
        try:
            payload = _FETCHERS[name](provider, api_key, settings)
        except (httpx.HTTPError, OSError, ValueError):
            attempted.append(f"{name}:refresh-failed")
            continue

        refresh = random.randint(settings["refresh_min_seconds"], settings["refresh_max_seconds"])
        payload["next_refresh_epoch"] = int(payload["fetched_epoch"]) + refresh
        payload["next_provider_index"] = (index + 1) % len(providers)
        _write_cache(cache_path, payload)
        return _state(payload, status="ready", message=None)

    if cache is not None:
        detail = ", ".join(attempted) if attempted else "no providers attempted"
        return _state(
            cache,
            status="stale",
            message=f"TAO market refresh failed through the configured rotation ({detail}); the displayed quote is stale.",
        )
    return _unavailable("TAO price unavailable because no configured market provider returned a usable quote.")
