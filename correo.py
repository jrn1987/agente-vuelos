"""Armado del correo en HTML, legible y ordenado por categoría.

El orden sigue la prioridad real de decisión:
  1. Directo con maleta (un solo boleto)
  2. Multi-aerolínea directo (ida y vuelta directas, pero en dos boletos)
  3. Con escala, nunca más de las horas permitidas, ni en la ida ni en la vuelta

Se escribe con tablas y estilos en línea porque Gmail y Outlook ignoran el CSS
de <style> y no soportan flexbox ni grid.
"""
import datetime as dt
import re

import escalas

AZUL = "#1b4f91"
TINTA = "#1a1a1a"
GRIS = "#5b6670"
BORDE = "#e1e5ea"
FONDO = "#f4f6f8"
VERDE = "#0f7a3d"
AMBAR = "#8a5a00"
ROJO = "#b3261e"
FUENTE = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def money(v, cur="MXN"):
    return f"${v:,.0f} {cur}"


def _hhmm(iso):
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return d.strftime("%d/%m %H:%M")
    except Exception:
        return str(iso)


def _dur(d):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", d or "")
    if not m:
        return d or ""
    return f"{m.group(1) or 0}h {int(m.group(2) or 0):02d}m"


def _esc(t):
    return (
        str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def partir(offer, destino):
    """Separa los tramos en ida y vuelta, para medir cada escala por dirección."""
    legs = offer.get("legs") or []
    corte = None
    for i, l in enumerate(legs):
        if l.get("to") == destino:
            corte = i + 1
            break
    if corte is None:
        corte = max(1, len(legs) // 2)
    return legs[:corte], legs[corte:]


def clasificar(offers):
    directos, multi, con_escala = [], [], []
    for o in offers:
        if o.get("stops"):
            con_escala.append(o)
        elif o.get("separate_tickets"):
            multi.append(o)
        else:
            directos.append(o)
    k = lambda x: x["price"]
    return sorted(directos, key=k), sorted(multi, key=k), sorted(con_escala, key=k)


def _chip(texto, color=GRIS, fondo="#ffffff"):
    return (
        f'<span style="display:inline-block;padding:2px 8px;margin:0 4px 4px 0;'
        f'border:1px solid {color};border-radius:10px;font-size:11px;line-height:16px;'
        f'color:{color};background:{fondo};white-space:nowrap">{_esc(texto)}</span>'
    )


def _tramos_html(legs, horas_max):
    filas = []
    paradas = escalas.de_tramos(legs)
    paradas_por_salida = {}
    for i, (aeropuerto, minutos) in enumerate(paradas):
        paradas_por_salida[i] = (aeropuerto, minutos)
    for i, l in enumerate(legs):
        filas.append(
            f'<tr><td style="padding:3px 0;font-size:13px;color:{TINTA};white-space:nowrap">'
            f'<strong>{_esc(l["from"])} → {_esc(l["to"])}</strong></td>'
            f'<td style="padding:3px 8px;font-size:13px;color:{GRIS}">'
            f'{_esc(_hhmm(l["depart"]))} → {_esc(_hhmm(l["arrive"]))}</td>'
            f'<td style="padding:3px 0;font-size:12px;color:{GRIS};text-align:right;'
            f'white-space:nowrap">{_esc(_dur(l.get("duration")))}</td></tr>'
        )
        if i in paradas_por_salida:
            aeropuerto, minutos = paradas_por_salida[i]
            excede = horas_max and minutos > horas_max * 60
            color = ROJO if excede else AMBAR
            filas.append(
                f'<tr><td colspan="3" style="padding:2px 0 4px">'
                f'{_chip(f"escala en {aeropuerto}: {escalas.formato(minutos)}", color, "#fffdf5")}'
                f"</td></tr>"
            )
    return "".join(filas)


def _botones(offer):
    ligas = offer.get("links") or (
        [("Ver esta oferta", offer["link"])] if offer.get("link") else []
    )
    if not ligas:
        return ""
    botones = "".join(
        f'<a href="{_esc(url)}" style="display:inline-block;margin:0 8px 6px 0;'
        f'padding:9px 16px;background:{AZUL};color:#ffffff;text-decoration:none;'
        f'border-radius:6px;font-size:13px;font-weight:600">{_esc(txt)} &rarr;</a>'
        for txt, url in ligas
    )
    return f'<div style="margin-top:12px">{botones}</div>'


def tarjeta(offer, destino, horas_max, etiqueta=None, destacada=False):
    ida, vuelta = partir(offer, destino)
    borde = AZUL if destacada else BORDE
    grosor = "2px" if destacada else "1px"
    chips = []
    if offer.get("checked_bag"):
        chips.append(_chip("maleta 23 kg incluida", VERDE, "#f3fbf6"))
    chips.append(_chip(offer.get("source", ""), GRIS))
    if offer.get("separate_tickets"):
        chips.append(_chip("BOLETOS SEPARADOS", ROJO, "#fdf3f2"))

    aviso = ""
    if offer.get("separate_tickets"):
        aviso = (
            f'<div style="margin-top:10px;padding:10px 12px;background:#fdf3f2;'
            f'border-left:3px solid {ROJO};font-size:12px;line-height:18px;color:{TINTA}">'
            "<strong>Son dos boletos distintos.</strong> En la conexión recoges la maleta y "
            "la vuelves a documentar, y pasas migración. Si el primer vuelo se retrasa, "
            "nadie te reacomoda en el siguiente: pierdes ese boleto."
            "</div>"
        )
    elif offer.get("note") and "MALETA NO INCLUIDA" in str(offer.get("note")):
        aviso = (
            f'<div style="margin-top:10px;padding:10px 12px;background:#fffdf5;'
            f'border-left:3px solid {AMBAR};font-size:12px;line-height:18px;color:{TINTA}">'
            f'{_esc(offer["note"])}</div>'
        )

    secciones = ""
    for titulo, legs in (("IDA", ida), ("VUELTA", vuelta)):
        if not legs:
            continue
        secciones += (
            f'<tr><td style="padding:8px 0 2px;font-size:10px;letter-spacing:.8px;'
            f'color:{GRIS};font-weight:700">{titulo}</td></tr>'
            f'<tr><td><table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
            f"{_tramos_html(legs, horas_max)}</table></td></tr>"
        )

    enc = (
        f'<div style="font-size:11px;font-weight:700;letter-spacing:.6px;color:{AZUL};'
        f'margin-bottom:6px">{_esc(etiqueta)}</div>'
        if etiqueta
        else ""
    )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="margin:0 0 14px;background:#ffffff;border:{grosor} solid {borde};'
        f'border-radius:10px"><tr><td style="padding:14px 16px">{enc}'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>'
        f'<td style="font-size:24px;font-weight:700;color:{TINTA};line-height:28px">'
        f'{money(offer["price"], offer["currency"])}</td>'
        f'<td style="text-align:right;font-size:14px;color:{GRIS}">'
        f'{_esc(offer.get("airline", ""))}</td></tr></table>'
        f'<div style="margin:8px 0 2px">{"".join(chips)}</div>'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{secciones}</table>{aviso}{_botones(offer)}</td></tr></table>"
    )


def _seccion(titulo, subtitulo, cuerpo):
    return (
        f'<tr><td style="padding:18px 0 8px">'
        f'<div style="font-size:15px;font-weight:700;color:{TINTA}">{_esc(titulo)}</div>'
        f'<div style="font-size:12px;color:{GRIS};margin-top:2px">{_esc(subtitulo)}</div>'
        f"</td></tr><tr><td>{cuerpo}</td></tr>"
    )


def _vacio(texto):
    return (
        f'<div style="padding:12px 14px;background:#ffffff;border:1px dashed {BORDE};'
        f'border-radius:10px;font-size:13px;color:{GRIS}">{_esc(texto)}</div>'
    )


def construir(reason, offers, search, threshold, encabezado, bloques_texto):
    """Devuelve el HTML del correo. bloques_texto: [(título, texto)] al final."""
    destino = search["destination"]
    horas = search.get("max_layover_hours")
    directos, multi, con_escala = clasificar(offers)
    best = min(offers, key=lambda o: o["price"])
    # El protagonista del correo es el directo con maleta; el resto va después.
    principal = next((o for o in directos if o.get("checked_bag")), None) or (
        directos[0] if directos else best
    )

    titulares = {
        "jackpot": ("🚨 Vale la pena: está debajo de tu objetivo", ROJO),
        "new_low": ("🔻 Nuevo mínimo desde que vigilo esta ruta", VERDE),
        "drop": ("🔻 Bajó el precio", VERDE),
        "drop_directo": ("🔻 Bajó el vuelo directo", VERDE),
        "at_reference": ("➡️ Sigue en el precio de referencia", AZUL),
        "first_run": ("Primera búsqueda: así está el panorama", AZUL),
        "digest": ("Resumen del día", AZUL),
        "prueba": ("🧪 Correo de prueba, con datos reales", AZUL),
        "heartbeat": ("✅ Sigo vigilando, sin novedades", GRIS),
    }
    titulo, color = titulares.get(reason, ("Actualización de precios", AZUL))

    diff = ""
    if threshold:
        delta = principal["price"] - threshold
        diff = (
            f"{money(abs(delta), best['currency'])} debajo de tu objetivo"
            if delta < 0
            else f"faltan {money(delta, best['currency'])} para tu objetivo"
        )

    partes = [
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="background:{FONDO};padding:0;margin:0"><tr><td align="center" '
        f'style="padding:16px 10px"><table width="600" cellpadding="0" cellspacing="0" '
        f'role="presentation" style="width:100%;max-width:600px;font-family:{FUENTE}">'
        # cabecera
        f'<tr><td style="padding:16px 18px;background:{AZUL};border-radius:10px">'
        f'<div style="font-size:11px;letter-spacing:1px;color:#c7d7ee;font-weight:700">'
        f'{_esc(search["origin"])} → {_esc(search["destination"])} · '
        f'{_esc(search["departure_date"])} al {_esc(search["return_date"])}</div>'
        f'<div style="font-size:11px;color:#9fbce4;margin-top:10px;font-weight:700;'
        f'letter-spacing:.6px">DIRECTO CON MALETA</div>'
        f'<div style="font-size:30px;font-weight:700;color:#ffffff;margin-top:2px;'
        f'line-height:34px">{money(principal["price"], principal["currency"])}'
        f'<span style="font-size:14px;font-weight:400;color:#dbe6f5"> · '
        f'{_esc(principal.get("airline", ""))}</span></div>'
        f'<div style="font-size:13px;color:#dbe6f5;margin-top:6px">{_esc(titulo)}</div>'
        + (
            f'<div style="font-size:12px;color:#c7d7ee;margin-top:6px">{_esc(diff)}</div>'
            if diff
            else ""
        )
        + (
            f'<div style="margin-top:12px;padding-top:10px;border-top:1px solid #3d6aa8;'
            f'font-size:12px;color:#dbe6f5">La más barata de todas es '
            f'<strong style="color:#ffffff">{money(best["price"], best["currency"])}</strong> '
            f'con {_esc(best.get("airline", ""))}, '
            + (
                f'con {best["stops"]} escala.'
                if best.get("stops")
                else "directa."
            )
            + " Está abajo, en su sección.</div>"
            if best is not principal
            else ""
        )
        + "</td></tr>",
    ]

    # 1. directo con maleta
    cuerpo = (
        "".join(
            tarjeta(o, destino, horas, destacada=(i == 0 and o is best))
            for i, o in enumerate(directos[:2])
        )
        or _vacio("Ninguna fuente devolvió vuelos directos en esta revisión.")
    )
    partes.append(_seccion("1. Directo con maleta", "Un solo boleto, sin conexiones.", cuerpo))

    # 2. multi-aerolínea directo
    cuerpo = (
        "".join(tarjeta(o, destino, horas) for o in multi[:2])
        or _vacio(
            "No encontré combinación de dos directos que convenga: hoy sale más caro "
            "que comprar ida y vuelta juntas."
        )
    )
    partes.append(
        _seccion(
            "2. Multi-aerolínea directo",
            "Ida y vuelta directas, pero compradas por separado.",
            cuerpo,
        )
    )

    # 3. con escala
    limite = f"Ninguna escala pasa de {horas} horas, ni en la ida ni en la vuelta."
    cuerpo = (
        "".join(
            tarjeta(o, destino, horas, destacada=(o is best)) for o in con_escala[:3]
        )
        or _vacio("No hubo itinerarios con escala dentro del límite de horas.")
    )
    partes.append(_seccion("3. Con escala", limite, cuerpo))

    # bloques de texto (tendencia, meses sin intereses)
    for titulo_bloque, texto in bloques_texto:
        partes.append(
            f'<tr><td style="padding:18px 0 8px">'
            f'<div style="font-size:15px;font-weight:700;color:{TINTA}">'
            f"{_esc(titulo_bloque)}</div></td></tr>"
            f'<tr><td style="background:#ffffff;border:1px solid {BORDE};border-radius:10px;'
            f'padding:14px 16px"><div style="font-size:12px;line-height:19px;color:{TINTA};'
            f'white-space:pre-wrap;word-break:break-word">{_esc(texto)}</div></td></tr>'
        )

    partes.append(
        f'<tr><td style="padding:18px 2px 6px;font-size:11px;color:{GRIS};line-height:17px">'
        f'Revisado el {dt.datetime.now().strftime("%d/%m/%Y a las %H:%M")} · '
        f"{len(offers)} opciones comparadas, todas con el precio final con maleta.<br>"
        "Los precios y la disponibilidad cambian en minutos: confirma siempre en el "
        "sitio antes de pagar."
        "</td></tr></table></td></tr></table>"
    )
    return "".join(partes)
