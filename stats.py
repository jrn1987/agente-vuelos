"""Lee el historial que el agente lleva guardando y responde: ¿compro o espero?

Ninguna fuente externa sabe cómo se ha movido ESTE vuelo desde que lo vigilas.
Esto convierte las revisiones acumuladas en una señal de compra.
"""
import json
import os


def _leer(path, dias=14):
    if not os.path.exists(path):
        return []
    precios = []
    with open(path) as f:
        for linea in f:
            try:
                precios.append(json.loads(linea))
            except Exception:
                continue
    return precios[-(dias * 48):]  # ~48 revisiones por día


def bloque(history_path, actual, currency="MXN"):
    datos = _leer(history_path)
    precios = [d["price"] for d in datos if d.get("price")]
    if len(precios) < 4:
        return (
            "TENDENCIA\n" + "-" * 60 + "\n"
            f"Apenas llevo {len(precios)} revisión(es) guardadas. En cuanto junte unos días "
            "podré decirte si el precio de hoy está barato o caro para esta ruta."
        )

    minimo, maximo = min(precios), max(precios)
    promedio = sum(precios) / len(precios)
    rango = maximo - minimo
    pct = 0 if rango == 0 else (actual - minimo) / rango * 100

    # Con un rango minúsculo, hablar de "alto" o "bajo" es ruido disfrazado de señal.
    if rango / promedio * 100 < 2:
        veredicto = (
            f"El precio ha estado prácticamente plano: solo ${rango:,.0f} {currency} "
            f"de diferencia entre el mínimo y el máximo ({rango / promedio * 100:.1f}%). "
            "Todavía no hay una señal real de compra."
        )
    elif pct <= 20:
        veredicto = "🟢 Está en la parte BAJA de todo lo que he visto. Buen momento."
    elif pct >= 80:
        veredicto = "🔴 Está en la parte ALTA de lo que he visto. Conviene esperar."
    else:
        veredicto = "🟡 Está en la zona media de lo observado."

    # Tendencia: últimas 6 revisiones contra las 6 anteriores.
    tendencia = ""
    if len(precios) >= 12:
        recientes = sum(precios[-6:]) / 6
        previas = sum(precios[-12:-6]) / 6
        delta = (recientes - previas) / previas * 100
        if delta <= -1:
            tendencia = f"Viene BAJANDO ({delta:+.1f}% en las últimas revisiones)."
        elif delta >= 1:
            tendencia = f"Viene SUBIENDO ({delta:+.1f}% en las últimas revisiones)."
        else:
            tendencia = "Se ha mantenido estable en las últimas revisiones."

    lines = [
        "TENDENCIA (según mi propio historial)",
        "-" * 60,
        veredicto,
    ]
    if tendencia:
        lines.append(tendencia)
    lines.append("")
    lines.append(f"  Mínimo visto:  ${minimo:,.0f} {currency}")
    lines.append(f"  Promedio:      ${promedio:,.0f} {currency}")
    lines.append(f"  Máximo visto:  ${maximo:,.0f} {currency}")
    lines.append(f"  Ahora:         ${actual:,.0f} {currency}"
                 + (f"  (percentil {pct:.0f} del rango)" if rango else ""))
    lines.append(f"  Revisiones acumuladas: {len(precios)}")
    return "\n".join(lines)
