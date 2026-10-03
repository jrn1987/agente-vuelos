"""Travelpayouts / Aviasales. Gratis, con token de afiliado.

Dos límites de esta API que determinan cómo se usa aquí:

1. Devuelve precios de CACHÉ, no consultas en vivo. Sirve para enterarse de que
   una tarifa baja existe; el precio se confirma en el buscador al abrir el enlace.
2. No dice cuánto dura cada escala ni si la tarifa incluye maleta. Como el límite
   de 6 horas de escala no se puede verificar, de esta fuente solo se toman
   VUELOS DIRECTOS, que además son la prioridad. La maleta se estima y se avisa.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import equipaje  # noqa: E402

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()

ENDPOINT = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _duracion(minutos):
    if not minutos:
        return ""
    return f"PT{int(minutos) // 60}H{int(minutos) % 60}M"


SONDEOS = [
    ("redondo directo", {"direct": "true", "one_way": "false", "con_regreso": True}),
    ("redondo con escalas", {"direct": "false", "one_way": "false", "con_regreso": True}),
    ("solo ida directo", {"direct": "true", "one_way": "true", "con_regreso": False}),
    ("solo ida con escalas", {"direct": "false", "one_way": "true", "con_regreso": False}),
    ("mes completo ida", {"direct": "false", "one_way": "true", "con_regreso": False,
                          "mes": True}),
]


def sondear(search_cfg, token):
    """Prueba combinaciones para saber qué tiene la caché de Aviasales.

    La API respondió data vacía para el viaje redondo directo, y sin esto solo
    quedaba adivinar qué parámetro es el que la deja sin datos.
    """
    for etiqueta, ajustes in SONDEOS:
        p = {
            "origin": search_cfg["origin"],
            "destination": search_cfg["destination"],
            "departure_at": search_cfg["departure_date"][:7]
            if ajustes.get("mes")
            else search_cfg["departure_date"],
            "currency": search_cfg.get("currency", "MXN").lower(),
            "sorting": "price",
            "direct": ajustes["direct"],
            "one_way": ajustes["one_way"],
            "limit": 30,
            "token": token,
        }
        if ajustes["con_regreso"]:
            p["return_at"] = search_cfg["return_date"]
        try:
            req = urllib.request.Request(
                ENDPOINT + "?" + urllib.parse.urlencode(p),
                headers={"accept": "application/json"},
            )
            d = json.load(urllib.request.urlopen(req, timeout=40, context=_CTX))
            filas = d.get("data") or []
            muestra = ""
            if filas:
                f0 = filas[0]
                muestra = (
                    f" · ej: {f0.get('airline')} {f0.get('price')} "
                    f"escalas={f0.get('transfers')} sale={str(f0.get('departure_at'))[:10]}"
                )
            print(f"    [sondeo] {etiqueta:<22} {len(filas):>3} registros{muestra}")
        except Exception as exc:
            print(f"    [sondeo] {etiqueta:<22} ERROR {type(exc).__name__}: {str(exc)[:60]}")


def search(search_cfg, provider_cfg=None):
    provider_cfg = provider_cfg or {}
    token = provider_cfg.get("token")
    if not token:
        raise RuntimeError(
            "Falta el token de Travelpayouts (variable TRAVELPAYOUTS_TOKEN)."
        )

    params = {
        "origin": search_cfg["origin"],
        "destination": search_cfg["destination"],
        "departure_at": search_cfg["departure_date"],
        "return_at": search_cfg["return_date"],
        "currency": search_cfg.get("currency", "MXN").lower(),
        "sorting": "price",
        "direct": "true",  # ver nota 2 arriba
        "unique": "false",
        "limit": provider_cfg.get("limit", 30),
        "one_way": "false",
        "token": token,
    }
    if provider_cfg.get("sondeo"):
        sondear(search_cfg, token)

    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=45, context=_CTX))
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read()[:200]
        if exc.code in (401, 403):
            raise RuntimeError(
                f"Travelpayouts rechazó el token (HTTP {exc.code}). Revisa el secret."
            ) from exc
        raise RuntimeError(f"Travelpayouts HTTP {exc.code}: {cuerpo!r}") from exc

    if not payload.get("success", True):
        raise RuntimeError(f"Travelpayouts: {str(payload.get('error'))[:150]}")

    crudas = payload.get("data") or []
    if provider_cfg.get("diagnostico"):
        # Para entender por qué una respuesta válida llega vacía.
        print(f"    [tp] respuesta: {len(crudas)} registros · claves={list(payload)}")
        for d in crudas[:3]:
            print(
                f"    [tp] {d.get('airline')} {d.get('price')} "
                f"escalas={d.get('transfers')}/{d.get('return_transfers')} "
                f"sale={d.get('departure_at')} vuelve={d.get('return_at')}"
            )

    quiere_maleta = search_cfg.get("checked_bag", True)
    offers = []
    descartadas = {"con_escala": 0, "sin_precio": 0}
    for d in crudas:
        if d.get("transfers") or d.get("return_transfers"):
            descartadas["con_escala"] += 1
            continue  # solo directos: no se puede verificar la escala
        tarifa = float(d.get("price") or 0)
        if not tarifa:
            descartadas["sin_precio"] += 1
            continue

        cache = (
            "Precio de CACHÉ de Aviasales: confirma el monto al abrir el enlace, "
            "puede haber cambiado."
        )
        precio = tarifa
        nota = cache
        con_maleta = quiere_maleta
        if quiere_maleta:
            estimado, explicacion = equipaje.estimar(d.get("airline", ""))
            if estimado is None:
                # Antes se descartaba la oferta, y una aerolínea sin tarifa en la
                # tabla hacía desaparecer la fuente entera sin explicar por qué.
                con_maleta = False
                nota = (
                    f"Tarifa {tarifa:,.0f} SIN maleta documentada y sin tarifa de "
                    f"equipaje registrada para {d.get('airline', '?')}: súmale ese "
                    f"costo al reservar. {cache}"
                )
            else:
                precio = tarifa + estimado
                nota = f"Tarifa {tarifa:,.0f} de caché. {explicacion} {cache}"

        enlace = d.get("link") or ""
        if enlace.startswith("/"):
            enlace = "https://www.aviasales.com" + enlace

        offers.append(
            {
                "price": precio,
                "currency": search_cfg.get("currency", "MXN").upper(),
                "airline": d.get("airline", ""),
                "legs": [
                    {
                        "from": d.get("origin_airport", search_cfg["origin"]),
                        "to": d.get("destination_airport", search_cfg["destination"]),
                        "depart": d.get("departure_at", ""),
                        "arrive": "",
                        "stops": 0,
                        "airline": d.get("airline", ""),
                        "flight": str(d.get("flight_number", "")),
                        "duration": _duracion(d.get("duration_to")),
                    },
                    {
                        "from": d.get("destination_airport", search_cfg["destination"]),
                        "to": d.get("origin_airport", search_cfg["origin"]),
                        "depart": d.get("return_at", ""),
                        "arrive": "",
                        "stops": 0,
                        "airline": d.get("airline", ""),
                        "flight": "",
                        "duration": _duracion(d.get("duration_back")),
                    },
                ],
                "seats_left": None,
                "checked_bag": con_maleta,
                "stops": 0,
                "layovers": [],
                "separate_tickets": False,
                "source": "Aviasales (caché)",
                "link": enlace,
                "links": [("Ver en Aviasales", enlace)] if enlace else None,
                "note": nota,
                "cached": True,
            }
        )

    if provider_cfg.get("diagnostico") and not offers:
        print(
            f"    [tp] sin ofertas utilizables · descartadas por escala: "
            f"{descartadas['con_escala']}, sin precio: {descartadas['sin_precio']}"
        )
    offers.sort(key=lambda o: o["price"])
    return offers
