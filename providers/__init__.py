from . import (
    booking,
    booking_intl,
    googleflights,
    googleflights_split,
    kiwi,
    kiwi_intl,
    serpapi,
)

PROVIDERS = {
    "booking": booking.search,
    "booking_intl": booking_intl.search,
    "googleflights": googleflights.search,
    "googleflights_split": googleflights_split.search,
    "kiwi": kiwi.search,
    "kiwi_intl": kiwi_intl.search,
    "serpapi": serpapi.search,
}


def get(name):
    """Acepta "kiwi" y también "kiwi:es" para varias variantes de la misma fuente."""
    base = name.split(":", 1)[0]
    if base not in PROVIDERS:
        raise ValueError(f"Proveedor desconocido: {base}. Opciones: {list(PROVIDERS)}")
    return PROVIDERS[base]
