# -*- coding: utf-8 -*-
"""
replay_tags.py — mide el efecto de un set de tags en el buscador, sin llamar a ninguna API.

Toma traducciones ya hechas ({consulta: traducción}, p. ej. las de comparar_modelos.py) y
las pasa por buscador_motor.buscar() con distintos sets de tags. Como la traducción queda
fija, cualquier diferencia en los resultados es efecto de los tags.

Métricas por consulta (se excluyen las banales: sin condiciones, barrios ni booleanos):
  vacia       -> el motor no devolvió ningún café
  nivel       -> completo / parcial / aproximado (nivel_cobertura del motor)
  bayes_top   -> el 1.º y el 2.º empatan en todo lo que no es el bayesiano: el que ganó
                 lo eligió la popularidad, no la evidencia
  bayes_puro  -> ninguno de los resultados cumple una condición con evidencia directa

Uso:
  python replay_tags.py --traducciones traducciones_base.json \
      --base basenueva48.xlsx --tags actual=tags_cafes_limpio_v2.json \
      --tags haiku55=tags_haiku55.json --tags sonnet55=tags_sonnet55.json

  Cada --tags a partir del segundo se superpone al primero: los cafés que trae reemplazan
  a los del primer set y el resto queda igual. Así se puede medir una muestra de cafés
  re-tageados sin tener la base entera.

  --top N               mide los N primeros en vez de los MAX_RESULTADOS del motor
  --solo-ids ids.json   limita el universo a esos IDs (lista o dict; p. ej. los activos)
  --universo-tags N     usa como universo solo los cafés que trae el set N (sin superponer)
  --salida detalle.csv  una fila por consulta x set
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import buscador_motor as motor

# El motor filtra por horario si la consulta pide "abierto ahora": se fija un momento
# para que el replay sea reproducible (sábado 17:00).
AHORA_FIJO = datetime(2026, 10, 17, 17, 0)


def cargar_tags(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cargar_universo(base, tags, solo_ids=None):
    """Igual que motor.cargar_data_local() pero con tags ya cargados y filtro de IDs."""
    import pandas as pd
    df = pd.read_excel(base).drop_duplicates("ID", keep="first")
    ids = set(tags) if solo_ids is None else set(tags) & set(solo_ids)
    df = df[df["ID"].isin(ids)]
    bools = ["Permite mascotas", "Comida vegetariana", "Acceso silla de ruedas", "Delivery",
             "Espacio afuera", "Reservable", "Tiene takeaway", "Musica en vivo", "Brunch",
             "Es una cadena", "Tiene opciones sin tacc", "Cafe de especialidad", "Pasteleria Artesanal"]
    dias = ["Domingo", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
    cafes = []
    for _, r in df.iterrows():
        v, R = r["Cantidad Reviews"], r["Rating"]
        cafes.append({
            "id": r["ID"], "nombre": r["Nombre"], "barrio": r["Barrio"], "rating": R, "reviews": v,
            "score_bayes": (v / (v + motor.BAYES_M)) * R + (motor.BAYES_M / (v + motor.BAYES_M)) * motor.BAYES_C,
            "booleanos": {c: motor.to_bool(r[c]) for c in bools},
            "horarios": {d: (r[f"{d}_open"], r[f"{d}_close"]) for d in dias},
            "tags": tags[r["ID"]],
        })
    return cafes


def es_banal(trad):
    f = (trad or {}).get("filtros") or {}
    return not any([f.get("condiciones"), f.get("barrios"), f.get("booleanos")])


def _clave_sin_bayes(cafe, ev, filtros):
    """La clave de ranking de motor._rankear() sin el último escalón (score_bayes)."""
    if filtros.get("orden") == "producto":
        kp = motor._keywords_producto_planas(filtros.get("condiciones", []))
        heroes = motor._heroes_matcheados(cafe["tags"], kp)
        return (ev["cobertura"], motor._nivel_producto(cafe["tags"], kp),
                max((h["intensidad"] or 0 for h in heroes), default=0),
                max((h["menciones"] or 0 for h in heroes), default=0),
                ev.get("fuerza", 0.0), ev.get("riqueza_kw", 0))
    return (ev["cobertura"], ev.get("fuerza", 0.0), ev.get("riqueza_kw", 0))


def medir(consulta, trad, cafes):
    res = motor.buscar(trad, cafes, ahora=AHORA_FIJO)
    out = {"consulta": consulta, "modo": res["modo"], "nivel": res.get("nivel_cobertura"),
           "n": len(res["resultados"]), "vacia": not res["resultados"],
           "bayes_top": False, "bayes_puro": False,
           "top": " | ".join(c["nombre"] for c, _ in res["resultados"]),
           "top_ids": [c["id"] for c, _ in res["resultados"]]}
    if res["resultados"]:
        filtros = motor.limpiar_traduccion(trad).get("filtros") or {}
        r = res["resultados"]
        if len(r) >= 2:
            out["bayes_top"] = _clave_sin_bayes(*r[0], filtros) == _clave_sin_bayes(*r[1], filtros)
        out["bayes_puro"] = bool(filtros.get("condiciones")) and all(
            ev.get("nivel_evidencia") in ("proxy", "sin_condiciones") for _, ev in r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traducciones", required=True)
    ap.add_argument("--base", required=True, help="basenueva*.xlsx (rating, reviews, booleanos, horarios)")
    ap.add_argument("--tags", action="append", required=True, metavar="NOMBRE=PATH")
    ap.add_argument("--solo-ids")
    ap.add_argument("--universo-tags", action="store_true",
                    help="cada set usa como universo solo sus propios cafés, sin superponer")
    ap.add_argument("--top", type=int, help="cuántos resultados medir (el motor devuelve MAX_RESULTADOS)")
    ap.add_argument("--salida")
    a = ap.parse_args()
    if a.top:
        motor.MAX_RESULTADOS = a.top

    trads = {q: t for q, t in json.loads(Path(a.traducciones).read_text(encoding="utf-8")).items()
             if t and t.get("modo", "busqueda") == "busqueda" and not es_banal(t)}
    solo = json.loads(Path(a.solo_ids).read_text(encoding="utf-8")) if a.solo_ids else None

    sets, primero = {}, None
    for spec in a.tags:
        nombre, path = spec.split("=", 1)
        t = cargar_tags(path)
        if primero is None or a.universo_tags:
            sets[nombre] = t
            primero = primero or t
        else:
            sets[nombre] = {**primero, **t}

    filas, resumen = [], []
    por_set = {}
    for nombre, tags in sets.items():
        motor.limpiar_cache_indice()   # el índice de keywords se arma con los tags: no reusar entre sets
        cafes = cargar_universo(a.base, tags, solo)
        medidas = [medir(q, t, cafes) for q, t in trads.items()]
        por_set[nombre] = {m["consulta"]: m for m in medidas}
        niveles = Counter(m["nivel"] for m in medidas)
        resumen.append({"set": nombre, "cafes": len(cafes), "consultas": len(medidas),
                        "vacias": sum(m["vacia"] for m in medidas),
                        "completo": niveles["completo"], "parcial": niveles["parcial"],
                        "aproximado": niveles["aproximado"],
                        "bayes_top": sum(m["bayes_top"] for m in medidas),
                        "bayes_puro": sum(m["bayes_puro"] for m in medidas)})
        filas += [{"set": nombre, **{k: v for k, v in m.items() if k != "top_ids"}} for m in medidas]

    ref = next(iter(por_set))
    for r in resumen[1:]:
        r["top_distinto_vs_" + ref] = sum(por_set[r["set"]][q]["top_ids"] != por_set[ref][q]["top_ids"]
                                         for q in trads)

    print(f"{len(trads)} consultas no banales\n")
    cols = list(dict.fromkeys(k for r in resumen for k in r))
    print("  ".join(f"{c:>12}" for c in cols))
    for r in resumen:
        print("  ".join(f"{str(r.get(c, '')):>12}" for c in cols))

    if a.salida:
        with open(a.salida, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
        print(f"\nDetalle: {a.salida}")


if __name__ == "__main__":
    main()
