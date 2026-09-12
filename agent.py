#!/usr/bin/env python3
"""Agente 24/7 de vuelos directos CDMX (MEX) → Madrid (MAD).

Uso:
    python3 agent.py --once      una sola búsqueda (para probar o para cron/launchd)
    python3 agent.py --loop      corre en bucle continuo según interval_minutes
    python3 agent.py --test-mail envía un correo de prueba
"""
import argparse
import datetime as dt
from zoneinfo import ZoneInfo
import json
import os
import sys
import time
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import notifier  # noqa: E402
import providers  # noqa: E402
import render  # noqa: E402

CONFIG = os.path.join(BASE, "config.json")
# El estado vive en data/ y se guarda en el repo desde GitHub Actions. Para probar
# en local sin pisar el estado de producción:  export AGENT_DATA_DIR=/tmp/prueba
DATA = os.environ.get("AGENT_DATA_DIR") or os.path.join(BASE, "data")
STATE = os.path.join(DATA, "state.json")
HISTORY = os.path.join(DATA, "history.jsonl")
LOG = os.path.join(BASE, "logs", "agent.log")

# Todo se razona en hora de CDMX. El servidor de GitHub corre en UTC, y con la
# hora del servidor el "resumen de las 9" caía a las 3 de la mañana de aquí.
TZ = ZoneInfo("America/Mexico_City")


def now():
    return dt.datetime.now(TZ)


def log(msg):
    line = f"[{now():%Y-%m-%d %H:%M} CDMX] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_config():
    if not os.path.exists(CONFIG):
        sys.exit(
            "Falta config.json. Copia config.example.json a config.json y "
            "llena tus credenciales:\n  cp config.example.json config.json"
        )
    with open(CONFIG) as f:
        raw = f.read()

    def expand(value):
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            name = value[2:-1]
            got = os.environ.get(name)
            if not got:
                sys.exit(
                    f"Falta la variable de entorno {name}. Local:  export {name}='...'\n"
                    f"En GitHub Actions: guárdala como repository secret."
                )
            return got
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    cfg = expand(json.loads(raw))
    to = cfg["email"].get("to_addrs")
    if isinstance(to, str):
        cfg["email"]["to_addrs"] = [x.strip() for x in to.split(",") if x.strip()]
    return cfg


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f, indent=2)


def decide(best_price, state, alerts):
    """Devuelve el motivo de la alerta, o None si no hay que enviar correo."""
    today = now().date().isoformat()
    if state.get("emails_date") != today:
        state["emails_date"] = today
        state["emails_sent"] = 0
        state["digest_sent"] = False
        state["prices_notified"] = []

    if state.get("emails_sent", 0) >= alerts.get("max_emails_per_day", 8):
        return None

    prev = state.get("last_best_price")
    low = state.get("all_time_low")
    threshold = alerts.get("price_threshold", 0)

    # Alerta mayor: debajo del objetivo. Se repite solo si mejora aún más.
    if best_price < threshold:
        seen = state.get("jackpot_price")
        if seen is None or best_price < seen:
            return "jackpot"

    if prev is None:
        return "first_run"

    # Precios de los que ya te avisé hoy, para no repetir el mismo correo.
    avisados = state.setdefault("prices_notified", [])

    # Cualquier bajada respecto a la revisión anterior, por mínima que sea.
    drop_pct = alerts.get("drop_pct", 0)
    if best_price < prev and (prev - best_price) / prev * 100 >= drop_pct:
        return "drop"

    margin = alerts.get("new_low_min_pct", 0)
    if (
        alerts.get("notify_on_new_low", True)
        and low is not None
        and best_price <= low * (1 - margin / 100)
        and best_price not in avisados
    ):
        return "new_low"

    # Sigue en el precio original (o por debajo) y hoy no te lo he dicho.
    ref = alerts.get("reference_price")
    if ref and best_price <= ref and best_price not in avisados:
        return "at_reference"

    # Resumen diario: en la PRIMERA corrida del día que ya pasó la hora fijada.
    # Antes exigía caer justo dentro de esa hora, y como GitHub se salta
    # corridas, había días en que el resumen simplemente nunca salía.
    hour = alerts.get("daily_digest_hour")
    if hour is not None and now().hour >= int(hour) and not state.get("digest_sent"):
        return "digest"

    # Latido: nunca dejarte más de N horas sin noticias, aunque no pase nada.
    # Sin esto, el silencio es ambiguo: no sabes si no hay novedades o si el
    # agente se murió.
    silence = alerts.get("max_silence_hours")
    if silence:
        last = state.get("last_email_ts")
        if not last:
            # Estado viejo sin esta marca: arrancamos el reloj desde ahora para
            # que el latido empiece a contar en vez de quedarse dormido.
            state["last_email_ts"] = now().isoformat(timespec="seconds")
        else:
            gap = (now() - dt.datetime.fromisoformat(last)).total_seconds() / 3600
            if gap >= float(silence):
                return "heartbeat"
    return None


def gather(cfg):
    """Consulta todas las fuentes configuradas y junta los resultados.

    Si una fuente falla, se sigue con las demás: el agente solo se da por vencido
    cuando ninguna responde.
    """
    search_cfg = cfg["search"]
    names = cfg["provider"].get("names") or [cfg["provider"]["name"]]
    offers, failures = [], []
    for name in names:
        try:
            got = providers.get(name)(search_cfg, cfg["provider"].get(name, {}))
            log(f"  {name}: {len(got)} opciones"
                + (f" · desde {render.money(got[0]['price'], got[0]['currency'])}" if got else ""))
            offers += got
        except Exception as exc:
            failures.append(f"{name} ({type(exc).__name__}: {exc})")
            log(f"  {name}: FALLÓ — {type(exc).__name__}: {exc}")

    # Un mismo vuelo puede venir de varias fuentes: nos quedamos con el más barato.
    best_by_flight = {}
    for o in offers:
        key = (o["legs"][0]["depart"], o["airline"])
        if key not in best_by_flight or o["price"] < best_by_flight[key]["price"]:
            best_by_flight[key] = o
    merged = sorted(best_by_flight.values(), key=lambda o: o["price"])
    return merged, failures


def run_once(cfg):
    search_cfg = cfg["search"]
    offers, failures = gather(cfg)

    if not offers:
        log("Ninguna fuente devolvió vuelos directos.")
        state = load_state()
        today = now().date().isoformat()
        if failures and state.get("failure_alert_date") != today:
            notifier.send(
                cfg["email"],
                "⚠️ El agente de vuelos no pudo buscar",
                "Ninguna fuente respondió en esta revisión:\n\n  - "
                + "\n  - ".join(failures)
                + "\n\nSi se repite, probablemente cambió el formato de la fuente y "
                  "hay que actualizar el agente. Revisa los logs de GitHub Actions.",
            )
            state["failure_alert_date"] = today
            save_state(state)
        return

    best = offers[0]
    state = load_state()
    log(f"TOTAL {len(offers)} opciones directas · mejor "
        f"{render.money(best['price'], best['currency'])} ({best['airline']}, vía {best['source']})")

    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "a") as f:
        f.write(json.dumps({
            "ts": now().isoformat(timespec="seconds"),
            "price": best["price"],
            "currency": best["currency"],
            "airline": best["airline"],
            "source": best["source"],
            "count": len(offers),
        }) + "\n")

    reason = decide(best["price"], state, cfg["alerts"])
    if reason:
        text, html = render.body(
            reason, offers, state, search_cfg, cfg["alerts"].get("price_threshold")
        )
        notifier.send(cfg["email"], render.subject(reason, best, search_cfg), text, html)
        state["emails_sent"] = state.get("emails_sent", 0) + 1
        state["last_email_ts"] = now().isoformat(timespec="seconds")
        state.setdefault("prices_notified", []).append(best["price"])
        if reason == "digest":
            state["digest_sent"] = True
        if reason == "jackpot":
            state["jackpot_price"] = best["price"]
        log(f"Correo enviado ({reason}) a {', '.join(cfg['email']['to_addrs'])}")
    else:
        log("Sin cambios relevantes; no se envía correo.")

    if best["price"] >= cfg["alerts"].get("price_threshold", 0):
        state.pop("jackpot_price", None)
    state["last_best_price"] = best["price"]
    state["all_time_low"] = min(best["price"], state.get("all_time_low", best["price"]))
    state["last_check"] = now().isoformat(timespec="seconds")
    save_state(state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--test-mail", action="store_true")
    args = ap.parse_args()
    cfg = load_config()

    if args.test_mail:
        notifier.send(
            cfg["email"],
            "✈️ Prueba del agente de vuelos",
            "Si lees esto, el envío de correo funciona correctamente.",
        )
        log("Correo de prueba enviado.")
        return

    if args.loop:
        interval = int(cfg["run"].get("interval_minutes", 60)) * 60
        log(f"Agente en bucle, revisión cada {interval // 60} min. Ctrl+C para detener.")
        while True:
            try:
                run_once(cfg)
            except Exception:
                log("ERROR:\n" + traceback.format_exc())
            time.sleep(interval)
    else:
        run_once(cfg)


if __name__ == "__main__":
    main()
