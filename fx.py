"""Tipo de cambio del Banco Central Europeo (frankfurter.dev). Gratis, sin llave."""
import json
import ssl
import time
import urllib.request

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

_cache = {"rates": None, "at": 0}


def rates(base="EUR"):
    if _cache["rates"] and time.time() - _cache["at"] < 6 * 3600:
        return _cache["rates"]
    req = urllib.request.Request(
        f"https://api.frankfurter.dev/v1/latest?base={base}",
        headers={"user-agent": "Mozilla/5.0"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=30, context=_CTX))
    _cache["rates"], _cache["at"] = data["rates"] | {base: 1.0}, time.time()
    return _cache["rates"]


def to_mxn(amount, currency):
    currency = currency.upper()
    if currency == "MXN":
        return float(amount)
    r = rates("EUR")
    return float(amount) * r["MXN"] / r[currency]
