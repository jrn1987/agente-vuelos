"""Formato de los correos."""
import datetime as dt
import re

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
        "at_reference": f"➡️ Sigue en {p} — {search['origin']}→{search['destination']} 22 dic / 2 ene",
        "digest": f"📊 Resumen diario {search['origin']}→{search['destination']} — mejor {p}",
        "heartbeat": f"✅ Sigo vigilando — {search['origin']}→{search['destination']} en {p}",
    }
    return tags.get(reason, f"Vuelos {search['origin']}→{search['destination']}: {p}")


HEADLINES = {
    "jackpot": "🚨 ESTE VUELO VALE LA PENA: está por debajo de tu objetivo.\n"
               "Los precios de temporada alta se mueven rápido; si te sirve, resérvalo hoy.",
    "new_low": "🔻 Nuevo mínimo desde que el agente vigila esta ruta.",
    "drop": "🔻 El precio bajó contra la revisión anterior.",
    "at_reference": "El precio sigue en el nivel original o por debajo.",
    "first_run": "Primera búsqueda. Este es el panorama actual; a partir de aquí solo te aviso si mejora.",
    "digest": "Resumen diario.",
    "heartbeat": "Sin novedades: el precio no ha mejorado lo suficiente para avisarte.\n"
                 "Te escribo de todos modos para que sepas que el agente sigue vivo.",
}


def body(reason, offers, state, search, threshold=None, history_path=None):
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
    lines.append(f"Ruta: {search['origin']} → {search['destination']} · Solo vuelos directos")
    if best.get("checked_bag"):
        lines.append("Incluye 1 maleta documentada de 23 kg (filtro aplicado en la búsqueda)")
    lines.append(f"Ida {search['departure_date']} · Regreso {search['return_date']} · {search.get('adults',1)} adulto(s)")
    lines.append("")
    lines.append("TOP 5 OPCIONES DIRECTAS (precio = total viaje redondo por persona)")
    lines.append("-" * 60)
    for i, o in enumerate(offers[:5], 1):
        lines.append(f"{i}. {money(o['price'], o['currency'])} — {o['airline']}  [{o['source']}]")
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
    lines.append(f"Revisado: {dt.datetime.now(dt.timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M')}")

    text = "\n".join(lines)
    html = (
        "<div style=\"font-family:-apple-system,Segoe UI,sans-serif;max-width:640px\">"
        f"<h2 style=\"margin:0 0 4px\">{money(best['price'], best['currency'])}"
        f"<span style=\"font-weight:400;font-size:15px;color:#555\"> · {best['airline']}</span></h2>"
        f"<p style=\"color:#555;margin:0 0 16px\">{search['origin']} → {search['destination']} · directo · "
        f"{search['departure_date']} → {search['return_date']}</p>"
        "<pre style=\"background:#f6f6f6;padding:14px;border-radius:8px;"
        "white-space:pre-wrap;font-size:13px\">" + text + "</pre></div>"
    )
    return text, html
