"""Proveedor Booking.com Flights. Gratis, sin cuenta.

Además de sus tarifas, aporta algo que ninguna otra fuente da: el **precio de
agregar la maleta documentada**. Eso permite comparar de verdad dos caminos que
suelen confundirse:

  A) tarifa que ya incluye maleta
  B) tarifa básica barata + pagar la maleta aparte

A veces gana B, a veces A. Sin el costo de la maleta, comparar es imposible.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import equipaje  # noqa: E402
import escalas  # noqa: E402

ENDPOINT = "https://flights.booking.com/api/flights/"


def pedir(url, intentos=3, espera=6):
    """Booking devuelve 429 si se le pregunta seguido. Se reintenta con pausa."""
    import time

    ultimo = None
    for intento in range(intentos):
        req = urllib.request.Request(
            url, headers={"user-agent": "Mozilla/5.0", "accept": "application/json"}
        )
        try:
            return json.load(urllib.request.urlopen(req, timeout=60, context=_CTX))
        except urllib.error.HTTPError as exc:
            ultimo = exc
            if exc.code != 429:
                raise
            if intento < intentos - 1:
                time.sleep(espera * (intento + 1))
    raise RuntimeError(f"Booking limitó el ritmo (429) tras {intentos} intentos") from ultimo


def _money(block):
    if not block:
        return None
    return block.get("units", 0) + block.get("nanos", 0) / 1e9


def _legs(offer):
    out = []
    for seg in offer.get("segments", []):
        legs = seg.get("legs", [])
        if not legs:
            continue
        first, last = legs[0], legs[-1]
        carrier = (first.get("carriersData") or [{}])[0].get("name", "")
        out.append(
            {
                "from": seg["departureAirport"]["code"],
                "to": seg["arrivalAirport"]["code"],
                "depart": seg["departureTime"],
                "arrive": seg["arrivalTime"],
                "stops": len(legs) - 1,
                "airline": carrier,
                "flight": str((first.get("flightInfo") or {}).get("flightNumber", "")),
                "duration": f"PT{seg.get('totalTime', 0) // 3600}H"
                f"{seg.get('totalTime', 0) % 3600 // 60}M",
            }
        )
    return out


def _tiene_maleta(offer):
    tipos = {
        b.get("luggageType")
        for seg in offer.get("includedProducts", {}).get("segments", [[]])
        for b in seg
    }
    return "CHECKED_IN" in tipos


def _precio_maleta(offer):
    for extra in offer.get("extraProducts") or []:
        if extra.get("type") == "checkedInBaggage":
            return _money(extra.get("priceBreakdown", {}).get("total"))
    return None


def search(search_cfg, provider_cfg=None):
    params = {
        "type": "ROUNDTRIP",
        "adults": search_cfg.get("adults", 1),
        "cabinClass": (search_cfg.get("travel_class") or "economy").upper(),
        "from": f"{search_cfg['origin']}.AIRPORT",
        "to": f"{search_cfg['destination']}.AIRPORT",
        "depart": search_cfg["departure_date"],
        "return": search_cfg["return_date"],
        "sort": "CHEAPEST",
        "selected_currency": (provider_cfg or {}).get(
            "currency", search_cfg.get("currency", "MXN")
        ),
        "locale": (provider_cfg or {}).get("locale", "es"),
    }
    tope = (
        0
        if (search_cfg.get("nonstop_only") is True and search_cfg.get("max_stops") is None)
        else search_cfg.get("max_stops", 0)
    )
    if tope == 0:
        params["stops"] = "none"

    url_consulta = ENDPOINT + "?" + urllib.parse.urlencode(params)
    payload = pedir(url_consulta)

    quiere_maleta = search_cfg.get("checked_bag", True)
    liga_params = {
        "type": "ROUNDTRIP",
        "adults": search_cfg.get("adults", 1),
        "cabinClass": (search_cfg.get("travel_class") or "economy").upper(),
        "from": f"{search_cfg['origin']}.AIRPORT",
        "to": f"{search_cfg['destination']}.AIRPORT",
        "depart": search_cfg["departure_date"],
        "return": search_cfg["return_date"],
        "sort": "CHEAPEST",
        "selected_currency": search_cfg.get("currency", "MXN"),
    }
    if tope == 0:
        liga_params["stops"] = "none"
    link = (
        f"https://flights.booking.com/flights/{search_cfg['origin']}.AIRPORT-"
        f"{search_cfg['destination']}.AIRPORT/?" + urllib.parse.urlencode(liga_params)
    )

    offers = []
    for o in payload.get("flightOffers", []):
        legs = _legs(o)
        if not legs:
            continue
        if tope is not None and any(l["stops"] > tope for l in legs):
            continue
        paradas = []
        for seg in o.get("segments", []):
            tramos = [
                {
                    "to": l["arrivalAirport"]["code"],
                    "arrive": l["arrivalTime"],
                    "depart": l["departureTime"],
                }
                for l in seg.get("legs", [])
            ]
            paradas += escalas.de_tramos(tramos)
        if not escalas.cumple(paradas, search_cfg.get("max_layover_hours")):
            continue
        tarifa = _money(o.get("priceBreakdown", {}).get("total"))
        if tarifa is None:
            continue
        currency = o["priceBreakdown"]["total"].get("currencyCode", "MXN")

        con_maleta = _tiene_maleta(o)
        nota = "Precio total viaje redondo"
        precio = tarifa

        if quiere_maleta and not con_maleta:
            costo = _precio_maleta(o)
            if costo is not None:
                precio = tarifa + costo
                nota = (
                    f"TARIFA BÁSICA {tarifa:,.0f} + MALETA {costo:,.0f} = "
                    f"{precio:,.0f} {currency}. La maleta SE COMPRA POR SEPARADO al "
                    "reservar; confirma el peso permitido."
                )
            else:
                # El vendedor no cotiza la maleta: la estimamos para poder comparar
                # peras con peras, avisando que es estimación y compra aparte.
                estimado, explicacion = equipaje.estimar(legs[0]["airline"])
                if estimado is None:
                    continue
                precio = tarifa + estimado
                nota = f"Tarifa básica {tarifa:,.0f} {currency}. {explicacion}"
        elif con_maleta:
            nota = "Precio total viaje redondo, maleta documentada incluida en la tarifa"

        offers.append(
            {
                "price": float(precio),
                "currency": currency,
                "airline": legs[0]["airline"],
                "legs": legs,
                "seats_left": None,
                "checked_bag": True if (con_maleta or quiere_maleta) else False,
                "stops": max((l["stops"] for l in legs), default=0),
                "layovers": paradas,
                "separate_tickets": False,
                "source": "Booking.com",
                "link": link,
                "links": [("Ver en Booking.com", link)],
                "note": nota,
                "bag_included_in_fare": con_maleta,
            }
        )

    offers.sort(key=lambda o: o["price"])
    return offers
