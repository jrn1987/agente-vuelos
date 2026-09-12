"""Proveedor Google Flights (vía fast-flights). No requiere cuenta ni API key.

Hace varias consultas y las combina, porque Google recorta la lista de resultados
y una sola búsqueda esconde aerolíneas más baratas: se corre una búsqueda general
más una por aerolínea (Iberia, Aeroméxico, Air Europa, World2Fly).
"""
from fast_flights import FlightQuery, Passengers, create_query, get_flights

DEFAULT_AIRLINES = ["IB", "AM", "UX", "2W"]
# Equipaje documentado incluido en tarifas transatlánticas estándar de estas
# aerolíneas: 1 maleta de 23 kg (por encima de los 20 kg solicitados).
CHECKED_BAG_KG = 23


def _query(search_cfg, airline=None):
    legs = [
        FlightQuery(
            date=search_cfg["departure_date"],
            from_airport=search_cfg["origin"],
            to_airport=search_cfg["destination"],
            max_stops=0 if search_cfg.get("nonstop_only", True) else None,
            airlines=[airline] if airline else None,
        ),
        FlightQuery(
            date=search_cfg["return_date"],
            from_airport=search_cfg["destination"],
            to_airport=search_cfg["origin"],
            max_stops=0 if search_cfg.get("nonstop_only", True) else None,
            airlines=[airline] if airline else None,
        ),
    ]
    return create_query(
        flights=legs,
        trip="round-trip",
        seat=search_cfg.get("travel_class") or "economy",
        passengers=Passengers(adults=search_cfg.get("adults", 1)),
        currency=search_cfg.get("currency", "MXN"),
        language="es",
        max_stops=0 if search_cfg.get("nonstop_only", True) else None,
        checked_bags=1 if search_cfg.get("checked_bag", True) else 0,
        hide_separate_and_self_transfer=True,
    )


def _fmt_dt(sd):
    y, m, d = sd.date
    hh, mm = sd.time
    return f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:00"


def _link(s):
    import urllib.parse

    q = (
        f"vuelos de {s['origin']} a {s['destination']} el {s['departure_date']} "
        f"regresando el {s['return_date']} sin escalas"
    )
    return "https://www.google.com/travel/flights?q=" + urllib.parse.quote(q)


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    airlines = provider_cfg.get("airlines", DEFAULT_AIRLINES)
    seen, offers, errors = set(), [], []

    for airline in [None] + list(airlines):
        try:
            results = get_flights(_query(search_cfg, airline))
        except Exception as exc:  # una aerolínea sin vuelos no debe tumbar la corrida
            errors.append(f"{airline or 'general'}: {type(exc).__name__}")
            continue

        for f in results:
            segs = f.flights
            if search_cfg.get("nonstop_only", True) and len(segs) > 1:
                continue
            key = (f.price, tuple(f.airlines), _fmt_dt(segs[0].departure))
            if key in seen:
                continue
            seen.add(key)
            offers.append(
                {
                    "price": float(f.price),
                    "currency": search_cfg.get("currency", "MXN"),
                    "airline": ", ".join(f.airlines),
                    "legs": [
                        {
                            "from": s.from_airport.code,
                            "to": s.to_airport.code,
                            "depart": _fmt_dt(s.departure),
                            "arrive": _fmt_dt(s.arrival),
                            "stops": 0,
                            "airline": ", ".join(f.airlines),
                            "flight": s.plane_type or "",
                            "duration": f"PT{s.duration // 60}H{s.duration % 60}M",
                        }
                        for s in segs
                    ],
                    "seats_left": None,
                    "checked_bag": search_cfg.get("checked_bag", True),
                    "source": "Google Flights",
                    "link": _link(search_cfg),
                    "note": "Precio total viaje redondo, 1 maleta documentada incluida"
                    if search_cfg.get("checked_bag", True)
                    else "Precio total viaje redondo",
                }
            )

    if not offers and errors:
        raise RuntimeError("Ninguna consulta devolvió vuelos: " + "; ".join(errors))
    offers.sort(key=lambda o: o["price"])
    return offers
