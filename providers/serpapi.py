"""Proveedor SerpAPI (motor google_flights). Requiere API key de serpapi.com."""
import json
import urllib.parse
import urllib.request


def search(search_cfg, provider_cfg):
    params = {
        "engine": "google_flights",
        "departure_id": search_cfg["origin"],
        "arrival_id": search_cfg["destination"],
        "outbound_date": search_cfg["departure_date"],
        "return_date": search_cfg["return_date"],
        "adults": search_cfg.get("adults", 1),
        "currency": search_cfg.get("currency", "MXN"),
        "hl": "es",
        "gl": "mx",
        "api_key": provider_cfg["api_key"],
    }
    if search_cfg.get("nonstop_only", True):
        params["stops"] = 1  # 1 = solo vuelos directos

    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        payload = json.load(r)
    if payload.get("error"):
        raise RuntimeError(payload["error"])

    offers = []
    for group in ("best_flights", "other_flights"):
        for item in payload.get(group, []):
            segs = item.get("flights", [])
            if not segs:
                continue
            if search_cfg.get("nonstop_only", True) and len(segs) > 1:
                continue
            legs = [
                {
                    "from": s["departure_airport"]["id"],
                    "to": s["arrival_airport"]["id"],
                    "depart": s["departure_airport"]["time"],
                    "arrive": s["arrival_airport"]["time"],
                    "stops": 0,
                    "airline": s.get("airline", ""),
                    "flight": s.get("flight_number", ""),
                    "duration": f"{s.get('duration', '')} min",
                }
                for s in segs
            ]
            offers.append(
                {
                    "price": float(item["price"]),
                    "currency": search_cfg.get("currency", "MXN"),
                    "airline": legs[0]["airline"],
                    "legs": legs,
                    "seats_left": None,
                    "source": "Google Flights (SerpAPI)",
                    "link": payload.get("search_metadata", {}).get("google_flights_url", ""),
                }
            )
    offers.sort(key=lambda o: o["price"])
    return offers
