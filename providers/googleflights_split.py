"""Hack: dos boletos sencillos en vez de uno redondo.

A veces la ida de una aerolínea más la vuelta de otra sale más barata que el
redondo, sobre todo cuando una de las dos fechas es cara. Se reporta solo cuando
realmente gana, y se advierte lo que implica: son dos boletos independientes, así
que si se cancela uno el otro no se reacomoda solo.
"""
import os
import sys

from fast_flights import FlightQuery, Passengers, create_query, get_flights

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import escalas  # noqa: E402


def _tope(search_cfg, provider_cfg=None):
    """provider_cfg["max_stops"]=0 fuerza la variante "multi-aerolínea directo":
    ida directa con una aerolínea y vuelta directa con otra, en dos boletos."""
    if provider_cfg and provider_cfg.get("max_stops") is not None:
        return provider_cfg["max_stops"]
    if search_cfg.get("nonstop_only") is True and search_cfg.get("max_stops") is None:
        return 0
    return search_cfg.get("max_stops", 0)


def _cheapest_oneway(search_cfg, date, frm, to, provider_cfg=None):
    tope = _tope(search_cfg, provider_cfg)
    q = create_query(
        flights=[FlightQuery(date=date, from_airport=frm, to_airport=to, max_stops=tope)],
        trip="one-way",
        seat=search_cfg.get("travel_class") or "economy",
        passengers=Passengers(adults=search_cfg.get("adults", 1)),
        currency=search_cfg.get("currency", "MXN"),
        language="es",
        max_stops=tope,
        checked_bags=1 if search_cfg.get("checked_bag", True) else 0,
        hide_separate_and_self_transfer=True,
    )
    validos = []
    for f in get_flights(q):
        if tope is not None and len(f.flights) - 1 > tope:
            continue
        tramos = [
            {
                "to": s.to_airport.code,
                "arrive": f"{s.arrival.date[0]:04d}-{s.arrival.date[1]:02d}-"
                          f"{s.arrival.date[2]:02d}T{s.arrival.time[0]:02d}:{s.arrival.time[1]:02d}:00",
                "depart": f"{s.departure.date[0]:04d}-{s.departure.date[1]:02d}-"
                          f"{s.departure.date[2]:02d}T{s.departure.time[0]:02d}:{s.departure.time[1]:02d}:00",
            }
            for s in f.flights
        ]
        paradas = escalas.de_tramos(tramos)
        if not escalas.cumple(paradas, search_cfg.get("max_layover_hours")):
            continue
        validos.append((f, paradas))
    if not validos:
        return None
    return min(validos, key=lambda par: par[0].price)


def _legs(f):
    return [_leg_de(s, f) for s in f.flights]


def _leg_de(s, f):
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
    r_ida = _cheapest_oneway(
        search_cfg, search_cfg["departure_date"], search_cfg["origin"],
        search_cfg["destination"], provider_cfg,
    )
    r_vuelta = _cheapest_oneway(
        search_cfg, search_cfg["return_date"], search_cfg["destination"],
        search_cfg["origin"], provider_cfg,
    )
    if not r_ida or not r_vuelta:
        return []
    ida, paradas_ida = r_ida
    vuelta, paradas_vuelta = r_vuelta

    total = float(ida.price + vuelta.price)
    airlines = sorted({*ida.airlines, *vuelta.airlines})
    return [
        {
            "price": total,
            "currency": search_cfg.get("currency", "MXN"),
            "airline": " + ".join(airlines),
            "legs": _legs(ida) + _legs(vuelta),
            "seats_left": None,
            "checked_bag": search_cfg.get("checked_bag", True),
            "stops": max(len(ida.flights), len(vuelta.flights)) - 1,
            "layovers": paradas_ida + paradas_vuelta,
            "separate_tickets": True,
            "source": "2 sencillos"
            + (" directos" if _tope(search_cfg, provider_cfg) == 0 else ""),
            "link": "https://www.google.com/travel/flights",
            "note": f"DOS BOLETOS SEPARADOS: ida {ida.price:,.0f} + vuelta {vuelta.price:,.0f}. "
            "Si cancelan un vuelo, el otro boleto no se reacomoda solo.",
            "split": True,
        }
    ]
