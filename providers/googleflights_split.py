"""Hack: dos boletos sencillos en vez de uno redondo.

A veces la ida de una aerolínea más la vuelta de otra sale más barata que el
redondo, sobre todo cuando una de las dos fechas es cara. Se reporta solo cuando
realmente gana, y se advierte lo que implica: son dos boletos independientes, así
que si se cancela uno el otro no se reacomoda solo.
"""
from fast_flights import FlightQuery, Passengers, create_query, get_flights


def _cheapest_oneway(search_cfg, date, frm, to):
    q = create_query(
        flights=[FlightQuery(date=date, from_airport=frm, to_airport=to, max_stops=0)],
        trip="one-way",
        seat=search_cfg.get("travel_class") or "economy",
        passengers=Passengers(adults=search_cfg.get("adults", 1)),
        currency=search_cfg.get("currency", "MXN"),
        language="es",
        max_stops=0 if search_cfg.get("nonstop_only", True) else None,
        checked_bags=1 if search_cfg.get("checked_bag", True) else 0,
        hide_separate_and_self_transfer=True,
    )
    results = [f for f in get_flights(q) if len(f.flights) == 1]
    if not results:
        return None
    return min(results, key=lambda f: f.price)


def _leg(f):
    s = f.flights[0]
    y, m, d = s.departure.date
    hh, mm = s.departure.time
    ay, am_, ad = s.arrival.date
    ahh, amm = s.arrival.time
    return {
        "from": s.from_airport.code,
        "to": s.to_airport.code,
        "depart": f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:00",
        "arrive": f"{ay:04d}-{am_:02d}-{ad:02d}T{ahh:02d}:{amm:02d}:00",
        "stops": 0,
        "airline": ", ".join(f.airlines),
        "flight": s.plane_type or "",
        "duration": f"PT{s.duration // 60}H{s.duration % 60}M",
    }


def search(search_cfg, provider_cfg=None):
    ida = _cheapest_oneway(
        search_cfg, search_cfg["departure_date"], search_cfg["origin"], search_cfg["destination"]
    )
    vuelta = _cheapest_oneway(
        search_cfg, search_cfg["return_date"], search_cfg["destination"], search_cfg["origin"]
    )
    if not ida or not vuelta:
        return []

    total = float(ida.price + vuelta.price)
    airlines = sorted({*ida.airlines, *vuelta.airlines})
    return [
        {
            "price": total,
            "currency": search_cfg.get("currency", "MXN"),
            "airline": " + ".join(airlines),
            "legs": [_leg(ida), _leg(vuelta)],
            "seats_left": None,
            "checked_bag": search_cfg.get("checked_bag", True),
            "source": "2 sencillos",
            "link": "https://www.google.com/travel/flights",
            "note": f"DOS BOLETOS SEPARADOS: ida {ida.price:,.0f} + vuelta {vuelta.price:,.0f}. "
            "Si cancelan un vuelo, el otro boleto no se reacomoda solo.",
            "split": True,
        }
    ]
