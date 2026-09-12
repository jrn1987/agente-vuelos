"""Meses sin intereses con BBVA México y American Express México.

Las promociones bancarias rotan seguido, así que aquí se guarda lo verificado
con fecha y liga oficial, y el correo siempre te manda a confirmar al pagar.
Actualiza VERIFICADO y los textos cuando cambien las campañas.
"""

VERIFICADO = "11 de septiembre de 2026"

# Regla clave: los MSI los da QUIEN TE COBRA, no la aerolínea que vuelas.
# Comprar en el sitio de la aerolínea casi siempre califica; comprar en una
# agencia en línea del extranjero (Kiwi, eDreams, Trip.com) casi nunca.
POR_AEROLINEA = {
    "iberia": {
        "amex": "Hasta 9 Meses sin Intereses comprando en iberia.com México.",
        "bbva": "3 o 6 MSI según campaña vigente, compra mínima $3,000 MXN en el sitio nacional.",
        "extra": "BBVA transfiere Puntos a Avios de Iberia Club (2.6 Puntos BBVA = 1 Avio, "
                 "mínimo 130 Puntos): sirve para bajar el costo o subir de clase.",
    },
    "aeromexico": {
        "amex": "Hasta 9 meses en PLAN DE PAGOS DIFERIDOS. Ojo: diferido NO es lo mismo "
                "que sin intereses; confirma si genera intereses antes de aceptar.",
        "bbva": "3 o 6 MSI según campaña vigente, compra mínima $3,000 MXN en aeromexico.com "
                "o tiendas de viaje Aeroméxico.",
        "extra": "Aeroméxico suele ofrecer hasta 12 MSI en campañas puntuales (Hot Sale, Buen Fin).",
    },
    "air europa": {
        "amex": "Sin promoción listada actualmente; pregunta al pagar.",
        "bbva": "Sin promoción listada actualmente; pregunta al pagar.",
        "extra": "",
    },
}

LIGAS = [
    ("Promociones Amex México en aerolíneas",
     "https://www.americanexpress.com/es-mx/beneficios/promociones/viajes/aerolineas.html"),
    ("Promociones BBVA México con tarjeta de crédito",
     "https://www.bbva.mx/personas/productos/tarjetas-de-credito/promociones.html"),
    ("Puntos BBVA → Avios de Iberia Club",
     "https://www.bbva.mx/personas/productos/tarjetas-de-credito/promociones/puntos-bbva/puntos-avios.html"),
]


def _clave(airline):
    a = (airline or "").lower()
    for k in POR_AEROLINEA:
        if k.split()[0] in a:
            return k
    return None


DIRECTO = {
    "iberia": "https://www.iberia.com/mx/",
    "aeromexico": "https://www.aeromexico.com/es-mx/booking/round-trip"
                  "?originCode={o}&destinationCode={d}&departureDate={ida}"
                  "&returnDate={vuelta}&adults={pax}",
    "air europa": "https://www.aireuropa.com/mx/es",
}


def liga_directa(airline, search):
    """Enlace al buscador de la propia aerolínea, que es donde aplican los MSI."""
    k = _clave(airline)
    if not k:
        return None
    return DIRECTO[k].format(
        o=search["origin"], d=search["destination"],
        ida=search["departure_date"], vuelta=search["return_date"],
        pax=search.get("adults", 1),
    )


def bloque(best, search=None):
    """Texto de MSI para la mejor oferta encontrada."""
    lines = ["MESES SIN INTERESES — BBVA y AMEX", "-" * 60]
    fuente_es_agencia = "kiwi" in (best.get("source", "").lower())
    k = _clave(best.get("airline"))

    if k:
        info = POR_AEROLINEA[k]
        lines.append(f"Volando {best['airline'].title()}:")
        lines.append(f"  • AMEX: {info['amex']}")
        lines.append(f"  • BBVA: {info['bbva']}")
        if info["extra"]:
            lines.append(f"  • {info['extra']}")
    else:
        lines.append("No tengo promociones registradas para esta aerolínea; pregunta al pagar.")

    lines.append("")
    if fuente_es_agencia:
        lines.append(
            "⚠️ OJO: esta tarifa la encontró una agencia en línea, y esas casi nunca\n"
            "   dan MSI con bancos mexicanos. Antes de comprar, checa el mismo vuelo\n"
            "   en el sitio de la aerolínea: si la diferencia es chica, los MSI pueden\n"
            "   convenirte más que ahorrarte unos pesos de contado."
        )
    else:
        lines.append(
            "Los MSI los da quien te cobra, no la aerolínea que vuelas: para que\n"
            "apliquen, compra en el sitio mexicano de la aerolínea, no en una agencia."
        )

    lines.append("")
    lines.append(
        "📅 El Buen Fin (mediados de noviembre) cae ANTES de tu viaje y es cuando\n"
        "   más MSI se ofrecen: si el precio no baja antes, conviene esperarlo."
    )
    if search:
        liga = liga_directa(best.get("airline"), search)
        if liga:
            lines.append("")
            lines.append(f"🔗 Comprar directo con la aerolínea (donde sí aplican los MSI):")
            lines.append(f"   {liga}")
    lines.append("")
    lines.append(f"Verificado el {VERIFICADO}. Las campañas cambian seguido, confirma aquí:")
    for nombre, url in LIGAS:
        lines.append(f"  - {nombre}: {url}")
    return "\n".join(lines)
