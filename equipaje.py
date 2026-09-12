"""Costo de la maleta documentada cuando la fuente no lo dice.

Orden de preferencia, de más confiable a menos:
  1. El precio real que cotiza el vendedor (Booking lo expone). Se usa tal cual.
  2. Esta tabla, como estimación, SIEMPRE avisando que se compra por separado.

Las tarifas de equipaje cambian por temporada, canal de compra y momento
(comprarla al reservar es más barato que en el aeropuerto), así que aquí se
guarda un rango real y se usa el extremo bajo, marcándolo como estimación.
"""
import fx

VERIFICADO = "12 de septiembre de 2026"

# Vuelos intercontinentales México–Europa. Precios POR TRAYECTO, en euros.
TARIFAS = {
    "iberia": {
        "desde_eur": 50,
        "hasta_eur": 120,
        "nota": "Primera maleta de 23 kg en tarifa Basic de largo radio.",
        "fuente": "https://www.iberia.com/us/baggage/",
    },
    "aeromexico": {
        "desde_eur": 30,
        "hasta_eur": 240,
        "nota": "Desde septiembre de 2025 la tarifa Básica a Europa ya NO incluye "
                "maleta documentada: solo 2 piezas de mano de 10 kg en total.",
        "fuente": "https://www.aeromexico.com/es-mx/informacion-de-viaje/equipaje",
    },
    "air europa": {
        "desde_eur": 40,
        "hasta_eur": 150,
        "nota": "Tarifa Light sin maleta documentada incluida.",
        "fuente": "https://www.aireuropa.com/mx/es/aea/informacion-y-servicios/equipaje.html",
    },
}


def _clave(airline):
    a = (airline or "").lower()
    for k in TARIFAS:
        if k.split()[0] in a:
            return k
    return None


def estimar(airline, trayectos=2):
    """Estimación conservadora en pesos del costo de documentar una maleta.

    Devuelve (monto_mxn, explicación) o (None, motivo) si no hay dato.
    """
    k = _clave(airline)
    if not k:
        return None, f"No tengo tarifa de equipaje registrada para {airline}."
    t = TARIFAS[k]
    try:
        bajo = fx.to_mxn(t["desde_eur"] * trayectos, "EUR")
        alto = fx.to_mxn(t["hasta_eur"] * trayectos, "EUR")
    except Exception:
        return None, "No pude convertir el costo de la maleta a pesos."
    return bajo, (
        f"MALETA NO INCLUIDA: sumé ${bajo:,.0f} MXN estimados "
        f"(desde {t['desde_eur']} EUR por trayecto, ida y vuelta). "
        f"Puede llegar a ${alto:,.0f} MXN según temporada y momento de compra. "
        f"SE COMPRA POR SEPARADO al reservar. {t['nota']} "
        f"Verificado el {VERIFICADO}: {t['fuente']}"
    )
