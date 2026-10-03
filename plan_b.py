"""Plan B: vuelos directos a otros destinos, en las mismas fechas.

Si Madrid no baja, conviene saber qué más se puede volar el 22 de diciembre sin
escalas y con maleta. No compite con la búsqueda principal: es una comparación
aparte, para decidir con números en lugar de intuición.

Se consulta solo Google Flights y sin barrido por aerolínea: una consulta por
destino. Con cinco destinos son cinco llamadas, no veinticinco.
"""
import providers

DESTINOS = [
    {"code": "LAX", "name": "Los Ángeles"},
    {"code": "JFK", "name": "Nueva York"},
    {"code": "ORD", "name": "Chicago"},
    {"code": "CDG", "name": "París"},
    {"code": "NRT", "name": "Tokio"},
]


def buscar(search_cfg, ajustes=None):
    """Devuelve [{code, name, offer|None, error|None}] ordenado por precio."""
    ajustes = ajustes or {}
    destinos = ajustes.get("destinations", DESTINOS)
    buscar_fn = providers.get("googleflights")

    resultados = []
    for d in destinos:
        cfg = dict(
            search_cfg,
            destination=d["code"],
            max_stops=0,          # el plan B es solo para vuelos directos
            nonstop_only=None,
            checked_bag=True,
        )
        try:
            # airlines vacío = una sola consulta, sin barrido por aerolínea
            offers = buscar_fn(cfg, {"airlines": [], "max_stops": 0})
            directos = [o for o in offers if not o.get("stops")]
            mejor = min(directos, key=lambda o: o["price"]) if directos else None
            resultados.append(
                {
                    "code": d["code"],
                    "name": d["name"],
                    "offer": mejor,
                    "error": None if mejor else "sin vuelos directos",
                }
            )
        except Exception as exc:
            resultados.append(
                {
                    "code": d["code"],
                    "name": d["name"],
                    "offer": None,
                    "error": f"{type(exc).__name__}",
                }
            )

    con_precio = [r for r in resultados if r["offer"]]
    sin_precio = [r for r in resultados if not r["offer"]]
    con_precio.sort(key=lambda r: r["offer"]["price"])
    return con_precio + sin_precio
