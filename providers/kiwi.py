"""Proveedor Kiwi.com (API GraphQL pública de su buscador). No requiere cuenta.

Kiwi agrega tarifas de agencias que Google Flights a veces no muestra, así que
sirve como segunda opinión y como respaldo si Google cambia su formato.
"""
import json
import ssl
import urllib.error
import urllib.request

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escalas  # noqa: E402

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # en Linux los certificados del sistema bastan
    _CTX = ssl.create_default_context()

ENDPOINT = (
    "https://api.skypicker.com/umbrella/v2/graphql"
    "?featureName=SearchReturnItinerariesQuery"
)

QUERY = """
query Q($search: SearchReturnInput, $filter: ItinerariesFilterInput, $options: ItinerariesOptionsInput) {
  returnItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on Itineraries {
      itineraries {
        id
        price { amount }
        ... on ItineraryReturn {
          outbound { sectorSegments { segment {
            source { station { code } localTime }
            destination { station { code } localTime }
            carrier { name code } duration } } }
          inbound { sectorSegments { segment {
            source { station { code } localTime }
            destination { station { code } localTime }
            carrier { name code } duration } } }
        }
      }
    }
  }
}"""


def _segments(sector):
    return [s["segment"] for s in (sector or {}).get("sectorSegments", [])]


def _leg(seg):
    return {
        "from": seg["source"]["station"]["code"],
        "to": seg["destination"]["station"]["code"],
        "depart": seg["source"]["localTime"],
        "arrive": seg["destination"]["localTime"],
        "stops": 0,
        "airline": seg["carrier"]["name"],
        "flight": seg["carrier"]["code"],
        "duration": f"PT{seg['duration'] // 3600}H{seg['duration'] % 3600 // 60}M",
    }


def _max_stops(search_cfg, provider_cfg=None):
    """Kiwi tarda minutos y se cae cuando se le piden escalas, así que su tope
    se puede fijar aparte (provider_cfg["max_stops"]) sin tocar el del resto."""
    if provider_cfg and provider_cfg.get("max_stops") is not None:
        return provider_cfg["max_stops"]
    if search_cfg.get("nonstop_only") is True and search_cfg.get("max_stops") is None:
        return 0
    return search_cfg.get("max_stops", 0)


def _consultar(search_cfg, provider_cfg, self_transfer):
    """Una consulta a Kiwi. self_transfer decide si acepta boletos separados."""
    tope = _max_stops(search_cfg, provider_cfg)
    bags = 1 if search_cfg.get("checked_bag", True) else 0
    variables = {
        "search": {
            "itinerary": {
                "source": {"ids": [f"Station:airport:{search_cfg['origin']}"]},
                "destination": {"ids": [f"Station:airport:{search_cfg['destination']}"]},
                "outboundDepartureDate": {
                    "start": f"{search_cfg['departure_date']}T00:00:00",
                    "end": f"{search_cfg['departure_date']}T23:59:59",
                },
                "inboundDepartureDate": {
                    "start": f"{search_cfg['return_date']}T00:00:00",
                    "end": f"{search_cfg['return_date']}T23:59:59",
                },
            },
            "passengers": {
                "adults": search_cfg.get("adults", 1),
                "children": 0,
                "infants": 0,
                "adultsHoldBags": bags,
                "adultsHandBags": 1,
            },
            "cabinClass": {
                "cabinClass": (search_cfg.get("travel_class") or "economy").upper().replace("-", "_"),
                "applyMixedClasses": False,
            },
        },
        "filter": {
            "maxStopsCount": tope,
            "enableSelfTransfer": self_transfer,
            "enableThrowAwayTicketing": False,  # nada de trucos que invalidan el boleto
            "enableTrueHiddenCity": False,
            # Con escalas la consulta pesa mucho más; pedir menos evita que se caiga.
            "limit": (provider_cfg or {}).get("limit", 10 if tope else 20),
        },
        "options": {
            "partner": "skypicker",
            "currency": (provider_cfg or {}).get("currency", search_cfg.get("currency", "MXN")).lower(),
            "locale": (provider_cfg or {}).get("locale", "es"),
            "market": (provider_cfg or {}).get("market", "mx"),
            "storeSearch": False,
        },
    }

    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0",
            "kw-skypicker-visitor-uniqid": "00000000-0000-0000-0000-000000000000",
        },
    )
    try:
        espera = (provider_cfg or {}).get("timeout", 90)
        payload = json.load(urllib.request.urlopen(req, timeout=espera, context=_CTX))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Kiwi HTTP {exc.code}: {exc.read()[:200]!r}") from exc

    if payload.get("errors"):
        raise RuntimeError("Kiwi GraphQL: " + json.dumps(payload["errors"])[:200])

    node = payload["data"]["returnItineraries"]
    out_currency = (provider_cfg or {}).get("currency", search_cfg.get("currency", "MXN")).upper()
    return node.get("itineraries", []), out_currency


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    tope = _max_stops(search_cfg, provider_cfg)
    permitir_separados = search_cfg.get("allow_separate_tickets", False)

    itinerarios, out_currency = _consultar(search_cfg, provider_cfg, permitir_separados)

    # Para saber CUÁLES son de boleto separado, se pide también lo que Kiwi
    # entrega sin self-transfer: lo que sobra en la primera lista lo es.
    ids_mismo_boleto = None
    if permitir_separados:
        try:
            base, _ = _consultar(
                search_cfg, {**provider_cfg, "timeout": 25}, False
            )
            ids_mismo_boleto = {i["id"] for i in base}
        except Exception:
            # No se pudo distinguir. No se asume nada: se marca como "sin confirmar".
            ids_mismo_boleto = None

    offers = []
    for it in itinerarios:
        out, inb = _segments(it.get("outbound")), _segments(it.get("inbound"))
        if not out or not inb:
            continue
        if tope is not None and (len(out) - 1 > tope or len(inb) - 1 > tope):
            continue
        legs = [_leg(x) for x in out] + [_leg(x) for x in inb]
        paradas = escalas.de_tramos([_leg(x) for x in out]) + escalas.de_tramos(
            [_leg(x) for x in inb]
        )
        if not escalas.cumple(paradas, search_cfg.get("max_layover_hours")):
            continue
        if not permitir_separados:
            separados = False
        elif ids_mismo_boleto is None:
            separados = None  # no se pudo confirmar
        else:
            separados = it["id"] not in ids_mismo_boleto
        offers.append(
            {
                "price": float(it["price"]["amount"]),
                "currency": out_currency,
                "airline": out[0]["carrier"]["name"],
                "legs": legs,
                "seats_left": None,
                "checked_bag": search_cfg.get("checked_bag", True),
                "stops": max(len(out) - 1, len(inb) - 1),
                "layovers": paradas,
                "separate_tickets": separados,
                "source": "Kiwi.com"
                + (
                    " (boletos separados)"
                    if separados
                    else (" (boleto sin confirmar)" if separados is None else "")
                ),
                "link": f"https://www.kiwi.com/es/search/results/"
                f"{search_cfg['origin']}/{search_cfg['destination']}/"
                f"{search_cfg['departure_date']}/{search_cfg['return_date']}",
                "note": "Precio total viaje redondo"
                + (", 1 maleta documentada incluida" if search_cfg.get("checked_bag", True) else "")
                + (
                    ". BOLETOS SEPARADOS: en la escala recoges y vuelves a documentar "
                    "la maleta, pasas migración y te vuelves a documentar. Si el primer "
                    "vuelo se retrasa, NADIE te reacomoda en el segundo: pierdes ese boleto."
                    if separados
                    else (
                        ". No pude confirmar si es un solo boleto o dos: verifícalo en "
                        "Kiwi antes de comprar."
                        if separados is None
                        else ""
                    )
                ),
            }
        )
    offers.sort(key=lambda o: o["price"])
    return offers
