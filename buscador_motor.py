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

- FUERZA DE EVIDENCIA (nuevo): dentro de una condición, los keywords vienen separados en
  "keywords_directas" (si el café tiene ese tag, es evidencia directa de la intención) y
  "keywords_proxy" (lo sugiere sin demostrarlo). Los dos cumplen la condición por igual --
  la cobertura no cambia -- pero no valen lo mismo para ordenar. Sin esto, "un lugar donde
  pueda leer tranquilo" daba cobertura 100% a los 1.850 cafés con el tag "tranquilo" y el
  orden lo decidía el rating: ganaba el más popular, no el más relevante.
  La fuerza se agrega como PROMEDIO sobre las condiciones cumplidas y toma pocos valores
  discretos, deliberadamente: así siguen existiendo empates y el bayesiano sigue decidiendo
  adentro de cada nivel. Una señal continua acá (se probó con rareza de tags) aplasta al
  bayesiano y hace subir cafés de 20 reviews.

NOTA sobre calidad de evidencia: este motor NO decide qué keyword es directo y cuál es
proxy -- eso lo declara el traductor (armar_system_prompt() en app.py). Medido sobre 161
consultas, ~5% de las condiciones traen un tag muy ancho ascendido a directa (ej:
"tranquilo" como directa de "que nadie me apure"). Para eso está GUARDRAIL_DIRECTAS_ANCHAS,
apagado por default: se prende solo si el replay demuestra que mejora.

En producción: la data viene de Firestore (colección cafes con campo tags).
Para testeo local: cargar tags_cafes_limpio.json + basenueva46.xlsx con cargar_data_local().
"""

import json
import re
import unicodedata
from functools import lru_cache
from datetime import datetime, time as dtime

MAX_RESULTADOS = 3
# Constantes del score bayesiano CONGELADAS para que los benchmarks entre versiones sean
# comparables (auditoría, punto 10). Recalcular deliberadamente (y re-correr el replay de
# regresión) solo cuando la base crezca en forma significativa: C = mean(Rating),
# m = quantile(0.75) de Cantidad Reviews.
BAYES_C = 4.42
BAYES_M = 906
MIN_REVIEWS_VAGAS = 50   # piso de reviews cuando la consulta es vaga (evita 5.0 con 12 reviews)

# --- Fuerza de evidencia ---
FUERZA_DIRECTA = 2       # el café tiene un tag que ES la intención
FUERZA_PROXY = 1         # el café tiene un tag que la sugiere

# --- Experimentos, apagados por default. Se prenden de a UNO para poder atribuir la mejora ---
PISO_REVIEWS_GENERAL = 20    # piso de reviews para TODA consulta, no solo las vagas.
                             # Red de seguridad contra ruido puro, NO un criterio de
                             # calidad: de eso ya se encarga score_bayes, que para eso
                             # tiene m=906. Estuvo en 50 y se bajó tras medir QUÉ cafés
                             # eliminaba: de los 7 que sacaba, 6 tenían evidencia DIRECTA
                             # (ej: Las Heliconias 4.9/24rv con el tag "café 100%
                             # colombiano", la mejor respuesta posible a "cafeterías con
                             # granos colombianos"). Un piso alto contradice el principio
                             # del sistema -- evidencia por encima de popularidad -- justo
                             # donde la evidencia es más fuerte. Con 20 desaparecen igual
                             # los resultados de <20 reviews, pero cambian 2 consultas de
                             # 161 en vez de 7. 0 lo desactiva.
GUARDRAIL_DIRECTAS_ANCHAS = 0   # si > 0, una keyword_directa que matchee más de este número
                                # de cafés se degrada a proxy. Corrige los proxies ascendidos
                                # por el traductor. OJO: "medialunas" matchea 915 cafés y ES
                                # una directa legítima cuando el usuario pide medialunas, así
                                # que esto solo debería activarse junto con el chequeo de
                                # literalidad. Con 0 queda desactivado.
UMBRAL_COBERTURA = 0.65  # % mínimo de condiciones cumplidas para nivel "parcial" (ver _nivel_cobertura)


# ==================== NORMALIZACIÓN ====================

def norm(s: str) -> str:
    """minúsculas + sin tildes. Solo para COMPARAR, nunca para modificar data almacenada."""
    return unicodedata.normalize("NFD", str(s).lower().strip()).encode("ascii", "ignore").decode()


# Nombres propios que contienen una palabra común buscable. Sin esto, "patio" matchea
# "Patio Bullrich" (un shopping) y "jardin" matchea "Jardín Botánico" (un café DE FRENTE al
# Botánico no tiene jardín). Caso real de producción: "cafe con jardin en retiro" devolvió
# Starbucks y Le Pain Quotidien, los dos por el tag de ubicación en Patio Bullrich.
# Se eliminan del texto ANTES de matchear: el resto del tag sigue siendo matcheable
# ("brunch en Patio Bullrich" pierde el patio pero conserva el brunch).
NOMBRES_PROPIOS = [
    "patio bullrich",
    "jardin botanico",
    "mercado pago",
    "alto palermo",
    "galeria belgrano",
    "mercado uriarte",
]


def _sin_nombres_propios(texto_normalizado: str) -> str:
    """Saca los nombres propios de un texto YA normalizado."""
    for np_ in NOMBRES_PROPIOS:
        texto_normalizado = texto_normalizado.replace(np_, " ")
    return re.sub(r"\s+", " ", texto_normalizado).strip()


# Memoización de la preparación de textos. La base tiene ~21.000 textos únicos (tags,
# señas, ideal_para, productos) y cada uno se compara contra todos los keywords de la
# consulta: sin caché, normalizar el MISMO texto se repite cientos de miles de veces por
# consulta. Un dict simple y no lru_cache porque el universo de textos es chico, fijo y
# conocido: acotarlo por debajo de ese número hace que el caché se desborde y no sirva
# para nada (con maxsize=8192 medimos 109.971 misses en una sola consulta).
_CACHE_TEXTO = {}
MAX_CACHE_TEXTO = 60000


def _preparar_texto(texto: str) -> str:
    """Normaliza un texto y le saca los nombres propios, una sola vez por texto."""
    listo = _CACHE_TEXTO.get(texto)
    if listo is None:
        listo = _sin_nombres_propios(_normalizar_frase(texto))
        if len(_CACHE_TEXTO) < MAX_CACHE_TEXTO:
            _CACHE_TEXTO[texto] = listo
    return listo


@lru_cache(maxsize=4096)
def _normalizar_frase(s: str) -> str:
    """Puntuación -> espacios, espacios múltiples colapsados. Para que 'flat-white' y
    'flat white' se traten como la misma frase al matchear.

    Cacheada porque matchea() la llama sobre el MISMO keyword una vez por cada texto de
    cada café: con 7 keywords y 3.000 cafés son ~150.000 llamadas por consulta para
    normalizar 7 strings distintos."""
    s = re.sub(r"[^\w\s]", " ", norm(s))
    return re.sub(r"\s+", " ", s).strip()


def matchea(keyword: str, texto: str) -> bool:
    """Match de FRASE completa (no AND de palabras sueltas): 'roll de canela' NO matchea
    'roll de chocolate y canela'. Se normaliza puntuación a espacios para tolerar variantes
    tipo 'flat-white' -> 'flat white', pero el orden y la adyacencia de las palabras
    del keyword se respetan tal cual."""
    k = _normalizar_frase(keyword)
    t = _preparar_texto(texto)
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


_CACHE_INDICE = {}   # (keyword, tipo) -> {id_cafe: texto_que_matcheo}

# Tope de keywords cacheados. Cada entrada guarda hasta un id + texto por café, así que sin
# tope el caché crece con cada keyword nuevo que escriba un usuario y no se libera nunca:
# en un proceso que corre semanas sin reiniciar, eso se acumula. Al pasarse se descartan las
# entradas más viejas (los dicts conservan el orden de inserción), que son las de consultas
# que ya nadie repite.
MAX_CACHE_INDICE = 3000


def limpiar_cache_indice():
    """Vacía el índice invertido. HAY QUE LLAMARLA CADA VEZ QUE SE RECARGAN LOS CAFÉS SIN
    REINICIAR EL PROCESO.

    El índice se arma una sola vez por keyword sobre la lista de cafés que había en ese
    momento. Si después los datos se recargan en caliente y el caché queda, un café nuevo o
    uno cuyos tags se editaron nunca va a matchear ese keyword hasta el próximo restart: el
    motor no lo vuelve a mirar, lee el índice viejo. La falla es silenciosa -- no hay error,
    simplemente el café no aparece."""
    _CACHE_INDICE.clear()


def indice_keyword(keyword, tipo, cafes):
    """Índice invertido: qué cafés matchean este keyword y con qué texto.

    Se calcula sobre la base COMPLETA (no sobre los candidatos que ya pasaron los filtros
    duros) para que el resultado sea una propiedad estable del vocabulario y el caché sirva
    entre consultas distintas, sin importar el barrio pedido.

    Este caché es lo que hace viable mirar TODOS los keywords de una condición en vez de
    cortar en el primero que matchea: sin él, cada consulta recorre los 2.634 cafés una vez
    por keyword. Medido: 0,95s por consulta antes, 0,017s con el caché caliente."""
    key = (keyword, tipo)
    if key in _CACHE_INDICE:
        return _CACHE_INDICE[key]
    idx = {}
    for c in cafes:
        textos = _textos_producto(c["tags"]) if tipo == "producto" else _textos_ambiente(c["tags"])
        m = next((tx for tx in textos if matchea(keyword, tx)), None)
        if m:
            idx[c["id"]] = m
    if len(_CACHE_INDICE) >= MAX_CACHE_INDICE:
        _CACHE_INDICE.pop(next(iter(_CACHE_INDICE)), None)
    _CACHE_INDICE[key] = idx
    return idx


def _grupos_condicion(cond):
    """Devuelve (directas, proxys) de una condición.

    Compatibilidad hacia atrás: si viene el campo viejo "keywords" (schema anterior al
    sistema de dos niveles), se tratan todos como directas. Así el motor no se rompe si
    quedó una traducción vieja cacheada en algún lado."""
    if "keywords_directas" in cond or "keywords_proxy" in cond:
        return cond.get("keywords_directas", []) or [], cond.get("keywords_proxy", []) or []
    return cond.get("keywords", []) or [], []


def preparar_condiciones(condiciones, cafes):
    """Una vez por consulta: arma el índice de cada keyword y su fuerza.
    Devuelve, por condición, una lista de (keyword, indice, fuerza) ordenada por fuerza
    descendente, para que la primera que matchee ya sea la mejor evidencia disponible."""
    total = len(cafes)
    prep = []
    for cond in condiciones:
        tipo = cond.get("tipo", "ambiente")
        fila = []
        for kws, fuerza in ((_grupos_condicion(cond)[0], FUERZA_DIRECTA),
                            (_grupos_condicion(cond)[1], FUERZA_PROXY)):
            for k in kws:
                idx = indice_keyword(k, tipo, cafes)
                f = fuerza
                if (GUARDRAIL_DIRECTAS_ANCHAS and fuerza == FUERZA_DIRECTA
                        and total and len(idx) > GUARDRAIL_DIRECTAS_ANCHAS):
                    f = FUERZA_PROXY   # directa demasiado ancha: se degrada a proxy
                fila.append((k, idx, f))
        fila.sort(key=lambda x: -x[2])
        prep.append(fila)
    return prep


def evaluar_cafe(cafe, filtros, ahora=None, prep=None):
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
                 "cobertura": 1.0, "fuerza": 0.0, "nivel_evidencia": "sin_condiciones",
                 "excluido_por": None}

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
        prep = prep or []
        cid = cafe["id"]
        fuerzas = []
        for i, cond in enumerate(condiciones):
            tipo = cond.get("tipo", "ambiente")
            intencion = cond.get("intencion", "")
            # prep[i] viene ordenado por fuerza descendente, así que la PRIMERA que matchea
            # ya es la mejor evidencia que este café tiene para esta intención. Cortamos ahí.
            encontrado = None
            for k, idx, fuerza in (prep[i] if i < len(prep) else []):
                m = idx.get(cid)
                if m:
                    encontrado = (k, m, fuerza)
                    break
            if encontrado:
                # tupla de 4, igual que antes: app.py desempaqueta (tipo, intencion, k, tx)
                evidencia["cumplidas"].append((tipo, intencion, encontrado[0], encontrado[1]))
                fuerzas.append(encontrado[2])
            else:
                evidencia["faltantes"].append((tipo, intencion))
        evidencia["cobertura"] = len(evidencia["cumplidas"]) / len(condiciones)
        # Promedio sobre las CUMPLIDAS y no sobre el total: la cobertura ya penaliza las
        # faltantes; la fuerza mide qué tan buena es la evidencia que sí hay.
        evidencia["fuerza"] = (sum(fuerzas) / len(fuerzas)) if fuerzas else 0.0
        if fuerzas:
            if all(f == FUERZA_DIRECTA for f in fuerzas):
                evidencia["nivel_evidencia"] = "directa"
            elif all(f == FUERZA_PROXY for f in fuerzas):
                evidencia["nivel_evidencia"] = "proxy"
            else:
                evidencia["nivel_evidencia"] = "mixta"

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


# Orden de menor a mayor exigencia, para poder tomar el mínimo entre lo que dice la
# cobertura y lo que dice la calidad de la evidencia.
_ORDEN_NIVEL = ["sin_resultados", "aproximado", "parcial", "completo"]

# Techo que la calidad de la evidencia le pone al nivel reportado.
# Sacar la clave "mixta" si se prefiere que un café que cumple TODAS las condiciones se
# reporte como "completo" aunque alguna la cumpla por proxy (son ~3 consultas de 139).
TECHO_POR_EVIDENCIA = {
    "proxy": "aproximado",   # ninguna condición se cumplió con evidencia directa
    "mixta": "parcial",      # algunas sí y otras no
}


def _nivel_final(cobertura, nivel_evidencia):
    """Combina CUÁNTO se cumplió (cobertura) con QUÉ TAN BIEN se cumplió (evidencia).

    Sin esto, un café que cumple la única condición pedida gracias a un proxy genérico se
    reporta como match "completo". Caso real de producción: "Cafe para ir con amigas"
    devolvió los tres cafés con mejor score bayesiano de toda la base, ninguno con un solo
    tag sobre amigas, y los presentó como coincidencia exacta. La consulta era respondible
    (610 cafés tienen tags de amigas) y el sistema degradó en silencio a popularidad.

    Regla: la evidencia pone un techo al nivel.
      - toda la evidencia es proxy  -> como mucho "aproximado"
      - mezcla de directa y proxy   -> como mucho "parcial"
      - toda directa                -> sin techo

    No hace falta un caso especial para consultas de entidad específica ("japonés",
    "medialunas", "patio"): en esas el traductor emite keywords_proxy vacío, así que solo
    pueden cumplirse con evidencia directa y nunca caen en este techo. Las únicas que caen
    son las funcionales/subjetivas, que es exactamente donde "aproximado" es la etiqueta
    honesta."""
    nivel = _nivel_cobertura(cobertura)
    techo = TECHO_POR_EVIDENCIA.get(nivel_evidencia)
    if techo is None:
        return nivel
    return min(nivel, techo, key=_ORDEN_NIVEL.index)


# ==================== RANKING Y RESPUESTA ====================

def _keywords_producto_planas(condiciones):
    """Aplana los keywords de las condiciones tipo 'producto' en una sola lista, para
    _heroes_matcheados (que necesita una lista plana, no la estructura anidada).
    Directas primero: si el café tiene un hero que ES lo pedido, gana sobre uno que
    solo matchea un proxy. Usa _grupos_condicion, así que sirve con el schema nuevo y
    con el viejo."""
    directas, proxys = [], []
    for c in condiciones:
        if c.get("tipo") == "producto":
            d, p = _grupos_condicion(c)
            directas.extend(d)
            proxys.extend(p)
    return directas + proxys


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
            return (cobertura, max_int, max_menc, ev.get("fuerza", 0.0), cafe["score_bayes"])
        # rating_bayesiano, en tres escalones:
        #   1. cobertura  -> ¿cuántas de las intenciones cumple?
        #   2. fuerza     -> ¿qué tan buena es la evidencia de que las cumple?
        #   3. bayesiano  -> ¿qué tan confiable es el café?
        # La fuerza toma pocos valores discretos a propósito: los empates siguen existiendo
        # y el bayesiano sigue decidiendo adentro de cada escalón.
        return (cobertura, ev.get("fuerza", 0.0), cafe["score_bayes"])

    candidatos = sorted(candidatos, key=clave, reverse=True)

    # piso de reviews para consultas vagas (sin ningún keyword)
    if consulta_vaga:
        candidatos = [c for c in candidatos if c[0]["reviews"] >= MIN_REVIEWS_VAGAS]

    # piso general: cualquier señal de evidencia por encima del bayesiano hace subir cafés
    # sin volumen. Se aplica solo si quedan candidatos suficientes, para no vaciar una
    # búsqueda específica y legítima donde todos los matches son lugares chicos.
    if PISO_REVIEWS_GENERAL and not consulta_vaga:
        con_piso = [c for c in candidatos if c[0]["reviews"] >= PISO_REVIEWS_GENERAL]
        if len(con_piso) >= MAX_RESULTADOS:
            candidatos = con_piso

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
    # Defensa: una condición sin ningún keyword no se puede cumplir nunca y hundiría la
    # cobertura de todos los cafés. El prompt tiene instrucción de no generarlas, pero es
    # largo y a veces igual aparece una (visto en consultas de negación, donde lo rechazado
    # debería ir a keywords_excluir y termina como condición vacía). Se descartan acá.
    validas = [c for c in condiciones if any(_grupos_condicion(c))]
    if len(validas) != len(condiciones):
        # copia: no mutamos el dict de filtros que nos pasaron
        filtros = {**filtros, "condiciones": validas}
        condiciones = validas

    prep = preparar_condiciones(condiciones, cafes) if condiciones else []

    candidatos = []
    for cafe in cafes:
        ev = evaluar_cafe(cafe, filtros, ahora, prep)
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

    mejor = resultados[0][1]
    nivel = ("completo" if consulta_vaga
             else _nivel_final(mejor["cobertura"], mejor.get("nivel_evidencia")))
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
