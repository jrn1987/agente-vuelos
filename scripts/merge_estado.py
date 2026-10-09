#!/usr/bin/env python3
"""Combina el estado y el historial locales con los que ya están en el repo.

Dos turnos del agente pueden correr a la vez (por ejemplo, la vigilancia y un
envío de prueba). Antes se intentaba un rebase y el choque hacía fallar la
corrida entera. Aquí no hay conflicto posible: el historial es la unión de las
dos versiones y el estado toma lo más reciente de cada campo.

Uso: merge_estado.py <dir_del_repo> <dir_con_la_copia_local>
"""
import json
import os
import sys

repo_dir, mio_dir = sys.argv[1], sys.argv[2]


def leer_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def leer_lineas(path):
    try:
        with open(path) as f:
            return [l for l in f.read().splitlines() if l.strip()]
    except Exception:
        return []


# --- historiales: uno por ruta vigilada, unión sin duplicados y ordenados ---
nombres = set()
for carpeta in (repo_dir, mio_dir):
    if os.path.isdir(carpeta):
        nombres |= {n for n in os.listdir(carpeta) if n.startswith("history") and n.endswith(".jsonl")}

historiales = {}
for nombre in sorted(nombres):
    combinado = {}
    for carpeta in (repo_dir, mio_dir):
        for linea in leer_lineas(os.path.join(carpeta, nombre)):
            try:
                combinado[json.loads(linea)["ts"]] = linea
            except Exception:
                continue
    historiales[nombre] = [combinado[k] for k in sorted(combinado)]

# --- estado: gana el más reciente, pero sin perder lo ya avisado ---
repo, mio = leer_json(os.path.join(repo_dir, "state.json")), leer_json(os.path.join(mio_dir, "state.json"))
nuevo = dict(repo)
if mio.get("last_check", "") >= repo.get("last_check", ""):
    nuevo.update(mio)

# Cada ruta vigilada lleva su propio bloque: se combinan uno por uno para que
# una ruta no pise el estado de la otra.
rutas_combinadas = dict(repo.get("routes") or {})
for rid, mio_r in (mio.get("routes") or {}).items():
    repo_r = rutas_combinadas.get(rid) or {}
    combinada = dict(repo_r)
    if mio_r.get("last_check", "") >= repo_r.get("last_check", ""):
        combinada.update(mio_r)
    if repo_r.get("emails_date") == mio_r.get("emails_date"):
        combinada["emails_sent"] = max(
            repo_r.get("emails_sent", 0), mio_r.get("emails_sent", 0)
        )
        combinada["digest_sent"] = repo_r.get("digest_sent") or mio_r.get("digest_sent")
        combinada["prices_notified"] = sorted(
            set(repo_r.get("prices_notified", [])) | set(mio_r.get("prices_notified", []))
        )
    for campo in ("all_time_low", "all_time_low_direct"):
        valores = [v for v in (repo_r.get(campo), mio_r.get(campo)) if v is not None]
        if valores:
            combinada[campo] = min(valores)
    rutas_combinadas[rid] = combinada
if rutas_combinadas:
    nuevo["routes"] = rutas_combinadas

if repo.get("emails_date") == mio.get("emails_date"):
    # Mismo día: no perder correos ya contados ni precios ya avisados, para que
    # dos turnos simultáneos no manden el mismo aviso dos veces.
    nuevo["emails_sent"] = max(repo.get("emails_sent", 0), mio.get("emails_sent", 0))
    nuevo["digest_sent"] = repo.get("digest_sent") or mio.get("digest_sent")
    nuevo["prices_notified"] = sorted(
        set(repo.get("prices_notified", [])) | set(mio.get("prices_notified", []))
    )
for campo in ("all_time_low",):
    valores = [v for v in (repo.get(campo), mio.get(campo)) if v is not None]
    if valores:
        nuevo[campo] = min(valores)
for campo in ("last_email_ts",):
    valores = [v for v in (repo.get(campo), mio.get(campo)) if v]
    if valores:
        nuevo[campo] = max(valores)

os.makedirs(repo_dir, exist_ok=True)
for nombre, lineas in historiales.items():
    with open(os.path.join(repo_dir, nombre), "w") as f:
        f.write("\n".join(lineas) + ("\n" if lineas else ""))
with open(os.path.join(repo_dir, "state.json"), "w") as f:
    json.dump(nuevo, f, indent=2)
resumen = " · ".join(f"{n}: {len(v)}" for n, v in historiales.items())
print(f"historiales -> {resumen} · rutas en estado: {list(rutas_combinadas)}")
