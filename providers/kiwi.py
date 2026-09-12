"""Proveedor Kiwi.com (API GraphQL pública de su buscador). No requiere cuenta.

Kiwi agrega tarifas de agencias que Google Flights a veces no muestra, así que
sirve como segunda opinión y como respaldo si Google cambia su formato.
"""
import json
import ssl
import urllib.error
import urllib.request

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


def search(search_cfg, provider_cfg=None):
    nonstop = search_cfg.get("nonstop_only", True)
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
            "maxStopsCount": 0 if nonstop else None,
            "enableSelfTransfer": False,       # nada de conexiones por tu cuenta
            "enableThrowAwayTicketing": False,  # ni trucos que invalidan el boleto
            "enableTrueHiddenCity": False,
            "limit": (provider_cfg or {}).get("limit", 20),
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
        payload = json.load(urllib.request.urlopen(req, timeout=60, context=_CTX))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Kiwi HTTP {exc.code}: {exc.read()[:200]!r}") from exc

    if payload.get("errors"):
        raise RuntimeError("Kiwi GraphQL: " + json.dumps(payload["errors"])[:200])

    node = payload["data"]["returnItineraries"]
    out_currency = (provider_cfg or {}).get("currency", search_cfg.get("currency", "MXN")).upper()
    offers = []
    for it in node.get("itineraries", []):
        out, inb = _segments(it.get("outbound")), _segments(it.get("inbound"))
        if not out or not inb:
            continue
        if nonstop and (len(out) > 1 or len(inb) > 1):
            continue
        legs = [_leg(s) for s in out] + [_leg(s) for s in inb]
        offers.append(
            {
                "price": float(it["price"]["amount"]),
                "currency": out_currency,
                "airline": out[0]["carrier"]["name"],
                "legs": legs,
                "seats_left": None,
                "checked_bag": bool(bags),
                "source": "Kiwi.com",
                "link": f"https://www.kiwi.com/es/search/results/"
                f"{search_cfg['origin']}/{search_cfg['destination']}/"
                f"{search_cfg['departure_date']}/{search_cfg['return_date']}",
                "note": "Precio total viaje redondo"
                + (", 1 maleta documentada incluida" if bags else ""),
            }
        )
    offers.sort(key=lambda o: o["price"])
    return offers
