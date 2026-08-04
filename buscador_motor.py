# -*- coding: utf-8 -*-
"""
buscador_motor.py
Motor de matching del buscador de buscafes.
Recibe la traducción del modelo (JSON de filtros) y devuelve hasta 3 resultados con su porqué.

Diseño:
- Función pura: no llama a ninguna API, no toca Firestore. Recibe data ya cargada.
- Matching por PALABRA COMPLETA (regex \\b), nunca substring crudo ("chill" no matchea "cuchillo").
- Ranking: "rating_bayesiano" (default) o "producto" (intensidad/menciones del hero).
- Dedupe por marca: máximo 1 resultado por nombre base.
- Relajación progresiva: si el filtro completo da vacío, se van soltando keywords
  (de a uno, los menos importantes primero) y se marca resultado_parcial=True.
- Devuelve estructura lista para armar la respuesta + mini-fichas.

En producción: la data viene de Firestore (colección cafes con campo tags).
Para testeo local: cargar tags_cafes_limpio.json + basenueva45.xlsx con cargar_data_local().
"""

import json
import re
import unicodedata
from datetime import datetime

MAX_RESULTADOS = 3
# Constantes del score bayesiano CONGELADAS para que los benchmarks entre versiones sean
# comparables (auditoría, punto 10). Recalcular deliberadamente (y re-correr el replay de
# regresión) solo cuando la base crezca en forma significativa: C = mean(Rating),
# m = quantile(0.75) de Cantidad Reviews.
BAYES_C = 4.42
BAYES_M = 906
MIN_REVIEWS_VAGAS = 50   # piso de reviews cuando la consulta es vaga (evita 5.0 con 12 reviews)
N_ESPECIFICOS = 2        # primeros N keywords de producto = intención específica; el resto, fallback


# ==================== NORMALIZACIÓN ====================

def norm(s: str) -> str:
    """minúsculas + sin tildes. Solo para COMPARAR, nunca para modificar data almacenada."""
    return unicodedata.normalize("NFD", str(s).lower().strip()).encode("ascii", "ignore").decode()


def matchea(keyword: str, texto: str) -> bool:
    """Match por palabra completa: cada palabra del keyword debe aparecer como palabra en el texto."""
    palabras = norm(keyword).split()
    t = norm(texto)
    return all(re.search(rf"\b{re.escape(p)}\b", t) for p in palabras)


def matchea_prefijo(keyword: str, texto: str) -> bool:
    """Match por PREFIJO de palabra: 'instagram' matchea 'instagrameable'.
    Solo para EXCLUSIONES: sobre-excluir es seguro, sub-excluir rompe la negación."""
    palabras = norm(keyword).split()
    t = norm(texto)
    return all(re.search(rf"\b{re.escape(p)}\w*", t) for p in palabras)


def nombre_base(nombre: str) -> str:
    """'Rita Specialty - Palermo' -> 'Rita Specialty' (para dedupe de marca)."""
    return re.split(r" - | \(", str(nombre))[0].strip()


# ==================== CARGA DE DATA (testeo local) ====================

def cargar_data_local(ruta_tags="tags_cafes_limpio.json", ruta_base="basenueva45.xlsx"):
    """Devuelve el universo de cafés como lista de dicts homogéneos."""
    import pandas as pd

    with open(ruta_tags, encoding="utf-8") as f:
        tags = json.load(f)
    df = pd.read_excel(ruta_base).drop_duplicates("ID", keep="first")
    df = df[df["ID"].isin(tags.keys())]

    C, m = BAYES_C, BAYES_M

    cafes = []
    for _, r in df.iterrows():
        t = tags[r["ID"]]
        v, R = r["Cantidad Reviews"], r["Rating"]
        cafes.append({
            "id": r["ID"],
            "nombre": r["Nombre"],
            "barrio": r["Barrio"],
            "rating": R,
            "reviews": v,
            "score_bayes": (v / (v + m)) * R + (m / (v + m)) * C,
            "booleanos": {c: bool(r[c]) for c in [
                "Permite mascotas", "Comida vegetariana", "Acceso silla de ruedas", "Delivery",
                "Espacio afuera", "Reservable", "Tiene takeaway", "Musica en vivo", "Brunch",
                "Es una cadena", "Tiene opciones sin tacc", "Cafe de especialidad", "Pasteleria Artesanal"]},
            "horarios": {dia: (r[f"{dia}_open"], r[f"{dia}_close"]) for dia in
                         ["Domingo", "Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]},
            "tags": t,
        })
    return cafes


# ==================== MATCHING ====================

def _textos_producto(t):
    return [h["producto"] for h in t["productos_hero"]] + t["productos_destacados"]


def _textos_ambiente(t):
    return t["ambiente_tags"] + t["señas_distintivas"] + t["ideal_para"]


def _heroes_matcheados(t, keywords):
    return [h for h in t["productos_hero"] if any(matchea(k, h["producto"]) for k in keywords)]


def _esta_abierto(cafe, ahora=None):
    ahora = ahora or datetime.now()
    dia = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][ahora.weekday()]
    ap, ci = cafe["horarios"].get(dia, (None, None))
    if ap is None or ci is None or str(ap) == "nan":
        return False
    try:
        hhmm = ahora.strftime("%H:%M")
        ap, ci = str(ap), str(ci)
        if ci < ap:  # cierra pasada la medianoche (ej. 09:00 a 02:00)
            return hhmm >= ap or hhmm <= ci
        return ap <= hhmm <= ci
    except (TypeError, ValueError):
        return False


def evaluar_cafe(cafe, filtros, ahora=None):
    """Evalúa un café contra los filtros. Devuelve (pasa, evidencia) donde evidencia
    explica cada match (la mini-ficha sale de acá)."""
    t = cafe["tags"]
    evidencia = {"barrio": None, "booleanos": [], "productos": [], "ambiente": [], "excluido_por": None}

    # barrio: filtro duro
    barrios = filtros.get("barrios", [])
    if barrios:
        if not any(norm(b) == norm(cafe["barrio"]) for b in barrios):
            return False, evidencia
        evidencia["barrio"] = cafe["barrio"]

    # booleanos: filtro duro
    for b in filtros.get("booleanos", []):
        if not cafe["booleanos"].get(b, False):
            return False, evidencia
        evidencia["booleanos"].append(b)

    # abierto ahora: filtro duro
    if filtros.get("abierto_ahora"):
        if not _esta_abierto(cafe, ahora):
            return False, evidencia

    # exclusiones: si CUALQUIER keyword de exclusión matchea tags o alertas -> afuera
    todos = _textos_producto(t) + _textos_ambiente(t) + [a["alerta"] for a in t["alertas_recurrentes"]]
    for k in filtros.get("keywords_excluir", []):
        hit = next((tx for tx in todos if matchea_prefijo(k, tx)), None)
        if hit:
            evidencia["excluido_por"] = f"{k} -> '{hit}'"
            return False, evidencia

    # productos: al menos UN keyword debe matchear (si hay keywords de producto)
    kp = filtros.get("keywords_productos", [])
    if kp:
        for k in kp:
            for tx in _textos_producto(t):
                if matchea(k, tx):
                    evidencia["productos"].append((k, tx))
        if not evidencia["productos"]:
            return False, evidencia

    # ambiente: al menos UN keyword debe matchear (si hay keywords de ambiente)
    ka = filtros.get("keywords_ambiente", [])
    if ka:
        for k in ka:
            for tx in _textos_ambiente(t):
                if matchea(k, tx):
                    evidencia["ambiente"].append((k, tx))
                    break  # un ejemplo por keyword alcanza para la ficha
        if not evidencia["ambiente"]:
            return False, evidencia

    return True, evidencia


# ==================== RANKING Y RESPUESTA ====================

def _rankear(candidatos, filtros, consulta_vaga):
    orden = filtros.get("orden", "rating_bayesiano")
    kp = filtros.get("keywords_productos", [])

    def prioridad_kw(ev):
        """Posición del mejor keyword de producto matcheado: matchear el #1 (la intención
        literal del usuario) vale más que matchear el #4 (fallback). Mayor = mejor."""
        idxs = [kp.index(k) for k, _ in ev["productos"] if k in kp]
        return -min(idxs) if idxs else -len(kp)

    def clave(item):
        cafe, ev = item
        if orden == "producto":
            heroes = _heroes_matcheados(cafe["tags"], kp)
            max_int = max((h["intensidad"] for h in heroes), default=0)
            max_menc = max((h["menciones"] for h in heroes), default=0)
            return (prioridad_kw(ev), max_int, max_menc, cafe["score_bayes"])
        # rating_bayesiano: prioridad del keyword, riqueza de evidencia, score
        riqueza = len(ev["productos"]) + len(ev["ambiente"])
        return (prioridad_kw(ev), riqueza, cafe["score_bayes"])

    candidatos = sorted(candidatos, key=clave, reverse=True)

    # piso de reviews para consultas vagas (sin ningún keyword)
    if consulta_vaga:
        candidatos = [c for c in candidatos if c[0]["reviews"] >= MIN_REVIEWS_VAGAS]

    # dedupe por marca + despriorizar cadenas en consultas vagas
    finales, marcas = [], set()
    for cafe, ev in candidatos:
        if consulta_vaga and cafe["booleanos"].get("Es una cadena"):
            continue
        b = nombre_base(cafe["nombre"])
        if b in marcas:
            continue
        marcas.add(b)
        finales.append((cafe, ev))
        if len(finales) == MAX_RESULTADOS:
            break

    # si despriorizar cadenas dejó menos de 3, completar con cadenas
    if consulta_vaga and len(finales) < MAX_RESULTADOS:
        for cafe, ev in candidatos:
            b = nombre_base(cafe["nombre"])
            if b in marcas:
                continue
            marcas.add(b)
            finales.append((cafe, ev))
            if len(finales) == MAX_RESULTADOS:
                break
    return finales


def _orden_relajacion(filtros):
    """Qué soltar primero si no hay resultados: ambiente de a uno (del último al primero),
    después productos de a uno (ídem, el primero es el más importante), nunca barrio ni booleanos."""
    pasos = []
    ka = list(filtros.get("keywords_ambiente", []))
    kp = list(filtros.get("keywords_productos", []))
    for i in range(len(ka) - 1, -1, -1):
        pasos.append(("keywords_ambiente", ka[i]))
    for i in range(len(kp) - 1, 0, -1):
        pasos.append(("keywords_productos", kp[i]))
    return pasos


def buscar(traduccion, cafes, ahora=None):
    """Punto de entrada del motor.
    traduccion: el JSON completo que devolvió el modelo (con modo, filtros, nota).
    cafes: universo cargado (lista de dicts).
    Devuelve: dict con modo, resultados [(cafe, evidencia)], resultado_parcial, keywords_sin_match, nota.
    """
    modo = traduccion.get("modo", "busqueda")
    nota = traduccion.get("nota_para_respuesta", "")

    if modo in ("favorita", "off_topic", "comparacion"):
        return {"modo": modo, "resultados": [], "resultado_parcial": False,
                "keywords_sin_match": [], "nota": nota}

    filtros = dict(traduccion.get("filtros", {}))
    consulta_vaga = not any([filtros.get("keywords_productos"), filtros.get("keywords_ambiente"),
                             filtros.get("barrios"), filtros.get("booleanos")])

    # PASADA 1 — solo la intención específica: primeros N_ESPECIFICOS keywords de producto.
    # El orden del modelo es semántico: lo puntual primero, la red amplia después.
    kp = filtros.get("keywords_productos", [])
    if len(kp) > N_ESPECIFICOS:
        f_especifico = dict(filtros)
        f_especifico["keywords_productos"] = kp[:N_ESPECIFICOS]
        candidatos = []
        for cafe in cafes:
            pasa, ev = evaluar_cafe(cafe, f_especifico, ahora)
            if pasa:
                candidatos.append((cafe, ev))
        resultados = _rankear(candidatos, f_especifico, consulta_vaga)
        if resultados:
            return {"modo": modo, "resultados": resultados, "resultado_parcial": False,
                    "keywords_sin_match": [], "nota": nota}

    # PASADA 2 — filtro completo con fallbacks; si esto responde, es resultado PARCIAL
    # (no hubo match de lo específico, se ofrece lo más cercano)
    candidatos = []
    for cafe in cafes:
        pasa, ev = evaluar_cafe(cafe, filtros, ahora)
        if pasa:
            candidatos.append((cafe, ev))
    resultados = _rankear(candidatos, filtros, consulta_vaga)
    if resultados:
        parcial = len(kp) > N_ESPECIFICOS  # si hubo pasada 1 y falló, esto es "lo más cercano"
        soltados = kp[:N_ESPECIFICOS] if parcial else []
        return {"modo": modo, "resultados": resultados, "resultado_parcial": parcial,
                "keywords_sin_match": soltados, "nota": nota}

    # relajación progresiva
    soltados = []
    f = {k: (list(v) if isinstance(v, list) else v) for k, v in filtros.items()}
    for campo, kw in _orden_relajacion(filtros):
        if kw in f.get(campo, []):
            f[campo].remove(kw)
            soltados.append(kw)
        candidatos = []
        for cafe in cafes:
            pasa, ev = evaluar_cafe(cafe, f, ahora)
            if pasa:
                candidatos.append((cafe, ev))
        resultados = _rankear(candidatos, f, False)
        if resultados:
            return {"modo": modo, "resultados": resultados, "resultado_parcial": True,
                    "keywords_sin_match": soltados, "nota": nota}

    # nada, ni relajado
    return {"modo": "sin_resultados", "resultados": [], "resultado_parcial": False,
            "keywords_sin_match": soltados, "nota": nota}


# ==================== FICHA (para debug / armar respuesta) ====================

def imprimir_resultado(res):
    print(f"modo: {res['modo']}" + (f" | PARCIAL, soltó: {res['keywords_sin_match']}" if res["resultado_parcial"] else ""))
    if res["nota"]:
        print(f"nota: {res['nota']}")
    for cafe, ev in res["resultados"]:
        print(f"★ {cafe['nombre']} ({cafe['barrio']}) — {cafe['rating']} ({cafe['reviews']:.0f} reviews)")
        if ev["productos"]:
            for k, tx in ev["productos"][:3]:
                print(f"   producto: '{tx}' (por '{k}')")
        if ev["ambiente"]:
            print(f"   ambiente: {', '.join(tx for _, tx in ev['ambiente'][:4])}")
        if ev["booleanos"]:
            print(f"   cumple: {', '.join(ev['booleanos'])}")
    print()
