"""Travelpayouts / Aviasales. Gratis, con token de afiliado.

Dos límites de esta API que determinan cómo se usa aquí:

1. Devuelve precios de CACHÉ, no consultas en vivo. Sirve para enterarse de que
   una tarifa baja existe; el precio se confirma en el buscador al abrir el enlace.
2. No dice cuánto dura cada escala ni si la tarifa incluye maleta. Como el límite
   de 6 horas de escala no se puede verificar, de esta fuente solo se toman
   VUELOS DIRECTOS, que además son la prioridad. La maleta se estima y se avisa.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import equipaje  # noqa: E402

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

ENDPOINT = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _duracion(minutos):
    if not minutos:
        return ""
    return f"PT{int(minutos) // 60}H{int(minutos) % 60}M"


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    token = provider_cfg.get("token")
    if not token:
        raise RuntimeError(
            "Falta el token de Travelpayouts (variable TRAVELPAYOUTS_TOKEN)."
        )

    params = {
        "origin": search_cfg["origin"],
        "destination": search_cfg["destination"],
        "departure_at": search_cfg["departure_date"],
        "return_at": search_cfg["return_date"],
        "currency": search_cfg.get("currency", "MXN").lower(),
        "sorting": "price",
        "direct": "true",  # ver nota 2 arriba
        "unique": "false",
        "limit": provider_cfg.get("limit", 30),
        "one_way": "false",
        "token": token,
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=45, context=_CTX))
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read()[:200]
        if exc.code in (401, 403):
            raise RuntimeError(
                f"Travelpayouts rechazó el token (HTTP {exc.code}). Revisa el secret."
            ) from exc
        raise RuntimeError(f"Travelpayouts HTTP {exc.code}: {cuerpo!r}") from exc

    if not payload.get("success", True):
        raise RuntimeError(f"Travelpayouts: {str(payload.get('error'))[:150]}")

    quiere_maleta = search_cfg.get("checked_bag", True)
    offers = []
    for d in payload.get("data", []):
        if d.get("transfers") or d.get("return_transfers"):
            continue  # solo directos: no se puede verificar la escala
        tarifa = float(d.get("price") or 0)
        if not tarifa:
            continue

        nota = (
            "Precio de CACHÉ de Aviasales: confirma el monto al abrir el enlace, "
            "puede haber cambiado."
        )
        precio = tarifa
        if quiere_maleta:
            estimado, explicacion = equipaje.estimar(d.get("airline", ""))
            if estimado is None:
                # Sin forma de estimar la maleta, el total no es comparable.
                continue
            precio = tarifa + estimado
            nota = f"Tarifa {tarifa:,.0f} de caché. {explicacion} {nota}"

        enlace = d.get("link") or ""
        if enlace.startswith("/"):
            enlace = "https://www.aviasales.com" + enlace

        offers.append(
            {
                "price": precio,
                "currency": search_cfg.get("currency", "MXN").upper(),
                "airline": d.get("airline", ""),
                "legs": [
                    {
                        "from": d.get("origin_airport", search_cfg["origin"]),
                        "to": d.get("destination_airport", search_cfg["destination"]),
                        "depart": d.get("departure_at", ""),
                        "arrive": "",
                        "stops": 0,
                        "airline": d.get("airline", ""),
                        "flight": str(d.get("flight_number", "")),
                        "duration": _duracion(d.get("duration_to")),
                    },
                    {
                        "from": d.get("destination_airport", search_cfg["destination"]),
                        "to": d.get("origin_airport", search_cfg["origin"]),
                        "depart": d.get("return_at", ""),
                        "arrive": "",
                        "stops": 0,
                        "airline": d.get("airline", ""),
                        "flight": "",
                        "duration": _duracion(d.get("duration_back")),
                    },
                ],
                "seats_left": None,
                "checked_bag": quiere_maleta,
                "stops": 0,
                "layovers": [],
                "separate_tickets": False,
                "source": "Aviasales (caché)",
                "link": enlace,
                "links": [("Ver en Aviasales", enlace)] if enlace else None,
                "note": nota,
                "cached": True,
            }
        )

    offers.sort(key=lambda o: o["price"])
    return offers
