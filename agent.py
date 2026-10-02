#!/usr/bin/env python3
"""Agente 24/7 de vuelos directos CDMX (MEX) → Madrid (MAD).

Uso:
    python3 agent.py --once      una sola búsqueda (para probar o para cron/launchd)
    python3 agent.py --loop      corre en bucle continuo según interval_minutes
    python3 agent.py --test-mail envía un correo de prueba
"""
import argparse
import concurrent.futures
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


def decide(best_price, state, alerts, direct_price=None):
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

    # El directo bajó, aunque el precio general no se haya movido. Importa porque
    # un directo más barato puede convenir aunque no sea la opción más baja.
    if direct_price is not None:
        previo_directo = state.get("last_direct_price")
        if previo_directo and direct_price < previo_directo:
            return "drop_directo"

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


def en_pausa(name, cfg, state):
    """Algunas fuentes bloquean si se les pregunta muy seguido (Booking responde
    429). Las tarifas no cambian cada 10 minutos, así que preguntar menos no
    pierde nada y evita que nos cierren la puerta."""
    ajustes = cfg["provider"].get(name) or {}

    def minutos_desde(registro):
        marca = (state.get(registro) or {}).get(name)
        if not marca:
            return None
        try:
            return (now() - dt.datetime.fromisoformat(marca)).total_seconds() / 60
        except Exception:
            return None

    # Tras un rechazo por ritmo, descansar es lo único que ayuda: insistir cada
    # 10 minutos es lo que mantenía a Booking bloqueándonos.
    tras_fallo = ajustes.get("cooldown_after_fail_minutes", 60)
    desde_fallo = minutos_desde("provider_last_fail")
    if tras_fallo and desde_fallo is not None and desde_fallo < tras_fallo:
        return f"descansando {tras_fallo - desde_fallo:.0f} min más tras un rechazo"

    minimos = ajustes.get("min_interval_minutes")
    desde_exito = minutos_desde("provider_last_ok")
    if minimos and desde_exito is not None and desde_exito < minimos:
        return f"se consulta cada {minimos} min"
    return False


def gather(cfg):
    """Consulta todas las fuentes configuradas y junta los resultados.

    Si una fuente falla, se sigue con las demás: el agente solo se da por vencido
    cuando ninguna responde.
    """
    search_cfg = cfg["search"]
    names = cfg["provider"].get("names") or [cfg["provider"]["name"]]
    # Tope de tiempo por fuente: una que se cuelgue no debe retrasar la revisión
    # completa (Kiwi, por ejemplo, tarda minutos cuando nos limita el ritmo).
    tope_global = cfg["provider"].get("timeout_seconds", 120)
    estado = load_state()
    exitos = dict(estado.get("provider_last_ok") or {})
    fallos = dict(estado.get("provider_last_fail") or {})
    offers, failures = [], []
    for name in names:
        motivo = en_pausa(name, cfg, estado)
        if motivo:
            log(f"  {name}: en pausa ({motivo})")
            continue
        # booking_intl consulta varios mercados con pausas, así que necesita más
        # margen que una fuente de una sola llamada.
        tope_seg = (cfg["provider"].get(name) or {}).get("timeout_seconds", tope_global)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                tarea = pool.submit(
                    providers.get(name), search_cfg, cfg["provider"].get(name, {})
                )
                try:
                    got = tarea.result(timeout=tope_seg)
                except concurrent.futures.TimeoutError:
                    failures.append(f"{name} (no respondió en {tope_seg}s)")
                    fallos[name] = now().isoformat(timespec="seconds")
                    log(f"  {name}: SE PASÓ DE TIEMPO ({tope_seg}s), se sigue sin ella")
                    pool.shutdown(wait=False, cancel_futures=True)
                    continue
                directos = sum(1 for o in got if not o.get("stops"))
            log(f"  {name}: {len(got)} opciones ({directos} directas)"
                + (f" · desde {render.money(got[0]['price'], got[0]['currency'])}" if got else ""))
            offers += got
            if got:
                exitos[name] = now().isoformat(timespec="seconds")
        except Exception as exc:
            failures.append(f"{name} ({type(exc).__name__}: {exc})")
            fallos[name] = now().isoformat(timespec="seconds")
            log(f"  {name}: FALLÓ — {type(exc).__name__}: {exc}")

    # Un mismo vuelo puede venir de varias fuentes: nos quedamos con el más barato.
    best_by_flight = {}
    for o in offers:
        key = (
            o["legs"][0]["depart"],
            o["airline"],
            len(o["legs"]),
            o["legs"][-1]["arrive"],
            o.get("separate_tickets", False),
        )
        if key not in best_by_flight or o["price"] < best_by_flight[key]["price"]:
            best_by_flight[key] = o
    merged = sorted(best_by_flight.values(), key=lambda o: o["price"])
    if exitos != (estado.get("provider_last_ok") or {}) or fallos != (
        estado.get("provider_last_fail") or {}
    ):
        estado["provider_last_ok"] = exitos
        estado["provider_last_fail"] = fallos
        save_state(estado)
    return merged, failures


def run_once(cfg, forzar=False):
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
    directos = [o for o in offers if not o.get("stops")]
    mejor_directo = directos[0] if directos else None
    state = load_state()
    log(f"TOTAL {len(offers)} opciones · mejor "
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
            "stops": best.get("stops", 0),
            "direct_price": mejor_directo["price"] if mejor_directo else None,
        }) + "\n")

    reason = decide(
        best["price"],
        state,
        cfg["alerts"],
        mejor_directo["price"] if mejor_directo else None,
    )
    if forzar:
        reason = reason or "prueba"
    if reason:
        text, html = render.body(
            reason, offers, state, search_cfg, cfg["alerts"].get("price_threshold"), HISTORY
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
    if mejor_directo:
        state["last_direct_price"] = mejor_directo["price"]
        state["all_time_low_direct"] = min(
            mejor_directo["price"], state.get("all_time_low_direct", mejor_directo["price"])
        )
    state["all_time_low"] = min(best["price"], state.get("all_time_low", best["price"]))
    state["last_check"] = now().isoformat(timespec="seconds")
    save_state(state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument(
        "--loop-minutes",
        type=int,
        default=0,
        help="Revisa en bucle durante N minutos y termina. Pensado para GitHub "
             "Actions: una sola corrida cubre una hora entera de vigilancia, "
             "aunque el cron se salte disparos.",
    )
    ap.add_argument("--test-mail", action="store_true")
    ap.add_argument(
        "--force-email",
        action="store_true",
        help="Busca y manda el reporte completo aunque no haya novedades. Para probar.",
    )
    args = ap.parse_args()
    cfg = load_config()

    if args.force_email:
        log("Envío forzado (prueba)")
        run_once(cfg, forzar=True)
        return

    if args.test_mail:
        notifier.send(
            cfg["email"],
            "✈️ Prueba del agente de vuelos",
            "Si lees esto, el envío de correo funciona correctamente.",
        )
        log("Correo de prueba enviado.")
        return

    if args.loop_minutes:
        interval = int(cfg["run"].get("interval_minutes", 10)) * 60
        fin = time.time() + args.loop_minutes * 60
        vuelta = 0
        log(f"Vigilancia continua por {args.loop_minutes} min, revisando cada "
            f"{interval // 60} min.")
        while True:
            vuelta += 1
            log(f"--- revisión {vuelta} ---")
            try:
                run_once(cfg)
            except Exception:
                log("ERROR:\n" + traceback.format_exc())
            # Solo dormimos si alcanza para otra revisión completa.
            if time.time() + interval >= fin:
                break
            time.sleep(interval)
        log(f"Fin del turno: {vuelta} revisiones.")
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
