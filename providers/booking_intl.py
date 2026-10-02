"""Booking.com comprando desde otro país (arbitraje de punto de venta).

El mismo vuelo puede costar distinto según el mercado desde el que se compra.
Se consulta Booking como si fueras de España, EE.UU. o Reino Unido, se convierte
a pesos al tipo de cambio del BCE y solo se reporta si el ahorro es grande de
verdad, porque tu tarjeta cobra comisión por conversión de divisa.

Mismo patrón que kiwi_intl, con una diferencia: Booking responde 429 cuando se le
pregunta seguido, así que entre mercado y mercado se hace una pausa.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fx  # noqa: E402

from . import booking  # noqa: E402

MERCADOS = [
    {"currency": "EUR", "locale": "es-es", "label": "España"},
    {"currency": "USD", "locale": "en-us", "label": "EE.UU."},
    {"currency": "GBP", "locale": "en-gb", "label": "Reino Unido"},
]


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    minimo_pct = provider_cfg.get("min_saving_pct", 3)
    pausa = provider_cfg.get("pausa_segundos", 5)

    # Referencia: lo que cuesta comprando desde México.
    try:
        local = booking.search(search_cfg, {})
        local_mejor = min(o["price"] for o in local) if local else None
    except Exception:
        local_mejor = None

    offers = []
    for m in provider_cfg.get("markets", MERCADOS):
        time.sleep(pausa)
        try:
            got = booking.search(
                search_cfg, {"currency": m["currency"], "locale": m["locale"]}
            )
        except Exception:
            continue  # un mercado caído no debe tumbar los demás

        for o in got:
            try:
                mxn = fx.to_mxn(o["price"], o["currency"])
            except Exception:
                continue
            # Solo vale la pena si el ahorro cubre de sobra la comisión por divisa.
            if local_mejor and mxn > local_mejor * (1 - minimo_pct / 100):
                continue
            o = dict(o)
            o["original_price"], o["original_currency"] = o["price"], o["currency"]
            o["price"], o["currency"] = mxn, "MXN"
            o["source"] = f"Booking {m['label']}"
            o["note"] = (
                f"Precio original {o['original_price']:,.0f} {o['original_currency']} "
                f"comprando desde {m['label']}"
                + (
                    f", {mxn / local_mejor * 100 - 100:+.1f}% contra comprar desde México"
                    if local_mejor
                    else ""
                )
                + ". Tu banco cobrará comisión por conversión de divisa (1-3%), "
                "y pagar en moneda extranjera puede complicar los meses sin intereses."
            )
            offers.append(o)

    offers.sort(key=lambda o: o["price"])
    return offers
