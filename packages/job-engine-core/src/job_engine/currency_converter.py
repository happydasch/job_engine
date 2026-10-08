"""
Currency converter for the Job Engine.

Fetches exchange rates from a free API, caches them locally, and
auto-refreshes once per day.  Provides a thread-safe singleton.

API source: https://open.er-api.com/v6/latest/USD  (free, no key required)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_CACHE_FILE = "data/exchange_rates.json"
CACHE_MAX_AGE_SECONDS = 86_400  # 24 hours
API_URL = "https://open.er-api.com/v6/latest/USD"

# Comprehensive ISO 4217 currency list with code, name, and symbol
ALL_CURRENCIES = [
    {"code": "AED", "name": "United Arab Emirates Dirham", "symbol": "د.إ"},
    {"code": "AFN", "name": "Afghan Afghani", "symbol": "؋"},
    {"code": "ALL", "name": "Albanian Lek", "symbol": "L"},
    {"code": "AMD", "name": "Armenian Dram", "symbol": "֏"},
    {"code": "ANG", "name": "Netherlands Antillean Guilder", "symbol": "ƒ"},
    {"code": "AOA", "name": "Angolan Kwanza", "symbol": "Kz"},
    {"code": "ARS", "name": "Argentine Peso", "symbol": "$"},
    {"code": "AUD", "name": "Australian Dollar", "symbol": "A$"},
    {"code": "AWG", "name": "Aruban Florin", "symbol": "ƒ"},
    {"code": "AZN", "name": "Azerbaijani Manat", "symbol": "₼"},
    {"code": "BAM", "name": "Bosnia-Herzegovina Convertible Mark", "symbol": "KM"},
    {"code": "BBD", "name": "Barbadian Dollar", "symbol": "Bds$"},
    {"code": "BDT", "name": "Bangladeshi Taka", "symbol": "৳"},
    {"code": "BGN", "name": "Bulgarian Lev", "symbol": "лв"},
    {"code": "BHD", "name": "Bahraini Dinar", "symbol": ".د.ب"},
    {"code": "BIF", "name": "Burundian Franc", "symbol": "FBu"},
    {"code": "BMD", "name": "Bermudan Dollar", "symbol": "$"},
    {"code": "BND", "name": "Brunei Dollar", "symbol": "B$"},
    {"code": "BOB", "name": "Bolivian Boliviano", "symbol": "Bs."},
    {"code": "BRL", "name": "Brazilian Real", "symbol": "R$"},
    {"code": "BSD", "name": "Bahamian Dollar", "symbol": "B$"},
    {"code": "BTN", "name": "Bhutanese Ngultrum", "symbol": "Nu."},
    {"code": "BWP", "name": "Botswanan Pula", "symbol": "P"},
    {"code": "BYN", "name": "Belarusian Ruble", "symbol": "Br"},
    {"code": "BZD", "name": "Belize Dollar", "symbol": "BZ$"},
    {"code": "CAD", "name": "Canadian Dollar", "symbol": "C$"},
    {"code": "CDF", "name": "Congolese Franc", "symbol": "FC"},
    {"code": "CHF", "name": "Swiss Franc", "symbol": "CHF"},
    {"code": "CLP", "name": "Chilean Peso", "symbol": "$"},
    {"code": "CNY", "name": "Chinese Yuan", "symbol": "¥"},
    {"code": "COP", "name": "Colombian Peso", "symbol": "$"},
    {"code": "CRC", "name": "Costa Rican Colón", "symbol": "₡"},
    {"code": "CUP", "name": "Cuban Peso", "symbol": "$"},
    {"code": "CVE", "name": "Cape Verdean Escudo", "symbol": "$"},
    {"code": "CZK", "name": "Czech Koruna", "symbol": "Kč"},
    {"code": "DJF", "name": "Djiboutian Franc", "symbol": "Fdj"},
    {"code": "DKK", "name": "Danish Krone", "symbol": "kr"},
    {"code": "DOP", "name": "Dominican Peso", "symbol": "RD$"},
    {"code": "DZD", "name": "Algerian Dinar", "symbol": "د.ج"},
    {"code": "EGP", "name": "Egyptian Pound", "symbol": "E£"},
    {"code": "ERN", "name": "Eritrean Nakfa", "symbol": "Nkf"},
    {"code": "ETB", "name": "Ethiopian Birr", "symbol": "Br"},
    {"code": "EUR", "name": "Euro", "symbol": "€"},
    {"code": "FJD", "name": "Fijian Dollar", "symbol": "FJ$"},
    {"code": "FKP", "name": "Falkland Islands Pound", "symbol": "£"},
    {"code": "FOK", "name": "Faroese Króna", "symbol": "kr"},
    {"code": "GBP", "name": "British Pound Sterling", "symbol": "£"},
    {"code": "GEL", "name": "Georgian Lari", "symbol": "₾"},
    {"code": "GGP", "name": "Guernsey Pound", "symbol": "£"},
    {"code": "GHS", "name": "Ghanaian Cedi", "symbol": "GH₵"},
    {"code": "GIP", "name": "Gibraltar Pound", "symbol": "£"},
    {"code": "GMD", "name": "Gambian Dalasi", "symbol": "D"},
    {"code": "GNF", "name": "Guinean Franc", "symbol": "FG"},
    {"code": "GTQ", "name": "Guatemalan Quetzal", "symbol": "Q"},
    {"code": "GYD", "name": "Guyanaese Dollar", "symbol": "G$"},
    {"code": "HKD", "name": "Hong Kong Dollar", "symbol": "HK$"},
    {"code": "HNL", "name": "Honduran Lempira", "symbol": "L"},
    {"code": "HRK", "name": "Croatian Kuna", "symbol": "kn"},
    {"code": "HTG", "name": "Haitian Gourde", "symbol": "G"},
    {"code": "HUF", "name": "Hungarian Forint", "symbol": "Ft"},
    {"code": "IDR", "name": "Indonesian Rupiah", "symbol": "Rp"},
    {"code": "ILS", "name": "Israeli New Shekel", "symbol": "₪"},
    {"code": "IMP", "name": "Isle of Man Pound", "symbol": "£"},
    {"code": "INR", "name": "Indian Rupee", "symbol": "₹"},
    {"code": "IQD", "name": "Iraqi Dinar", "symbol": "ع.د"},
    {"code": "IRR", "name": "Iranian Rial", "symbol": "﷼"},
    {"code": "ISK", "name": "Icelandic Króna", "symbol": "kr"},
    {"code": "JEP", "name": "Jersey Pound", "symbol": "£"},
    {"code": "JMD", "name": "Jamaican Dollar", "symbol": "J$"},
    {"code": "JOD", "name": "Jordanian Dinar", "symbol": "د.ا"},
    {"code": "JPY", "name": "Japanese Yen", "symbol": "¥"},
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KSh"},
    {"code": "KGS", "name": "Kyrgyzstani Som", "symbol": "с"},
    {"code": "KHR", "name": "Cambodian Riel", "symbol": "៛"},
    {"code": "KID", "name": "Kiribati Dollar", "symbol": "$"},
    {"code": "KMF", "name": "Comorian Franc", "symbol": "CF"},
    {"code": "KRW", "name": "South Korean Won", "symbol": "₩"},
    {"code": "KWD", "name": "Kuwaiti Dinar", "symbol": "د.ك"},
    {"code": "KYD", "name": "Cayman Islands Dollar", "symbol": "CI$"},
    {"code": "KZT", "name": "Kazakhstani Tenge", "symbol": "₸"},
    {"code": "LAK", "name": "Laotian Kip", "symbol": "₭"},
    {"code": "LBP", "name": "Lebanese Pound", "symbol": "ل.ل"},
    {"code": "LKR", "name": "Sri Lankan Rupee", "symbol": "Rs"},
    {"code": "LRD", "name": "Liberian Dollar", "symbol": "L$"},
    {"code": "LSL", "name": "Lesotho Loti", "symbol": "L"},
    {"code": "LYD", "name": "Libyan Dinar", "symbol": "ل.د"},
    {"code": "MAD", "name": "Moroccan Dirham", "symbol": "د.م."},
    {"code": "MDL", "name": "Moldovan Leu", "symbol": "L"},
    {"code": "MGA", "name": "Malagasy Ariary", "symbol": "Ar"},
    {"code": "MKD", "name": "Macedonian Denar", "symbol": "ден"},
    {"code": "MMK", "name": "Myanmar Kyat", "symbol": "Ks"},
    {"code": "MNT", "name": "Mongolian Tugrik", "symbol": "₮"},
    {"code": "MOP", "name": "Macanese Pataca", "symbol": "MOP$"},
    {"code": "MRU", "name": "Mauritanian Ouguiya", "symbol": "UM"},
    {"code": "MUR", "name": "Mauritian Rupee", "symbol": "₨"},
    {"code": "MVR", "name": "Maldivian Rufiyaa", "symbol": "Rf"},
    {"code": "MWK", "name": "Malawian Kwacha", "symbol": "MK"},
    {"code": "MXN", "name": "Mexican Peso", "symbol": "Mex$"},
    {"code": "MYR", "name": "Malaysian Ringgit", "symbol": "RM"},
    {"code": "MZN", "name": "Mozambican Metical", "symbol": "MT"},
    {"code": "NAD", "name": "Namibian Dollar", "symbol": "N$"},
    {"code": "NGN", "name": "Nigerian Naira", "symbol": "₦"},
    {"code": "NIO", "name": "Nicaraguan Córdoba", "symbol": "C$"},
    {"code": "NOK", "name": "Norwegian Krone", "symbol": "kr"},
    {"code": "NPR", "name": "Nepalese Rupee", "symbol": "₨"},
    {"code": "NZD", "name": "New Zealand Dollar", "symbol": "NZ$"},
    {"code": "OMR", "name": "Omani Rial", "symbol": "ر.ع."},
    {"code": "PAB", "name": "Panamanian Balboa", "symbol": "B/."},
    {"code": "PEN", "name": "Peruvian Sol", "symbol": "S/."},
    {"code": "PGK", "name": "Papua New Guinean Kina", "symbol": "K"},
    {"code": "PHP", "name": "Philippine Peso", "symbol": "₱"},
    {"code": "PKR", "name": "Pakistani Rupee", "symbol": "₨"},
    {"code": "PLN", "name": "Polish Zloty", "symbol": "zł"},
    {"code": "PYG", "name": "Paraguayan Guarani", "symbol": "₲"},
    {"code": "QAR", "name": "Qatari Riyal", "symbol": "ر.ق"},
    {"code": "RON", "name": "Romanian Leu", "symbol": "lei"},
    {"code": "RSD", "name": "Serbian Dinar", "symbol": "дин"},
    {"code": "RUB", "name": "Russian Ruble", "symbol": "₽"},
    {"code": "RWF", "name": "Rwandan Franc", "symbol": "FRw"},
    {"code": "SAR", "name": "Saudi Riyal", "symbol": "﷼"},
    {"code": "SBD", "name": "Solomon Islands Dollar", "symbol": "SI$"},
    {"code": "SCR", "name": "Seychellois Rupee", "symbol": "₨"},
    {"code": "SDG", "name": "Sudanese Pound", "symbol": "ج.س."},
    {"code": "SEK", "name": "Swedish Krona", "symbol": "kr"},
    {"code": "SGD", "name": "Singapore Dollar", "symbol": "S$"},
    {"code": "SHP", "name": "Saint Helena Pound", "symbol": "£"},
    {"code": "SLL", "name": "Sierra Leonean Leone", "symbol": "Le"},
    {"code": "SOS", "name": "Somali Shilling", "symbol": "Sh.So."},
    {"code": "SRD", "name": "Surinamese Dollar", "symbol": "$"},
    {"code": "SSP", "name": "South Sudanese Pound", "symbol": "£"},
    {"code": "STN", "name": "São Tomé and Príncipe Dobra", "symbol": "Db"},
    {"code": "SYP", "name": "Syrian Pound", "symbol": "£S"},
    {"code": "SZL", "name": "Eswatini Lilangeni", "symbol": "E"},
    {"code": "THB", "name": "Thai Baht", "symbol": "฿"},
    {"code": "TJS", "name": "Tajikistani Somoni", "symbol": "SM"},
    {"code": "TMT", "name": "Turkmenistani Manat", "symbol": "T"},
    {"code": "TND", "name": "Tunisian Dinar", "symbol": "د.ت"},
    {"code": "TOP", "name": "Tongan Paʻanga", "symbol": "T$"},
    {"code": "TRY", "name": "Turkish Lira", "symbol": "₺"},
    {"code": "TTD", "name": "Trinidad and Tobago Dollar", "symbol": "TT$"},
    {"code": "TVD", "name": "Tuvaluan Dollar", "symbol": "$"},
    {"code": "TWD", "name": "New Taiwan Dollar", "symbol": "NT$"},
    {"code": "TZS", "name": "Tanzanian Shilling", "symbol": "TSh"},
    {"code": "UAH", "name": "Ukrainian Hryvnia", "symbol": "₴"},
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "USh"},
    {"code": "USD", "name": "US Dollar", "symbol": "$"},
    {"code": "UYU", "name": "Uruguayan Peso", "symbol": "$U"},
    {"code": "UZS", "name": "Uzbekistani Som", "symbol": "so'm"},
    {"code": "VES", "name": "Venezuelan Bolívar", "symbol": "Bs.S"},
    {"code": "VND", "name": "Vietnamese Dong", "symbol": "₫"},
    {"code": "VUV", "name": "Vanuatu Vatu", "symbol": "VT"},
    {"code": "WST", "name": "Samoan Tala", "symbol": "WS$"},
    {"code": "XAF", "name": "Central African CFA Franc", "symbol": "FCFA"},
    {"code": "XCD", "name": "East Caribbean Dollar", "symbol": "EC$"},
    {"code": "XDR", "name": "Special Drawing Rights", "symbol": "SDR"},
    {"code": "XOF", "name": "West African CFA Franc", "symbol": "F CFA"},
    {"code": "XPF", "name": "CFP Franc", "symbol": "₣"},
    {"code": "YER", "name": "Yemeni Rial", "symbol": "﷼"},
    {"code": "ZAR", "name": "South African Rand", "symbol": "R"},
    {"code": "ZMW", "name": "Zambian Kwacha", "symbol": "ZK"},
    {"code": "ZWL", "name": "Zimbabwean Dollar", "symbol": "Z$"},
]

# ── Currency list helper ────────────────────────────────────────────────────


def get_all_currencies() -> list[dict[str, str]]:
    """Return the comprehensive ISO 4217 currency list sorted by code."""
    return list(ALL_CURRENCIES)


def get_currency_by_code(code: str) -> dict[str, str] | None:
    """Look up a currency by its ISO code (case-insensitive)."""
    upper = code.upper().strip()
    for c in ALL_CURRENCIES:
        if c["code"] == upper:
            return dict(c)
    return None


SUPPORTED_CURRENCIES = sorted(
    {
        "USD",
        "EUR",
        "GBP",
        "PLN",
        "CHF",
        "CZK",
        "JPY",
        "CNY",
        "CAD",
        "AUD",
        "NZD",
        "SEK",
        "NOK",
        "DKK",
        "HUF",
        "RON",
        "BGN",
        "ISK",
        "INR",
        "BRL",
        "MXN",
        "KRW",
        "SGD",
        "HKD",
        "ILS",
        "TRY",
        "ZAR",
        "MYR",
        "THB",
        "PHP",
        "IDR",
        "VND",
    }
)

# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class ExchangeRates:
    """Cached exchange rates with metadata."""

    base: str  # always USD
    rates: dict[str, float]
    fetched_at: float  # unix timestamp
    source: str = "open.er-api.com"


# ── Singleton ─────────────────────────────────────────────────────────────────

_rates_instance: ExchangeRates | None = None
_cache_path: Path | None = None


def _resolve_cache_path() -> Path:
    """Resolve the exchange rates cache file path relative to project root."""
    global _cache_path
    if _cache_path is not None:
        return _cache_path

    # Try to find project root (same logic as config.py)
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        root = Path(env_root)
    else:
        # Walk up from this file
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".project-root").exists():
                root = parent
                break
        else:
            root = Path.cwd()
    _cache_path = root / DEFAULT_CACHE_FILE
    return _cache_path


# ── Cache I/O ─────────────────────────────────────────────────────────────────


def _load_cache() -> dict[str, Any] | None:
    """Load cached exchange rates from disk. Returns None if missing or corrupt."""
    path = _resolve_cache_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rates" in data and "fetched_at" in data:
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt exchange rate cache at %s: %s", path, exc)
    return None


def _save_cache(rates: dict[str, Any]) -> None:
    """Persist exchange rates to the cache file."""
    path = _resolve_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(rates, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("Failed to write exchange rate cache: %s", exc)


def _is_cache_stale(data: dict[str, Any]) -> bool:
    """Check if the cached rates are older than CACHE_MAX_AGE_SECONDS."""
    fetched_at = data.get("fetched_at", 0)
    return (time.time() - fetched_at) > CACHE_MAX_AGE_SECONDS


# ── API Fetch ─────────────────────────────────────────────────────────────────


def _fetch_rates_from_api() -> dict[str, Any] | None:
    """Fetch fresh exchange rates from the free API.

    Returns a dict with ``base``, ``rates``, ``fetched_at``, or None on failure.
    """
    try:
        resp = httpx.get(API_URL, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch exchange rates: %s", exc)
        return None

    if payload.get("result") != "success":
        logger.warning("Exchange rate API returned non-success: %s", payload.get("result"))
        return None

    rates = payload.get("rates")
    if not isinstance(rates, dict):
        logger.warning("Exchange rate API returned no rates")
        return None

    # Normalise: ensure USD is 1.0 (the API base is always USD)
    rates["USD"] = 1.0

    return {
        "base": "USD",
        "rates": rates,
        "fetched_at": time.time(),
        "source": payload.get("provider", "open.er-api.com"),
    }


# ── Public API ────────────────────────────────────────────────────────────────


def get_rates(*, force_refresh: bool = False) -> ExchangeRates | None:
    """Return the current exchange rates, refreshing from API if stale.

    Args:
        force_refresh: If True, always fetch fresh rates from the API.

    Returns:
        An ``ExchangeRates`` instance, or ``None`` if no rates are available
        (neither cached nor fetchable).
    """
    global _rates_instance

    # Try in-memory cache first
    if _rates_instance is not None and not force_refresh:
        # Check freshness of in-memory cache
        if not _is_cache_stale({"fetched_at": _rates_instance.fetched_at}):
            return _rates_instance

    # Try disk cache
    cached = _load_cache()
    if cached is not None and not force_refresh and not _is_cache_stale(cached):
        _rates_instance = ExchangeRates(
            base=cached["base"],
            rates=cached["rates"],
            fetched_at=cached["fetched_at"],
            source=cached.get("source", "cache"),
        )
        return _rates_instance

    # Fetch from API
    fresh = _fetch_rates_from_api()
    if fresh is not None:
        _save_cache(fresh)
        _rates_instance = ExchangeRates(
            base=fresh["base"],
            rates=fresh["rates"],
            fetched_at=fresh["fetched_at"],
            source=fresh.get("source", "open.er-api.com"),
        )
        return _rates_instance

    # Fall back to stale disk cache if API fails
    if cached is not None:
        logger.warning("Using stale exchange rate cache (API fetch failed)")
        _rates_instance = ExchangeRates(
            base=cached["base"],
            rates=cached["rates"],
            fetched_at=cached["fetched_at"],
            source=cached.get("source", "cache (stale)"),
        )
        return _rates_instance

    return None


def get_rate(from_currency: str, to_currency: str) -> float | None:
    """Get the exchange rate from ``from_currency`` to ``to_currency``.

    Example: ``get_rate("USD", "PLN")`` → 4.3

    Returns ``None`` if rates are unavailable or the currency is unsupported.
    """
    from_upper = from_currency.upper().strip()
    to_upper = to_currency.upper().strip()

    if from_upper == to_upper:
        return 1.0

    rates = get_rates()
    if rates is None:
        return None

    from_rate = rates.rates.get(from_upper)
    to_rate = rates.rates.get(to_upper)

    if from_rate is None or to_rate is None:
        logger.debug("Unsupported currency: %s → %s", from_currency, to_currency)
        return None

    # All rates are relative to USD, so: rate = to_rate / from_rate
    return to_rate / from_rate


def convert(amount: float, from_currency: str, to_currency: str) -> float | None:
    """Convert ``amount`` from ``from_currency`` to ``to_currency``.

    Returns the converted amount, or ``None`` if conversion is not possible.
    """
    rate = get_rate(from_currency, to_currency)
    if rate is None:
        return None
    return round(amount * rate, 2)


def format_converted(
    amount: float | None,
    from_currency: str,
    to_currency: str,
    *,
    decimals: int = 0,
) -> str:
    """Format an amount converted to the target currency, with original in parens.

    Returns something like ``"12,500 PLN (≈3,125 USD)"``.

    If conversion fails, returns the original amount in the original currency.
    """
    if amount is None:
        return "N/A"

    from_upper = from_currency.upper().strip()
    to_upper = to_currency.upper().strip()

    if from_upper == to_upper:
        return f"{amount:,.{decimals}f} {from_upper}"

    converted_val = convert(amount, from_upper, to_upper)
    if converted_val is not None:
        return f"{amount:,.{decimals}f} {from_upper} (≈{converted_val:,.{decimals}f} {to_upper})"
    return f"{amount:,.{decimals}f} {from_upper}"


def convert_amount(
    amount: float | None,
    from_currency: str,
    to_currency: str,
    *,
    decimals: int = 0,
) -> str:
    """Convert an amount and format it in the target currency only.

    Returns something like ``"3,125 USD"``.

    If conversion fails, returns the original amount in the original currency.
    """
    if amount is None:
        return "N/A"

    from_upper = from_currency.upper().strip()
    to_upper = to_currency.upper().strip()

    if from_upper == to_upper:
        return f"{amount:,.{decimals}f} {to_upper}"

    converted_val = convert(amount, from_upper, to_upper)
    if converted_val is not None:
        return f"{converted_val:,.{decimals}f} {to_upper}"
    return f"{amount:,.{decimals}f} {from_upper}"


def clear_cache() -> None:
    """Clear the in-memory and disk caches. Useful for testing."""
    global _rates_instance
    _rates_instance = None
    path = _resolve_cache_path()
    if path.exists():
        path.unlink(missing_ok=True)


def refresh_rates() -> bool:
    """Force-refresh exchange rates from the API. Returns True on success."""
    result = get_rates(force_refresh=True)
    return result is not None
