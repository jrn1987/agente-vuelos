"""Cálculo y formato de escalas.

La resta de horarios es válida porque la llegada de un vuelo y la salida del
siguiente ocurren en el MISMO aeropuerto, así que están en la misma zona horaria.
"""
import datetime as dt


def _parse(iso):
    try:
        return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def minutos(llegada_iso, salida_iso):
    a, b = _parse(llegada_iso), _parse(salida_iso)
    if not a or not b:
        return None
    return max(0, int((b - a).total_seconds() // 60))


def de_tramos(tramos):
    """Escalas de una serie de vuelos consecutivos: [(aeropuerto, minutos), ...]"""
    out = []
    for previo, siguiente in zip(tramos, tramos[1:]):
        m = minutos(previo.get("arrive"), siguiente.get("depart"))
        if m is not None:
            out.append((previo.get("to"), m))
    return out


def formato(m):
    if m is None:
        return "?"
    return f"{m // 60}h {m % 60:02d}m"


def cumple(escalas, max_horas):
    """True si todas las escalas caben en el límite (y si no hay, también)."""
    if not escalas:
        return True
    if not max_horas:
        return True
    return all(m <= max_horas * 60 for _, m in escalas)
