"""Formato de los correos."""
import datetime as dt
import re

import correo
import escalas
import msi
import stats


def money(amount, currency):
    return f"${amount:,.0f} {currency}"


def _hhmm(iso):
    try:
        return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m %H:%M")
    except Exception:
        return iso


def _dur(d):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", d or "")
    if not m:
        return d or ""
    h, mi = m.group(1) or 0, m.group(2) or 0
    return f"{h}h {mi}m"


def subject(reason, best, search):
    p = money(best["price"], best["currency"])
    tags = {
        "jackpot": f"🚨 ¡VUELO BUENO! {p} — directo {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "first_run": f"✈️ Agente activo — {search['origin']}→{search['destination']} desde {p}",
        "new_low": f"🔻 NUEVO MÍNIMO {p} — {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "drop": f"🔻 Bajó de precio: {p} — {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "drop_directo": f"🔻 Bajó el DIRECTO — {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "at_reference": f"➡️ Sigue en {p} — {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "digest": f"📊 Resumen diario {search['origin']}→{search['destination']} — mejor {p}",
        "prueba": f"🧪 Prueba del agente — {search['origin']}→{search['destination']} en {p}",
        "heartbeat": f"✅ Sigo vigilando — {search['origin']}→{search['destination']} en {p}",
    }
    return tags.get(reason, f"Vuelos {search['origin']}→{search['destination']}: {p}")


HEADLINES = {
    "jackpot": "🚨 ESTE VUELO VALE LA PENA: está por debajo de tu objetivo.\n"
               "Los precios de temporada alta se mueven rápido; si te sirve, resérvalo hoy.",
    "new_low": "🔻 Nuevo mínimo desde que el agente vigila esta ruta.",
    "drop": "🔻 El precio bajó contra la revisión anterior.",
    "at_reference": "El precio sigue en el nivel original o por debajo.",
    "drop_directo": "🔻 Bajó el precio del vuelo DIRECTO. Mira la sección de\n"
                    "la mejor opción directa más abajo.",
    "first_run": "Primera búsqueda. Este es el panorama actual; a partir de aquí solo te aviso si mejora.",
    "digest": "Resumen diario.",
    "prueba": "🧪 Correo de prueba pedido a mano. Todo lo que sigue son datos reales\n"
              "de esta búsqueda: así se ve un aviso normal del agente.",
    "heartbeat": "Sin novedades: el precio no ha mejorado lo suficiente para avisarte.\n"
                 "Te escribo de todos modos para que sepas que el agente sigue vivo.",
}


def body(reason, offers, state, search, threshold=None, history_path=None, plan_b=None):
    best = offers[0]
    prev = state.get("last_best_price")
    low = state.get("all_time_low")
    lines = []
    if HEADLINES.get(reason):
        lines += [HEADLINES[reason], ""]
    lines.append(f"Mejor precio ahora: {money(best['price'], best['currency'])} ({best['airline']})")
    if threshold:
        gap = best["price"] - threshold
        lines.append(
            f"Contra tu objetivo de {money(threshold, best['currency'])}: "
            + (f"{money(abs(gap), best['currency'])} POR DEBAJO ✅" if gap < 0
               else f"faltan {money(gap, best['currency'])} para llegar")
        )
    if prev:
        diff = best["price"] - prev
        lines.append(
            f"Contra la búsqueda anterior: {'+' if diff >= 0 else ''}{money(diff, best['currency'])}"
        )
    if low:
        lines.append(f"Mínimo histórico registrado: {money(low, best['currency'])}")
    lines.append("")
    tope = search.get("max_stops", 0)
    if tope:
        criterio = (
            f"Directos y con hasta {tope} escala, "
            f"siempre que la escala no pase de {search.get('max_layover_hours', 6)} horas"
        )
    else:
        criterio = "Solo vuelos directos"
    lines.append(f"Ruta: {search['origin']} → {search['destination']} · {criterio}")
    if best.get("checked_bag"):
        lines.append("Incluye 1 maleta documentada de 23 kg (filtro aplicado en la búsqueda)")
    lines.append(f"Ida {search['departure_date']} · Regreso {search['return_date']} · {search.get('adults',1)} adulto(s)")
    lines.append("")
    directos = [o for o in offers if not o.get("stops")]
    if directos and directos[0] is not best:
        d = directos[0]
        extra = d["price"] - best["price"]
        lines.append("")
        lines.append("MEJOR OPCIÓN DIRECTA (sin escalas)")
        lines.append("-" * 60)
        lines.append(f"{money(d['price'], d['currency'])} — {d['airline']}  [{d['source']}]")
        for leg in d["legs"]:
            lines.append(
                f"   {leg['from']}→{leg['to']}  {_hhmm(leg['depart'])} → {_hhmm(leg['arrive'])}"
                f"  {leg['flight']}  {_dur(leg['duration'])}"
            )
        lines.append(
            f"Cuesta {money(extra, d['currency'])} más que la opción más barata, "
            "que lleva escala."
        )
    elif not directos:
        lines.append("")
        lines.append("MEJOR OPCIÓN DIRECTA (sin escalas)")
        lines.append("-" * 60)
        lines.append("Ninguna fuente devolvió vuelos directos en esta revisión.")

    if best.get("separate_tickets"):
        lines.append("")
        lines.append("⚠️ LA MÁS BARATA ES DE BOLETOS SEPARADOS")
        lines.append(
            "   Son dos contratos distintos: en la escala recoges la maleta, pasas\n"
            "   migración y vuelves a documentar. Si el primer vuelo se retrasa,\n"
            "   nadie te reacomoda en el segundo y pierdes ese boleto.\n"
            "   Compáralo con la mejor opción de un solo boleto antes de decidir."
        )
    lines.append("")
    lines.append("TOP 5 OPCIONES (precio = total viaje redondo por persona)")
    lines.append("-" * 60)
    for i, o in enumerate(offers[:5], 1):
        etiqueta = "DIRECTO" if not o.get("stops") else f"{o['stops']} escala(s)"
        if o.get("separate_tickets"):
            etiqueta += " · BOLETOS SEPARADOS"
        lines.append(
            f"{i}. {money(o['price'], o['currency'])} — {o['airline']}  "
            f"[{o['source']}]  ({etiqueta})"
        )
        for aeropuerto, minutos in o.get("layovers") or []:
            lines.append(f"   ⏱ escala en {aeropuerto}: {escalas.formato(minutos)}")
        for leg in o["legs"]:
            lines.append(
                f"   {leg['from']}→{leg['to']}  {_hhmm(leg['depart'])} → {_hhmm(leg['arrive'])}"
                f"  {leg['flight']}  {_dur(leg['duration'])}"
            )
        if o.get("note") and o.get("source") not in ("Google Flights", "Kiwi.com"):
            lines.append(f"   ⚠️ {o['note']}")
        if o.get("seats_left"):
            lines.append(f"   Asientos disponibles a este precio: {o['seats_left']}")
        lines.append("")
    if history_path:
        lines.append(stats.bloque(history_path, best["price"], best["currency"]))
        lines.append("")
    lines.append(msi.bloque(best, search))
    lines.append("")
    lines.append(f"Mejor oferta encontrada en: {best['source']}")
    if best.get("link"):
        lines.append(f"Ver / reservar: {best['link']}")
    lines.append("")
    if plan_b:
        lines.append("")
        lines.append("PLAN B — OTROS DESTINOS DIRECTOS, MISMAS FECHAS")
        lines.append("-" * 60)
        for alt in plan_b:
            o = alt.get("offer")
            if o:
                lines.append(
                    f"  {alt['name']:<14} {money(o['price'], o['currency']):>16}  "
                    f"{o['airline']}"
                )
            else:
                lines.append(f"  {alt['name']:<14} {'sin vuelos directos':>16}")
        lines.append("")
    lines.append(f"Revisado: {dt.datetime.now(dt.timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M')}")

    text = "\n".join(lines)
    bloques = []
    if history_path:
        bloques.append(("Tendencia", stats.bloque(history_path, best["price"], best["currency"])))
    bloques.append(("Meses sin intereses — BBVA y Amex", msi.bloque(best, search)))
    serie = stats.por_dia(history_path) if history_path else []
    try:
        html = correo.construir(
            reason,
            offers,
            search,
            threshold,
            HEADLINES.get(reason),
            bloques,
            plan_b=plan_b,
            serie=serie,
        )
    except Exception:
        # Si el diseño falla por algo inesperado, mejor un correo feo que ninguno.
        html = (
            "<pre style=\"font-family:ui-monospace,monospace;font-size:13px;"
            "white-space:pre-wrap\">" + text.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
        )
    return text, html
