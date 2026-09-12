"""Proveedor Amadeus Self-Service (API oficial, plan gratuito disponible)."""
import json
import time
import urllib.parse
import urllib.request

_HOSTS = {
    "production": "https://api.amadeus.com",
    "test": "https://test.api.amadeus.com",
}
_token_cache = {"value": None, "expires_at": 0}


def _token(cfg):
    if _token_cache["value"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["value"]
    host = _HOSTS[cfg.get("environment", "production")]
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{host}/v1/security/oauth2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    _token_cache["value"] = payload["access_token"]
    _token_cache["expires_at"] = time.time() + payload.get("expires_in", 1799)
    return _token_cache["value"]


def search(search_cfg, provider_cfg):
    host = _HOSTS[provider_cfg.get("environment", "production")]
    params = {
        "originLocationCode": search_cfg["origin"],
        "destinationLocationCode": search_cfg["destination"],
        "departureDate": search_cfg["departure_date"],
        "returnDate": search_cfg["return_date"],
        "adults": search_cfg.get("adults", 1),
        "currencyCode": search_cfg.get("currency", "MXN"),
        "max": 30,
    }
    if search_cfg.get("nonstop_only", True):
        params["nonStop"] = "true"
    if search_cfg.get("travel_class"):
        params["travelClass"] = search_cfg["travel_class"]

    url = f"{host}/v2/shopping/flight-offers?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token(provider_cfg)}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)

    carriers = payload.get("dictionaries", {}).get("carriers", {})
    offers = []
    for offer in payload.get("data", []):
        itineraries = offer.get("itineraries", [])
        if len(itineraries) < 2:
            continue
        legs = []
        nonstop = True
        for it in itineraries:
            segs = it.get("segments", [])
            if len(segs) != 1:
                nonstop = False
            first, last = segs[0], segs[-1]
            code = first.get("carrierCode", "")
            legs.append(
                {
                    "from": first["departure"]["iataCode"],
                    "to": last["arrival"]["iataCode"],
                    "depart": first["departure"]["at"],
                    "arrive": last["arrival"]["at"],
                    "stops": len(segs) - 1,
                    "airline": carriers.get(code, code),
                    "flight": f"{code}{first.get('number', '')}",
                    "duration": it.get("duration", ""),
                }
            )
        if search_cfg.get("nonstop_only", True) and not nonstop:
            continue
        offers.append(
            {
                "price": float(offer["price"]["grandTotal"]),
                "currency": offer["price"].get("currency", search_cfg.get("currency", "MXN")),
                "airline": legs[0]["airline"],
                "legs": legs,
                "seats_left": offer.get("numberOfBookableSeats"),
                "source": "Amadeus",
                "link": _gflights_link(search_cfg),
            }
        )
    offers.sort(key=lambda o: o["price"])
    return offers


def _gflights_link(s):
    return (
        "https://www.google.com/travel/flights?q="
        + urllib.parse.quote(
            f"Flights from {s['origin']} to {s['destination']} on "
            f"{s['departure_date']} through {s['return_date']} nonstop"
        )
    )
