"""
buscador_nombres.py
Lookup por nombre de café, ANTES de mandar la consulta a Sonnet.

Idea: si la persona tipea "Numa" o "Martinelli", no es una búsqueda por atributos,
es Google Maps. Se resuelve con un índice local: cero costo, cero latencia, y no
tiene por qué descontar uso.

Uso:
    from buscador_nombres import construir_indice, buscar_por_nombre, terminos_desde_vocab

    IDX = construir_indice(cafes, barrios=vocab['barrios'],
                           terminos_vocab=terminos_desde_vocab(vocab))
    r = buscar_por_nombre('numa', IDX)
    # r['tipo'] in {'cafe', 'ambiguo', None}
    #   'cafe'    -> match exacto de nombre o núcleo, y no es término del vocabulario:
    #                mostrar ficha(s) directamente, no llamar a Sonnet
    #   'ambiguo' -> el texto es nombre Y término del vocabulario (ej. "Kissaten", "Patio"),
    #                o el match fue aproximado (typo, contención): mostrar "¿Buscabas X?"
    #                + seguir con la búsqueda normal. Si Sonnet da off_topic / sin_resultados,
    #                queda solo la sugerencia.
    #   None      -> no es un nombre: flujo normal con Sonnet

`cafes`: lista de dicts con al menos 'id' y 'nombre' (opcionales: 'barrio', 'reviews').
Sirve CAFES_BUSCADOR, pero conviene indexar TODOS los activos del mapa, también los
que no tienen tags: si alguien busca un café publicado, tiene que encontrarlo.

Diseño del matching (en orden):
  1. Consulta larga (> MAX_PALABRAS) o con marcadores de intención ("con", "para",
     "cerca"...) -> no es nombre, salvo que coincida EXACTO con un nombre completo.
  2. Exacto contra el nombre completo normalizado.
  3. Exacto contra el NÚCLEO: el nombre sin palabras genéricas (café, coffee,
     specialty, bakery...) ni barrios, y solo la parte antes de " - " / "|" / ",".
     "Numa Cafe" -> "numa"; "Atiko - Villa del Parque" -> "atiko";
     "Martinelli Caffe & Pasticceria" -> "martinelli".
     Si el núcleo queda vacío ("Cafetería Flores") ese café no se indexa por núcleo:
     "flores" es un barrio y tiene que seguir yendo a Sonnet.
  4. Contención: todos los tokens del núcleo están en la consulta y sobra como mucho
     1 token ("somos numa cafe" -> numa).
  5. Fuzzy (solo núcleos de >= 4 letras): typos tipo "tinos" -> "tino".
  Después: si lo que matcheó también es barrio o término del vocabulario -> 'ambiguo'.
"""

import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches

MAX_PALABRAS = 4
UMBRAL_FUZZY = 0.85
MIN_LARGO_FUZZY = 4

GENERICAS = {
    'cafe', 'cafes', 'caffe', 'caffee', 'cafeteria', 'cafeterias', 'coffee', 'coffees',
    'specialty', 'especialidad', 'shop', 'store', 'bar', 'bakery', 'panaderia',
    'pasteleria', 'pasticceria', 'confiteria', 'tostador', 'tostadores', 'roasters',
    'roastery', 'brunch', 'gelato', 'co', 'company', 'cia', 'sucursal', 'casa',
    'de', 'del', 'la', 'el', 'los', 'las', 'y', 'e', 'the', 'and', 'en', 'by',
}
# palabras que delatan una búsqueda por atributos, no un nombre
MARCADORES_INTENCION = {
    'con', 'para', 'sin', 'cerca', 'abierto', 'abierta', 'abiertos', 'que', 'donde',
    'mejor', 'mejores', 'buen', 'buena', 'buenos', 'buenas', 'quiero', 'busco',
    'recomendame', 'recomiendame', 'algun', 'alguna', 'lugar', 'lugares', 'por', 'en',
}
# palabras comunes que no alcanzan como núcleo por sí solas:
# "La Nueva Recoleta" -> "nueva" haría que "cafeterias nuevas" devuelva ese café
NUCLEOS_DEBILES = {
    'nueva', 'nuevo', 'nuevas', 'nuevos', 'vieja', 'viejo', 'antiguo', 'antigua', 'gran',
    'mi', 'tu', 'su', 'punto', 'esquina', 'rincon', 'parque', 'plaza', 'centro', 'barrio',
    'real', 'buen', 'buena', 'dulce', 'rico', 'rica', 'social', 'club', 'mercado',
}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _quitar_frases(texto, frases):
    """Saca frases completas (ej. barrios de varias palabras) respetando límites de palabra."""
    for f in frases:
        if f and f in texto:
            texto = re.sub(r'\b' + re.escape(f) + r'\b', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def nucleo(nombre, barrios_norm):
    principal = re.split(r'\s[-|–]\s|,|\|', str(nombre or ''))[0]
    t = _quitar_frases(norm(principal), barrios_norm)
    return ' '.join(w for w in t.split() if w not in GENERICAS)


def terminos_desde_vocab(obj):
    """Junta todos los strings de vocabulario_buscador.json (cualquier estructura)."""
    out = set()
    if isinstance(obj, str):
        out.add(norm(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out |= terminos_desde_vocab(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            out |= terminos_desde_vocab(v)
    return {t for t in out if t}


def construir_indice(cafes, barrios=(), terminos_vocab=()):
    # barrios ordenados de más largo a más corto: "villa del parque" antes que "parque"
    barrios_norm = sorted({norm(b) for b in barrios if b}, key=len, reverse=True)
    por_completo, por_nucleo, info = {}, {}, {}
    for c in cafes:
        cid, nom = c.get('id'), c.get('nombre')
        if not cid or not nom:
            continue
        info[cid] = c
        por_completo.setdefault(norm(nom), set()).add(cid)
        nu = nucleo(nom, barrios_norm)
        if nu and nu not in NUCLEOS_DEBILES:
            por_nucleo.setdefault(nu, set()).add(cid)
    return {
        'por_completo': por_completo,
        'por_nucleo': por_nucleo,
        'nucleos_fuzzy': [n for n in por_nucleo if len(n.replace(' ', '')) >= MIN_LARGO_FUZZY],
        'info': info,
        'barrios': set(barrios_norm),
        'vocab': set(terminos_vocab),
    }


def _ordenar(ids, idx):
    cafes = [idx['info'][i] for i in ids]
    return sorted(cafes, key=lambda c: -(c.get('reviews') or c.get('cantidad_reviews') or 0))


def _resultado(ids, idx, via, matcheo, q):
    # contención y fuzzy nunca son autoritativos: con nombres de cafés que son palabras
    # comunes ("Cake & Coffee", "Barto", "Caffe Vergnano") generan falsos positivos
    # ("carrot cake", "barato", "vegano"). Se muestran como sugerencia + búsqueda normal.
    es_termino = (via in ('contencion', 'fuzzy')
                  or matcheo in idx['barrios'] or matcheo in idx['vocab']
                  or q in idx['barrios'] or q in idx['vocab'])
    return {
        'tipo': 'ambiguo' if es_termino else 'cafe',
        'cafes': _ordenar(ids, idx),
        'via': via,          # exacto | nucleo | contencion | fuzzy (para loguear/auditar)
        'matcheo': matcheo,
    }


def buscar_por_nombre(consulta, idx):
    q = norm(consulta)
    vacio = {'tipo': None, 'cafes': [], 'via': None, 'matcheo': None}
    if not q:
        return vacio

    # 2. nombre completo exacto: gana siempre, aunque la consulta sea larga
    if q in idx['por_completo']:
        return _resultado(idx['por_completo'][q], idx, 'exacto', q, q)

    tokens = q.split()
    if len(tokens) > MAX_PALABRAS or MARCADORES_INTENCION & set(tokens):
        return vacio
    if q in idx['barrios']:
        return vacio  # "Villa del Parque", "Boedo": búsqueda por barrio, va a Sonnet

    # la consulta pasa por el mismo recorte que los nombres:
    # "numa cafe" -> "numa"; "osvaldo recoleta" -> "osvaldo"
    sin_barrio = _quitar_frases(q, sorted(idx['barrios'], key=len, reverse=True))
    qn = ' '.join(w for w in sin_barrio.split() if w not in GENERICAS)
    if not qn:
        return vacio  # "cafe", "cafeteria de especialidad": no es un nombre

    # 3. núcleo exacto
    if qn in idx['por_nucleo']:
        ids = set(idx['por_nucleo'][qn])
        if len(qn) >= 3:  # sucursales con sufijo: "Nica Mercado", "Nica Distrito"
            for n, otros in idx['por_nucleo'].items():
                if n.startswith(qn + ' ') and len(n.split()) == len(qn.split()) + 1:
                    ids |= otros
        return _resultado(ids, idx, 'nucleo', qn, q)

    # 4. contención: el núcleo entero está en la consulta, sobra a lo sumo 1 token
    qset = set(qn.split())
    candidatos = [(n, ids) for n, ids in idx['por_nucleo'].items()
                  if set(n.split()) <= qset and len(qset) - len(n.split()) <= 1]
    if candidatos:
        largo = max(len(n.split()) for n, _ in candidatos)  # el núcleo más específico
        ids = set().union(*(ids for n, ids in candidatos if len(n.split()) == largo))
        mejor = next(n for n, _ in candidatos if len(n.split()) == largo)
        return _resultado(ids, idx, 'contencion', mejor, q)

    # 5. fuzzy (typos), solo consultas no triviales
    if len(qn.replace(' ', '')) >= MIN_LARGO_FUZZY:
        cerca = [n for n in get_close_matches(qn, idx['nucleos_fuzzy'], n=5, cutoff=UMBRAL_FUZZY)
                 if n[0] == qn[0]][:3]  # "gloria" no debe caer en "loria"
        if cerca:
            top = SequenceMatcher(None, qn, cerca[0]).ratio()
            ids = set().union(*(idx['por_nucleo'][n] for n in cerca
                                if SequenceMatcher(None, qn, n).ratio() >= top - 0.02))
            return _resultado(ids, idx, 'fuzzy', cerca[0], q)

    return vacio


def parece_nombre(consulta, idx):
    """True si la consulta tiene forma de nombre propio aunque no esté en la base
    ("Fedora", "Zulu Haus"). Para el endpoint: si esto da True, buscar_por_nombre no
    encontró nada y Sonnet devuelve off_topic/sin_resultados, la respuesta correcta es
    "ese café todavía no lo tengo en el mapa" (modo cafe_no_encontrado), no off_topic."""
    q = norm(consulta)
    tokens = q.split()
    if not tokens or len(tokens) > MAX_PALABRAS:
        return False
    if MARCADORES_INTENCION & set(tokens) or re.search(r'\d', q):
        return False  # intención, o dirección ("Aizpurua 3535")
    if q in idx['barrios'] or q in idx['vocab']:
        return False
    return any(w not in GENERICAS for w in tokens)
