"""Hack: comprar desde otro país (arbitraje de punto de venta).

El mismo vuelo a veces cuesta distinto según el mercado desde el que compras.
Se consulta Kiwi como si fueras de España, EE.UU. o Reino Unido, se convierte a
pesos al tipo de cambio del BCE y solo se reporta si el ahorro es grande, porque
tu tarjeta cobrará comisión por conversión de divisa.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fx  # noqa: E402

from . import kiwi  # noqa: E402

MARKETS = [
    {"market": "es", "locale": "es", "currency": "EUR", "label": "España"},
    {"market": "us", "locale": "en", "currency": "USD", "label": "EE.UU."},
    {"market": "gb", "locale": "en", "currency": "GBP", "label": "Reino Unido"},
]


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    min_saving_pct = provider_cfg.get("min_saving_pct", 3)

    try:
        local = kiwi.search(search_cfg, {"limit": 10})
        local_best = min(o["price"] for o in local) if local else None
    except Exception:
        local_best = None

    offers = []
    for m in provider_cfg.get("markets", MARKETS):
        try:
            got = kiwi.search(search_cfg, {"limit": 10, **m})
        except Exception:
            continue
        for o in got:
            try:
                mxn = fx.to_mxn(o["price"], o["currency"])
            except Exception:
                continue
            # Solo vale la pena si el ahorro cubre de sobra la comisión por divisa.
            if local_best and mxn > local_best * (1 - min_saving_pct / 100):
                continue
            o = dict(o)
            o["original_price"], o["original_currency"] = o["price"], o["currency"]
            o["price"], o["currency"] = mxn, "MXN"
            o["source"] = f"Kiwi {m['label']}"
            o["note"] = (
                f"Precio original {o['original_price']:,.0f} {o['original_currency']} "
                f"comprando desde {m['label']}. Tu banco cobrará comisión por "
                "conversión de divisa (normalmente 1-3%)."
            )
            offers.append(o)

    offers.sort(key=lambda o: o["price"])
    return offers
