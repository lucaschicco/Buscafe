# -*- coding: utf-8 -*-
"""
buscador_motor.py
Motor de matching del buscador de buscafes.
Recibe la traducción del modelo (JSON de filtros) y devuelve hasta 3 resultados con su porqué.

Diseño:
- Función pura: no llama a ninguna API, no toca Firestore. Recibe data ya cargada.
- Matching por FRASE completa (no AND de palabras sueltas), con flexibilidad morfológica
  por palabra ('roll de canela' no matchea 'roll de chocolate y canela'; 'flat-white'
  matchea 'flat white').
- Filtros DUROS (sin excepción): barrios, booleanos, abierto_ahora, keywords_excluir.
- CONDICIONES (filtros["condiciones"], viene del prompt del traductor): cada una representa
  UNA intención independiente del usuario, con sus propios keywords/variantes/proxies
  adentro (matcheo OR interno -- cualquiera de esos keywords alcanza para dar la condición
  por cumplida). El % de cobertura de un café = condiciones cumplidas / condiciones totales,
  contando cada condición UNA vez sin importar cuántos keywords tenga adentro. Esto es
  deliberado: si contáramos cada keyword suelto como una condición (diseño viejo), una
  consulta vaga como "un lugar lindo" (que el traductor expande a 5 tags relacionados)
  quedaría con cobertura artificialmente baja con solo 1 de esos 5 matcheando, cuando
  conceptualmente es un match perfecto de la única cosa que pidieron.
- NIVELES DE COBERTURA (ver _nivel_cobertura): "completo" (100%), "parcial" (>=65% pero
  no 100% -- se muestra con aviso de qué falta), "aproximado" (<65% pero >0% -- se
  muestra como "lo más cercano", nunca se oculta un café que no matcheó NADA de lo pedido).
  Reemplaza el diseño de un único umbral fijo: con pocas condiciones el 65% puede no
  existir como valor posible (2 condiciones: 0/50/100%), así que un solo corte castigaba
  de forma inconsistente según cuántas condiciones tuviera cada consulta.
- Ranking: cobertura primero, después "rating_bayesiano" (default) o "producto"
  (intensidad/menciones del hero) como desempate.
- Dedupe por marca: máximo 1 resultado por nombre base.
- Devuelve estructura lista para armar la respuesta + mini-fichas, con evidencia de
  qué se cumplió y qué faltó por café (para que el mensaje al usuario sea honesto).

NOTA sobre calidad de evidencia: este motor NO decide qué keywords agrupar dentro de
una condición -- eso lo hace el prompt del traductor (armar_system_prompt() en
benchmark_buscador_v1.py / app.py). Si en algún momento aparece evidencia demasiado
genérica o poco relacionada (ej: "medialunas" matcheando por el proxy "pasteleria",
una categoría mucho más amplia que incluye tortas/cheesecakes/lemon pie sin relación
real con medialunas), el fix va en la REGLA del prompt sobre cuándo agrupar proxies
dentro de una condición, no en este archivo -- acá no hay nada que ajustar.

En producción: la data viene de Firestore (colección cafes con campo tags).
Para testeo local: cargar tags_cafes_limpio.json + basenueva46.xlsx con cargar_data_local().
"""

import json
import re
import unicodedata
from datetime import datetime, time as dtime

MAX_RESULTADOS = 3
# Constantes del score bayesiano CONGELADAS para que los benchmarks entre versiones sean
# comparables (auditoría, punto 10). Recalcular deliberadamente (y re-correr el replay de
# regresión) solo cuando la base crezca en forma significativa: C = mean(Rating),
# m = quantile(0.75) de Cantidad Reviews.
BAYES_C = 4.42
BAYES_M = 906
MIN_REVIEWS_VAGAS = 50   # piso de reviews cuando la consulta es vaga (evita 5.0 con 12 reviews)
UMBRAL_COBERTURA = 0.65  # % mínimo de condiciones cumplidas para nivel "parcial" (ver _nivel_cobertura)


# ==================== NORMALIZACIÓN ====================

def norm(s: str) -> str:
    """minúsculas + sin tildes. Solo para COMPARAR, nunca para modificar data almacenada."""
    return unicodedata.normalize("NFD", str(s).lower().strip()).encode("ascii", "ignore").decode()


def _normalizar_frase(s: str) -> str:
    """Puntuación -> espacios, espacios múltiples colapsados. Para que 'flat-white' y
    'flat white' se traten como la misma frase al matchear."""
    s = re.sub(r"[^\w\s]", " ", norm(s))
    return re.sub(r"\s+", " ", s).strip()


def matchea(keyword: str, texto: str) -> bool:
    """Match de FRASE completa (no AND de palabras sueltas): 'roll de canela' NO matchea
    'roll de chocolate y canela'. Se normaliza puntuación a espacios para tolerar variantes
    tipo 'flat-white' -> 'flat white', pero el orden y la adyacencia de las palabras
    del keyword se respetan tal cual."""
    k = _normalizar_frase(keyword)
    t = _normalizar_frase(texto)
    return re.search(rf"\b{re.escape(k)}\b", t) is not None


def matchea_prefijo(keyword: str, texto: str) -> bool:
    """Match de FRASE (adyacente, en orden) con flexibilidad morfológica por palabra:
    'instagram' matchea 'instagrameable', 'ruidoso' matchea 'ruidosos'. Solo para
    EXCLUSIONES: sobre-excluir es preferible a sub-excluir, pero las palabras del
    keyword deben aparecer juntas como frase -- si no, un keyword de 2+ palabras puede
    matchear textos sin relación real (ej. la palabra 'cafe' aparece en casi cualquier
    tag de la base) y vaciar resultados válidos sin motivo."""
    k = _normalizar_frase(keyword)
    t = _normalizar_frase(texto)
    patron = r"\b" + r"\w*\s+".join(re.escape(p) for p in k.split()) + r"\w*\b"
    return re.search(patron, t) is not None


def nombre_base(nombre: str) -> str:
    """'Rita Specialty - Palermo' -> 'Rita Specialty' (para dedupe de marca)."""
    return re.split(r" - | \(", str(nombre))[0].strip()


# ==================== CARGA DE DATA (testeo local) ====================

def to_bool(v):
    """NaN/vacío -> False (dato faltante NUNCA es afirmación positiva).
    Bool real se respeta. String se interpreta explícitamente, nunca con bool() crudo
    (bool('False') da True en Python -- trampa clásica)."""
    import pandas as pd
    if pd.isna(v):
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "si", "sí")


def cargar_data_local(ruta_tags="tags_cafes_limpio.json", ruta_base="basenueva46.xlsx"):
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
            "booleanos": {c: to_bool(r[c]) for c in [
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


def _a_minutos(v):
    """Convierte un horario a minutos desde medianoche, sin importar el formato de origen
    (datetime.time de Excel/pandas, o string '18:30' / '18:30:00'). Comparar en minutos
    evita el bug de comparación lexicográfica de strings ('18:30' <= '18:00:00' -> True,
    que es incorrecto). Devuelve None si no se puede parsear -> tratado como sin dato."""
    if v is None:
        return None
    if isinstance(v, dtime):
        return v.hour * 60 + v.minute
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return None


def _esta_abierto(cafe, ahora=None):
    ahora = ahora or datetime.now()
    dia = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"][ahora.weekday()]
    ap, ci = cafe["horarios"].get(dia, (None, None))
    ap_min, ci_min = _a_minutos(ap), _a_minutos(ci)
    if ap_min is None or ci_min is None:
        return False
    ahora_min = ahora.hour * 60 + ahora.minute
    if ci_min < ap_min:  # cierra pasada la medianoche (ej. 09:00 a 02:00)
        return ahora_min >= ap_min or ahora_min <= ci_min
    return ap_min <= ahora_min <= ci_min


def evaluar_cafe(cafe, filtros, ahora=None):
    """Evalúa un café contra los filtros. Devuelve evidencia (dict) si el café pasa los
    filtros duros, o None si queda afuera por barrio/booleano/horario/exclusión.

    evidencia["cobertura"]: % de condiciones cumplidas (cada una cuenta 1 vez, sin
    importar cuántos keywords tenga adentro), 1.0 si no hay ninguna condición (consulta
    vaga o solo filtros duros).
    evidencia["cumplidas"]: [(tipo, intencion, keyword_que_matcheo, texto_matcheado), ...]
    evidencia["faltantes"]: [(tipo, intencion), ...] — condiciones que NO se pudieron
    confirmar con ningún keyword de esa condición.
    """
    t = cafe["tags"]
    evidencia = {"barrio": None, "booleanos": [], "cumplidas": [], "faltantes": [],
                 "cobertura": 1.0, "excluido_por": None}

    # barrio: filtro duro
    barrios = filtros.get("barrios", [])
    if barrios:
        if not any(norm(b) == norm(cafe["barrio"]) for b in barrios):
            return None
        evidencia["barrio"] = cafe["barrio"]

    # booleanos: filtro duro
    for b in filtros.get("booleanos", []):
        if not cafe["booleanos"].get(b, False):
            return None
        evidencia["booleanos"].append(b)

    # abierto ahora: filtro duro
    if filtros.get("abierto_ahora"):
        if not _esta_abierto(cafe, ahora):
            return None

    # exclusiones: si CUALQUIER keyword de exclusión matchea tags o alertas -> afuera
    todos = _textos_producto(t) + _textos_ambiente(t) + [a["alerta"] for a in t["alertas_recurrentes"]]
    for k in filtros.get("keywords_excluir", []):
        hit = next((tx for tx in todos if matchea_prefijo(k, tx)), None)
        if hit:
            evidencia["excluido_por"] = f"{k} -> '{hit}'"
            return None

    # condiciones: cada una es UNA intención independiente. Adentro, matcheo OR entre
    # todos sus keywords (variantes/sinónimos/proxies) -- cualquiera que matchee alcanza
    # para dar la condición entera por cumplida.
    condiciones = filtros.get("condiciones", [])

    if condiciones:
        textos_producto = _textos_producto(t)
        textos_ambiente = _textos_ambiente(t)
        for cond in condiciones:
            tipo = cond.get("tipo", "ambiente")
            intencion = cond.get("intencion", "")
            keywords = cond.get("keywords", [])
            textos = textos_producto if tipo == "producto" else textos_ambiente
            encontrado = None
            for k in keywords:
                match = next((tx for tx in textos if matchea(k, tx)), None)
                if match:
                    encontrado = (k, match)
                    break
            if encontrado:
                evidencia["cumplidas"].append((tipo, intencion, encontrado[0], encontrado[1]))
            else:
                evidencia["faltantes"].append((tipo, intencion))
        evidencia["cobertura"] = len(evidencia["cumplidas"]) / len(condiciones)

    return evidencia


def _nivel_cobertura(cobertura):
    """Clasifica el % de cobertura en 3 niveles para decidir cómo comunicarlo:
    - "completo": 100%, match exacto de todo lo pedido.
    - "parcial": >=UMBRAL_COBERTURA pero no 100% -- se puede decir "encontré esto que
      cumple X, aunque no Y".
    - "aproximado": <UMBRAL_COBERTURA pero >0% -- ningún café cumple lo suficiente como
      para un "match parcial" honesto, pero mostrar el más cercano sigue siendo más útil
      que "no encontré nada" (mientras haya cumplido AL MENOS una condición real).
    - "sin_resultados": 0%, no hay ningún café con evidencia de ninguna condición pedida.
    """
    if cobertura >= 1.0:
        return "completo"
    if cobertura >= UMBRAL_COBERTURA:
        return "parcial"
    if cobertura > 0:
        return "aproximado"
    return "sin_resultados"


# ==================== RANKING Y RESPUESTA ====================

def _keywords_producto_planas(condiciones):
    """Aplana todos los keywords de las condiciones tipo 'producto' en una sola lista,
    para _heroes_matcheados (que necesita una lista plana, no la estructura anidada)."""
    out = []
    for c in condiciones:
        if c.get("tipo") == "producto":
            out.extend(c.get("keywords", []))
    return out


def _rankear(candidatos, filtros, consulta_vaga):
    orden = filtros.get("orden", "rating_bayesiano")
    kp_planas = _keywords_producto_planas(filtros.get("condiciones", []))

    def clave(item):
        cafe, ev = item
        cobertura = ev["cobertura"]
        if orden == "producto":
            heroes = _heroes_matcheados(cafe["tags"], kp_planas)
            max_int = max((h["intensidad"] for h in heroes), default=0)
            max_menc = max((h["menciones"] for h in heroes), default=0)
            return (cobertura, max_int, max_menc, cafe["score_bayes"])
        # rating_bayesiano: cobertura primero (cuántas condiciones cumple),
        # score bayesiano como desempate entre cafés con la misma cobertura
        return (cobertura, cafe["score_bayes"])

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


def buscar(traduccion, cafes, ahora=None):
    """Punto de entrada del motor.
    traduccion: el JSON completo que devolvió el modelo (con modo, filtros, nota).
    cafes: universo cargado (lista de dicts).
    Devuelve: dict con modo, resultados [(cafe, evidencia)], resultado_parcial,
    nivel_cobertura, nota.

    nivel_cobertura ("completo" | "parcial" | "aproximado"): calculado sobre el MEJOR
    resultado devuelto (el primero, tras rankear). Le dice a app.py qué plantilla de
    mensaje usar -- "encontré esto" / "encontré esto, aunque no cumple todo" / "no hay
    match completo, lo más cercano es esto". Cada café individual puede tener su propia
    cobertura distinta (ver evidencia["cumplidas"]/["faltantes"] de cada uno).

    NOTA para app.py: "keywords_sin_match" (top-level) ya NO se usa — queda vacío por
    compatibilidad. La info de qué faltó vive POR CAFÉ en evidencia["faltantes"].
    """
    modo = traduccion.get("modo", "busqueda")
    nota = traduccion.get("nota_para_respuesta", "")

    if modo in ("favorita", "off_topic", "comparacion"):
        return {"modo": modo, "resultados": [], "resultado_parcial": False,
                "nivel_cobertura": None, "keywords_sin_match": [], "nota": nota}

    filtros = dict(traduccion.get("filtros", {}))
    condiciones = filtros.get("condiciones", [])
    consulta_vaga = not any([condiciones, filtros.get("barrios"), filtros.get("booleanos")])

    # una sola pasada: evaluar_cafe calcula cobertura (%) por café, filtros duros ya
    # aplicados adentro (barrio/booleanos/horario/exclusiones)
    candidatos = []
    for cafe in cafes:
        ev = evaluar_cafe(cafe, filtros, ahora)
        if ev is not None:
            candidatos.append((cafe, ev))

    if not candidatos:
        return {"modo": "sin_resultados", "resultados": [], "resultado_parcial": False,
                "nivel_cobertura": "sin_resultados", "keywords_sin_match": [], "nota": nota}

    # piso: al menos UNA condición cumplida (cobertura > 0). Mostrar un café que no
    # matcheó NADA de lo pedido no es "lo más cercano", es ruido. No aplica a consulta
    # vaga (ahí cobertura siempre es 1.0, no hay nada que filtrar).
    if not consulta_vaga:
        candidatos = [c for c in candidatos if c[1]["cobertura"] > 0]
        if not candidatos:
            return {"modo": "sin_resultados", "resultados": [], "resultado_parcial": False,
                    "nivel_cobertura": "sin_resultados", "keywords_sin_match": [], "nota": nota}

    resultados = _rankear(candidatos, filtros, consulta_vaga)
    if not resultados:
        return {"modo": "sin_resultados", "resultados": [], "resultado_parcial": False,
                "nivel_cobertura": "sin_resultados", "keywords_sin_match": [], "nota": nota}

    mejor_cobertura = resultados[0][1]["cobertura"]
    nivel = "completo" if consulta_vaga else _nivel_cobertura(mejor_cobertura)
    resultado_parcial = nivel != "completo"

    return {"modo": modo, "resultados": resultados, "resultado_parcial": resultado_parcial,
            "nivel_cobertura": nivel, "keywords_sin_match": [], "nota": nota}


# ==================== FICHA (para debug / armar respuesta) ====================

def imprimir_resultado(res):
    nivel = res.get("nivel_cobertura")
    print(f"modo: {res['modo']}" + (f" | nivel: {nivel}" if nivel else ""))
    if res["nota"]:
        print(f"nota: {res['nota']}")
    for cafe, ev in res["resultados"]:
        print(f"★ {cafe['nombre']} ({cafe['barrio']}) — {cafe['rating']} ({cafe['reviews']:.0f} reviews) "
              f"— cobertura {ev['cobertura']*100:.0f}%")
        for tipo, intencion, k, tx in ev["cumplidas"]:
            print(f"   ✓ [{tipo}] {intencion}: '{tx}' (por '{k}')")
        for tipo, intencion in ev["faltantes"]:
            print(f"   ✗ [{tipo}] NO se encontró: {intencion}")
        if ev["booleanos"]:
            print(f"   cumple: {', '.join(ev['booleanos'])}")
    print()
