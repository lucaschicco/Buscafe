import sys, re
STAGE = sys.argv[1]  # 'A' = spinner+debounce+preload ; 'B' = A + sin lookup inline
p = 'app.py'; s = open(p, encoding='utf-8').read()
def rep(old, new, count=1):
    global s
    assert s.count(old) >= 1, old[:80]
    s = s.replace(old, new, count)

# 1) spinner: callback Python (sube el geojson) -> clientside
old_cb = s[s.index("@app.callback(\n    Output('loading-div', 'style'),"):s.index("BLOB_CONNECTION_STRING")]
rep(old_cb, '''app.clientside_callback(
    """function(gj, store) {
        if ((gj && gj.features && gj.features.length) || store) return {display: 'none'};
        return window.dash_clientside.no_update;
    }""",
    Output('loading-div', 'style'),
    Input('geojson-layer', 'data'),
    Input('clientside-store-data', 'data'),
    prevent_initial_call=True
)

''')
# 2) sin debounce de 700ms en la carga inicial (trigger = llegada del store)
rep("const delay = isMapMove ? 0 : 700;",
    "const isInitial = triggered.includes('clientside-store-data') || !triggered;\n        const delay = (isMapMove || isInitial) ? 0 : 700;")
# 3) bajar el geojson en paralelo a los bundles de Dash
rep('<link rel="preload" as="image" href="/assets/buscafes_header2.png" fetchpriority="high">',
    '<link rel="preload" as="fetch" href="/api/geojson" crossorigin="anonymous" fetchpriority="high">\n  <link rel="preload" as="image" href="/assets/buscafes_header2.png" fetchpriority="high">')
if STAGE == 'B':
    # 4) lookup inline (614 KB en el HTML) -> se arma en el cliente desde el geojson
    rep("window.buscafesLookup = __GEO_LOOKUP__;", "window.buscafesLookup = window.buscafesLookup || {};")
    rep("""        const data = await res.json();
        return data;""", """        const data = await res.json();
        const lk = {};
        for (const f of data.features) {
            const p = f.properties, c = f.geometry.coordinates;
            lk[p.id] = {nombre: p.Nombre, dir: p['Dirección'], barrio: p.Barrio, web: p['Sitio Web'] || '', lat: c[1], lng: c[0]};
        }
        window.buscafesLookup = lk;
        return data;""")
    # el deep link /?cafe=<id> corre antes de que llegue el geojson: resolver el café adentro del intervalo
    rep("""        const info = window.buscafesLookup[cafeId];
        if (!info || info.lat == null) return;
    
        let intentos = 0;
        const timer = setInterval(function() {
            intentos++;
            if (intentos > 40) { clearInterval(timer); return; }  // corta a los ~16s
    """, """        let info = null;
        let intentos = 0;
        const timer = setInterval(function() {
            intentos++;
            if (intentos > 40) { clearInterval(timer); return; }  // corta a los ~16s
            if (!info) {
                info = (window.buscafesLookup || {})[cafeId];
                if (!info) return;  // todavía no llegó el geojson
                if (info.lat == null) { clearInterval(timer); return; }
            }
    """)
open(p, 'w', encoding='utf-8').write(s)
print('patched', STAGE)
