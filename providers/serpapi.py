"""SerpAPI (motor google_flights). Capa gratuita: 100 búsquedas al mes.

Con ese presupuesto no sirve para vigilar, sino para **verificar**: una consulta
cada 8 horas (3 al día, ~90 al mes) confirma de forma independiente que el precio
que leo de Google es real y no un artefacto de cómo interpreto su página.

Ventaja propia: devuelve la duración de cada escala ya calculada, así que el
límite de horas se puede verificar sin estimar nada.
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


def _max_stops(search_cfg, provider_cfg=None):
    if provider_cfg and provider_cfg.get("max_stops") is not None:
        return provider_cfg["max_stops"]
    if search_cfg.get("nonstop_only") is True and search_cfg.get("max_stops") is None:
        return 0
    return search_cfg.get("max_stops", 0)


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    key = provider_cfg.get("api_key")
    if not key:
        raise RuntimeError("Falta la llave de SerpAPI (variable SERAPI_KEY).")

    tope = _max_stops(search_cfg, provider_cfg)
    params = {
        "engine": "google_flights",
        "departure_id": search_cfg["origin"],
        "arrival_id": search_cfg["destination"],
        "outbound_date": search_cfg["departure_date"],
        "return_date": search_cfg["return_date"],
        "type": 1,  # viaje redondo
        "adults": search_cfg.get("adults", 1),
        "currency": search_cfg.get("currency", "MXN"),
        "hl": "es",
        "gl": "mx",
        "api_key": key,
    }
    if tope == 0:
        params["stops"] = 1  # en SerpAPI, 1 significa "solo sin escalas"

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    try:
        payload = json.load(urllib.request.urlopen(url, timeout=60, context=_CTX))
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read()[:200]
        if exc.code == 401:
            raise RuntimeError("SerpAPI rechazó la llave. Revisa el secret.") from exc
        raise RuntimeError(f"SerpAPI HTTP {exc.code}: {cuerpo!r}") from exc

    if payload.get("error"):
        error = str(payload["error"])
        if "run out" in error.lower() or "exceed" in error.lower():
            raise RuntimeError(
                "Se agotaron las 100 búsquedas gratis del mes en SerpAPI. "
                "Se retoma al reiniciar el ciclo."
            )
        raise RuntimeError(f"SerpAPI: {error[:150]}")

    horas_max = search_cfg.get("max_layover_hours")
    quiere_maleta = search_cfg.get("checked_bag", True)
    enlace = payload.get("search_metadata", {}).get("google_flights_url", "")

    offers = []
    for grupo in ("best_flights", "other_flights"):
        for item in payload.get(grupo, []) or []:
            tramos = item.get("flights") or []
            if not tramos:
                continue
            if tope is not None and len(tramos) - 1 > tope:
                continue

            # SerpAPI ya entrega la duración de cada escala: no hay que estimarla.
            paradas = [
                (l.get("id") or l.get("name", ""), int(l.get("duration") or 0))
                for l in (item.get("layovers") or [])
            ]
            if horas_max and any(m > horas_max * 60 for _, m in paradas):
                continue

            tarifa = float(item.get("price") or 0)
            if not tarifa:
                continue

            nota = "Precio verificado con SerpAPI (lectura independiente de Google)."
            precio, con_maleta = tarifa, quiere_maleta
            if quiere_maleta:
                estimado, explicacion = equipaje.estimar(
                    tramos[0].get("airline", "")
                )
                if estimado is None:
                    con_maleta = False
                    nota = (
                        f"SerpAPI no informa el equipaje y no tengo tarifa registrada "
                        f"para {tramos[0].get('airline', '?')}: súmale la maleta. {nota}"
                    )
                else:
                    precio = tarifa + estimado
                    nota = f"Tarifa {tarifa:,.0f}. {explicacion} {nota}"

            offers.append(
                {
                    "price": precio,
                    "currency": search_cfg.get("currency", "MXN"),
                    "airline": tramos[0].get("airline", ""),
                    "legs": [
                        {
                            "from": t["departure_airport"]["id"],
                            "to": t["arrival_airport"]["id"],
                            "depart": t["departure_airport"]["time"],
                            "arrive": t["arrival_airport"]["time"],
                            "stops": 0,
                            "airline": t.get("airline", ""),
                            "flight": t.get("flight_number", ""),
                            "duration": f"PT{int(t.get('duration') or 0) // 60}H"
                            f"{int(t.get('duration') or 0) % 60}M",
                        }
                        for t in tramos
                    ],
                    "seats_left": None,
                    "checked_bag": con_maleta,
                    "stops": len(tramos) - 1,
                    "layovers": paradas,
                    "separate_tickets": False,
                    "source": "SerpAPI (verificación)",
                    "link": enlace,
                    "links": [("Ver en Google Flights", enlace)] if enlace else None,
                    "note": nota,
                }
            )

    offers.sort(key=lambda o: o["price"])
    return offers
