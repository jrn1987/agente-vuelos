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
    if offer.get("cached"):
        chips.append(_chip("precio de caché: confírmalo", AMBAR, "#fffdf5"))
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


def _kpi(etiqueta, valor, pie, color=TINTA):
    return (
        f'<td width="33%" style="padding:12px 10px;background:#ffffff;'
        f'border:1px solid {BORDE};border-radius:10px;vertical-align:top">'
        f'<div style="font-size:10px;letter-spacing:.7px;color:{GRIS};font-weight:700">'
        f"{_esc(etiqueta)}</div>"
        f'<div style="font-size:19px;font-weight:700;color:{color};margin-top:4px;'
        f'line-height:23px">{_esc(valor)}</div>'
        f'<div style="font-size:11px;color:{GRIS};margin-top:3px;line-height:15px">'
        f"{_esc(pie)}</div></td>"
    )


def _kpis(principal, best, threshold):
    celdas = [
        _kpi(
            "DIRECTO CON MALETA",
            money(principal["price"], principal["currency"]),
            principal.get("airline", ""),
        ),
        _kpi(
            "LA MÁS BARATA",
            money(best["price"], best["currency"]),
            (f"{best['stops']} escala · " if best.get("stops") else "directa · ")
            + (best.get("airline", "") or ""),
            VERDE if best is not principal else TINTA,
        ),
    ]
    if threshold:
        delta = best["price"] - threshold
        celdas.append(
            _kpi(
                "TU OBJETIVO",
                money(threshold, best["currency"]),
                f"{money(abs(delta), best['currency'])} "
                + ("por debajo ✅" if delta < 0 else "por encima"),
                VERDE if delta < 0 else AMBAR,
            )
        )
    separador = '<td width="8" style="font-size:0;line-height:0">&nbsp;</td>'
    return (
        f'<tr><td style="padding:12px 0 0"><table width="100%" cellpadding="0" '
        f'cellspacing="0" role="presentation"><tr>'
        + separador.join(celdas)
        + "</tr></table></td></tr>"
    )


def _barra(ancho_pct, color):
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f'<tr><td style="background:{BORDE};border-radius:4px;font-size:0;line-height:0">'
        f'<table width="{max(2, min(100, ancho_pct)):.0f}%" cellpadding="0" '
        f'cellspacing="0" role="presentation"><tr>'
        f'<td style="background:{color};height:8px;border-radius:4px;font-size:0;'
        f'line-height:0">&nbsp;</td></tr></table></td></tr></table>'
    )


def plan_b_tabla(resultados, madrid_precio, currency="MXN"):
    """Comparativa de destinos alternativos, con barra proporcional al precio."""
    con_precio = [r for r in resultados if r.get("offer")]
    if not con_precio:
        return _vacio("No pude cotizar los destinos alternativos en esta revisión.")
    tope = max([r["offer"]["price"] for r in con_precio] + [madrid_precio or 0])

    filas = []
    for r in resultados:
        o = r.get("offer")
        if not o:
            filas.append(
                f'<tr><td style="padding:9px 0;font-size:13px;color:{GRIS}">'
                f'{_esc(r["name"])} <span style="font-size:11px">({_esc(r["code"])})</span></td>'
                f'<td colspan="2" style="padding:9px 0;font-size:12px;color:{GRIS}">'
                f'sin vuelos directos</td></tr>'
            )
            continue
        barato = madrid_precio and o["price"] < madrid_precio
        color = VERDE if barato else AZUL
        liga = (o.get("links") or [(None, o.get("link"))])[0][1]
        filas.append(
            f'<tr><td style="padding:9px 8px 9px 0;vertical-align:top">'
            f'<div style="font-size:13px;font-weight:600;color:{TINTA}">'
            f'{_esc(r["name"])}</div>'
            f'<div style="font-size:11px;color:{GRIS}">{_esc(o.get("airline",""))} · '
            f'{_esc(_dur(o["legs"][0].get("duration")))}</div></td>'
            f'<td style="padding:9px 8px;vertical-align:middle;width:45%">'
            f'{_barra(o["price"] / tope * 100 if tope else 0, color)}</td>'
            f'<td style="padding:9px 0;text-align:right;vertical-align:top;white-space:nowrap">'
            f'<div style="font-size:14px;font-weight:700;color:{color}">'
            f'{money(o["price"], o["currency"])}</div>'
            + (
                f'<a href="{_esc(liga)}" style="font-size:11px;color:{AZUL};'
                f'text-decoration:underline">ver vuelo</a>'
                if liga
                else ""
            )
            + "</td></tr>"
        )

    encabezado_madrid = ""
    if madrid_precio:
        encabezado_madrid = (
            f'<tr><td style="padding:9px 8px 9px 0;vertical-align:top">'
            f'<div style="font-size:13px;font-weight:700;color:{TINTA}">Madrid '
            f'<span style="font-size:11px;font-weight:400;color:{GRIS}">'
            f'(tu destino)</span></div></td>'
            f'<td style="padding:9px 8px;vertical-align:middle">'
            f'{_barra(100, TINTA)}</td>'
            f'<td style="padding:9px 0;text-align:right;white-space:nowrap">'
            f'<div style="font-size:14px;font-weight:700;color:{TINTA}">'
            f'{money(madrid_precio, currency)}</div></td></tr>'
        )

    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="background:#ffffff;border:1px solid {BORDE};border-radius:10px">'
        f'<tr><td style="padding:6px 16px 10px">'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{encabezado_madrid}{''.join(filas)}</table></td></tr></table>"
    )


def tendencia_barras(serie, currency="MXN"):
    """Precio mínimo por día, en barras. Sin gráficas externas: los clientes de
    correo bloquean imágenes remotas y el SVG no se ve en Outlook."""
    if len(serie) < 2:
        return ""
    precios = [p for _, p in serie]
    minimo, maximo = min(precios), max(precios)
    rango = maximo - minimo or 1
    filas = []
    for dia, precio in serie:
        # La barra mide la posición dentro del rango, no el valor absoluto, para
        # que las diferencias se noten aunque sean pequeñas.
        pct = 15 + (precio - minimo) / rango * 85
        color = VERDE if precio == minimo else (ROJO if precio == maximo else AZUL)
        filas.append(
            f'<tr><td style="padding:3px 8px 3px 0;font-size:11px;color:{GRIS};'
            f'white-space:nowrap">{_esc(dia[5:])}</td>'
            f'<td style="padding:3px 8px;width:60%">{_barra(pct, color)}</td>'
            f'<td style="padding:3px 0;text-align:right;font-size:11px;'
            f'color:{TINTA};white-space:nowrap">{money(precio, currency)}</td></tr>'
        )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
        f'style="background:#ffffff;border:1px solid {BORDE};border-radius:10px">'
        f'<tr><td style="padding:12px 16px">'
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation">'
        f"{''.join(filas)}</table>"
        f'<div style="margin-top:8px;font-size:11px;color:{GRIS}">'
        f'Verde = el más bajo del periodo · Rojo = el más alto</div>'
        f"</td></tr></table>"
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


def construir(
    reason,
    offers,
    search,
    threshold,
    encabezado,
    bloques_texto,
    plan_b=None,
    serie=None,
):
    """Devuelve el HTML del correo.

    bloques_texto: [(título, texto)] que van al final.
    plan_b: resultados de plan_b.buscar(). serie: [(día, precio mínimo)].
    """
    destino = search["destination"]
    horas = search.get("max_layover_hours")
    directos, multi, con_escala = clasificar(offers)
    best = min(offers, key=lambda o: o["price"])
    # El protagonista del correo es el directo con maleta; el resto va después.
    # Un precio de caché no encabeza el correo si hay uno en vivo: sería anunciar
    # como firme algo que todavía hay que confirmar.
    principal = (
        next((o for o in directos if o.get("checked_bag") and not o.get("cached")), None)
        or next((o for o in directos if not o.get("cached")), None)
        or (directos[0] if directos else best)
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

    partes.append(_kpis(principal, best, threshold))

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

    if serie and len(serie) >= 2:
        partes.append(
            _seccion(
                "Cómo se ha movido el precio",
                "Precio más bajo de cada día, desde que vigilo esta ruta.",
                tendencia_barras(serie, best["currency"]),
            )
        )

    if plan_b:
        partes.append(
            _seccion(
                "Plan B: otros destinos, mismas fechas",
                "Solo vuelos directos con maleta, 22 dic al 2 ene. Por si Madrid no baja.",
                plan_b_tabla(plan_b, principal["price"], principal["currency"]),
            )
        )

    # bloques de texto (meses sin intereses)
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
