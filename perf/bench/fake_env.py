"""Entorno falso para medir app.py sin red: geojson sintético (~3000 cafés) servido
en lugar del blob de Azure, y un Firestore en memoria con tags sintéticos.
Latencias de red simuladas configurables con BENCH_BLOB_MS / BENCH_FS_MS."""
import os, random, json, time, gzip, sys
import orjson

random.seed(42)
N = int(os.getenv('BENCH_N', '3000'))
BLOB_MS = int(os.getenv('BENCH_BLOB_MS', '0'))
FS_MS = int(os.getenv('BENCH_FS_MS', '0'))

BARRIOS = ['Palermo', 'Recoleta', 'Belgrano', 'Caballito', 'Almagro', 'Villa Crespo', 'San Telmo',
           'Colegiales', 'Núñez', 'Balvanera', 'Flores', 'Boedo', 'Chacarita', 'Villa Urquiza',
           'Retiro', 'San Nicolás', 'Monserrat', 'Puerto Madero', 'Villa del Parque', 'Saavedra']
DIAS = ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']
BOOLS_GJ = ['Permite mascotas', 'El café es de especialidad', 'Tiene pastelería artesanal',
            'Tiene comida vegetariana', 'Acceso silla de ruedas', 'Es cadena', 'No es cadena',
            'Popular', 'Delivery', 'Sirve brunch', 'Tiene opciones sin tacc', 'Espacio afuera',
            'Musica en vivo', 'Temática: Puesto de diario', 'Reservable', 'Tiene takeaway']
WORDS = ['Numa', 'Lattente', 'Cuervo', 'Tostado', 'Atiko', 'Martinelli', 'Birkin', 'Café', 'Bar',
         'Coffee', 'Roasters', 'Negro', 'Brew', 'Puerto', 'Luna', 'Sur', 'Norte', 'Casa', 'Flor',
         'Bakery', 'Mostaza', 'Canela', 'Tinto', 'Habitué', 'Origen', 'Molino', 'Nube']
PRODUCTOS = ['flat white', 'medialunas', 'cafe', 'roll de canela', 'tostado', 'cheesecake', 'latte',
             'cortado', 'brownie', 'alfajor', 'avocado toast', 'scones', 'budin', 'capuccino',
             'chipa', 'cookies', 'espresso', 'te', 'licuado', 'jugo de naranja', 'pan de masa madre']
AMB = ['tranquilo', 'luminoso', 'acogedor', 'pet friendly', 'mesas afuera', 'amplio', 'limpio',
       'calido', 'pequeno', 'comodo', 'wifi', 'enchufes', 'buena musica', 'ruidoso', 'moderno']
IDEAL = ['trabajar', 'estudiar', 'leer', 'charlar', 'primera cita', 'desayunar', 'merendar']

BASE = 'https://jsonbuscafe.blob.core.windows.net/contbuscafe/'


def _hora(h):
    return f'{h:02d}:00'


def make_cafe(i):
    rating = round(random.uniform(3.2, 5.0), 1)
    reviews = int(random.paretovariate(1.2) * 20)
    lat = -34.62 + random.uniform(-0.08, 0.08)
    lng = -58.44 + random.uniform(-0.08, 0.08)
    nombre = f"{random.choice(WORDS)} {random.choice(WORDS)} {i}"
    horarios = {}
    for d in DIAS:
        if random.random() < 0.85:
            horarios[d.lower()] = {'open': _hora(random.randint(7, 10)), 'close': _hora(random.randint(18, 23))}
        else:
            horarios[d.lower()] = {'open': None, 'close': None}
    return dict(id=f'ChIJ{i:06d}xxxxxxxxxxxxxxxxx', nombre=nombre, rating=rating, reviews=reviews,
                lat=lat, lng=lng, barrio=random.choice(BARRIOS), horarios=horarios,
                direccion=f'Av. Siempre Viva {random.randint(100, 9999)}, C1414 CABA, Argentina',
                web=random.choice(['', f'https://www.instagram.com/cafe{i}/', f'https://cafe{i}.com.ar/']),
                bools={b: random.random() < 0.35 for b in BOOLS_GJ})


CAFES = [make_cafe(i) for i in range(N)]


def icono(r):
    return BASE + ('markverde.svg' if r >= 4 else 'markbeige.svg')


def geojson():
    feats = []
    for c in CAFES:
        p = {'id': c['id'], 'Nombre': c['nombre'], 'Rating': c['rating'],
             'Cantidad Reviews': c['reviews'], 'Sitio Web': c['web'], 'Dirección': c['direccion'],
             'iconUrl': icono(c['rating']), 'Barrio': c['barrio']}
        for d in DIAS:
            h = c['horarios'][d.lower()]
            p[f'{d}_open'] = h['open']
            p[f'{d}_close'] = h['close']
        p.update(c['bools'])
        feats.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [c['lng'], c['lat']]},
                      'properties': p})
    return {'type': 'FeatureCollection', 'features': feats}


GEOJSON_BYTES = orjson.dumps(geojson())


def tags_for(i):
    if i % 8 == 0:
        return None
    return {
        'productos_hero': [{'producto': p, 'menciones': random.randint(2, 40), 'intensidad': random.randint(1, 3)}
                           for p in random.sample(PRODUCTOS, 4)],
        'productos_destacados': random.sample(PRODUCTOS, 6),
        'menciones_aisladas': random.sample(PRODUCTOS, 3),
        'ambiente_tags': random.sample(AMB, 6),
        'señas_distintivas': ['tiene un patio con plantas', 'barra de madera'],
        'ideal_para': random.sample(IDEAL, 3),
        'resumen': 'Un café de barrio con buena pastelería y ambiente tranquilo para trabajar.',
    }


# ---------------- mocks ----------------
class _Resp:
    def __init__(self, content):
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return orjson.loads(self.content)


def install():
    import requests
    _orig_get = requests.get

    def fake_get(url, *a, **k):
        if 'geojson_data_latest.json' in url:
            time.sleep(BLOB_MS / 1000)
            return _Resp(GEOJSON_BYTES)
        return _orig_get(url, *a, **k)
    requests.get = fake_get

    class Snap:
        def __init__(self, c, i):
            self.id = c['id']
            self._c, self._i = c, i

        def to_dict(self):
            c = self._c
            d = {'nombre': c['nombre'], 'barrio': c['barrio'], 'rating': c['rating'],
                 'cantidad_reviews': c['reviews'], 'horarios': c['horarios'], 'direccion': c['direccion'],
                 'sitio_web': c['web'], 'activo': True, 'tags': tags_for(self._i)}
            return d

    class Q:
        def where(self, *a, **k):
            return self

        def stream(self):
            time.sleep(FS_MS / 1000)
            for i, c in enumerate(CAFES):
                yield Snap(c, i)

    class DB:
        def collection(self, *_):
            return Q()

    import firebase_admin.firestore as fs
    fs.client = lambda *a, **k: DB()
