"""Proveedor Booking.com Flights. Gratis, sin cuenta.

Además de sus tarifas, aporta algo que ninguna otra fuente da: el **precio de
agregar la maleta documentada**. Eso permite comparar de verdad dos caminos que
suelen confundirse:

  A) tarifa que ya incluye maleta
  B) tarifa básica barata + pagar la maleta aparte

A veces gana B, a veces A. Sin el costo de la maleta, comparar es imposible.
"""
import json
import ssl
import urllib.parse
import urllib.request

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

ENDPOINT = "https://flights.booking.com/api/flights/"


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
        "locale": "es",
        "selected_currency": search_cfg.get("currency", "MXN"),
    }
    if search_cfg.get("nonstop_only", True):
        params["stops"] = "none"

    req = urllib.request.Request(
        ENDPOINT + "?" + urllib.parse.urlencode(params),
        headers={"user-agent": "Mozilla/5.0", "accept": "application/json"},
    )
    payload = json.load(urllib.request.urlopen(req, timeout=60, context=_CTX))

    quiere_maleta = search_cfg.get("checked_bag", True)
    link = (
        "https://flights.booking.com/flights/"
        f"{search_cfg['origin']}.AIRPORT-{search_cfg['destination']}.AIRPORT/"
        f"?type=ROUNDTRIP&depart={search_cfg['departure_date']}"
        f"&return={search_cfg['return_date']}&stops=none"
    )

    offers = []
    for o in payload.get("flightOffers", []):
        legs = _legs(o)
        if not legs:
            continue
        if search_cfg.get("nonstop_only", True) and any(l["stops"] for l in legs):
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
            if costo is None:
                continue  # sin maleta y sin forma de cotizarla: no sirve
            precio = tarifa + costo
            nota = (
                f"TARIFA BÁSICA {tarifa:,.0f} + MALETA {costo:,.0f} = {precio:,.0f} {currency}. "
                "La maleta se paga aparte al reservar; confirma el peso permitido."
            )
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
                "source": "Booking.com",
                "link": link,
                "note": nota,
                "bag_included_in_fare": con_maleta,
            }
        )

    offers.sort(key=lambda o: o["price"])
    return offers
