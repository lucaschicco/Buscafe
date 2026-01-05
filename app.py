#!/usr/bin/env python
# coding: utf-8

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_leaflet as dl
import pandas as pd
from dash_extensions.javascript import assign
#import dash_bootstrap_components as dbc
import numpy as np
from flask_compress import Compress
import json
import requests
import dash_loading_spinners as dls
from azure.storage.blob import BlobServiceClient
import os
from datetime import datetime
import orjson
import unicodedata


app = dash.Dash(__name__, title="Buscafes")
server = app.server  # Esto expone el servidor de Flask
app._favicon = ("coffee-solid.ico")
# Habilitar la compresión
Compress(server)

# Agregar el atributo lang al elemento <html>
CLIENT_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")

app.index_string = """
<!DOCTYPE html>
<html lang="es">
<head>
  {%metas%}
  <title>{%title%}</title>
  {%favicon%}
  {%css%}

  <!-- Preload del logo para mejorar LCP -->
  <link rel="preload" as="image" href="/assets/buscafes.png" fetchpriority="high">

  <!-- Preconnect a Carto basemaps para reducir latencia -->
  <link rel="preconnect" href="https://a.basemaps.cartocdn.com" crossorigin>
  <link rel="preconnect" href="https://b.basemaps.cartocdn.com" crossorigin>
  <link rel="preconnect" href="https://c.basemaps.cartocdn.com" crossorigin>

  <!-- Application Insights recomendado -->
  <script src="https://js.monitor.azure.com/scripts/b/ai.2.min.js" crossorigin="anonymous"></script>
  <script type="text/javascript">
    var appInsights = window.appInsights || new Microsoft.ApplicationInsights.ApplicationInsights({
      config: {
        connectionString: "__AI_CONN__",
        enableAutoRouteTracking: true
      }
    });
    appInsights.loadAppInsights();
    appInsights.trackPageView();
  </script>
</head>
<body>
  <div id="react-entry-point">{%app_entry%}</div>
  <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

# Reemplaza el placeholder por tu connection string sin romper las llaves de Dash/JS
app.index_string = app.index_string.replace("__AI_CONN__", CLIENT_CONN)


# URL del archivo JSON comprimido en Azure
url = 'https://jsonbuscafe.blob.core.windows.net/contbuscafe/geojson_data43.json'

# Traer el contenido
response = requests.get(url)

response.raise_for_status()  # lanza error si algo falló

# Cargar el contenido ya descomprimido en un diccionario Python
geojson_data = orjson.loads(response.content)

# Calcular latitud y longitud mín/máx desde el GeoJSON
latitudes = [feature['geometry']['coordinates'][1] for feature in geojson_data['features']]
longitudes = [feature['geometry']['coordinates'][0] for feature in geojson_data['features']]

lat_min, lat_max = min(latitudes), max(latitudes)
lon_min, lon_max = min(longitudes), max(longitudes)

with open('assets/cafeinit.svg', 'r') as file:
    svg_content = file.read()

# Obtener valores mínimos y máximos de latitud/longitud
lat_min = min(feature['geometry']['coordinates'][1] for feature in geojson_data['features'])
lat_max = max(feature['geometry']['coordinates'][1] for feature in geojson_data['features'])
lon_min = min(feature['geometry']['coordinates'][0] for feature in geojson_data['features'])
lon_max = max(feature['geometry']['coordinates'][0] for feature in geojson_data['features'])

# Obtener valores únicos para dropdowns
barrios_unicos = sorted(set(feature['properties'].get('Barrio', 'Desconocido') for feature in geojson_data['features']))
nombres_unicos = sorted(set(feature['properties'].get('Nombre', 'Desconocido') for feature in geojson_data['features']))

# Obtener valores mínimo y máximo de rating (evita errores con `.get()` y valores por defecto)
ratings = [feature['properties'].get('Rating', 0) for feature in geojson_data['features']]
rating_min = min(ratings)
rating_max = max(ratings)

def _sort_key(s):
    if not isinstance(s, str):
        return ""
    # quita acentos y pasa a minúsculas
    s_norm = unicodedata.normalize("NFD", s)
    s_norm = "".join(ch for ch in s_norm if unicodedata.category(ch) != "Mn")
    return s_norm.casefold()

barrios_unicos = sorted(
    {f['properties'].get('Barrio', 'Desconocido').strip()
     for f in geojson_data['features']},
    key=_sort_key
)


# Layout de la aplicación
app.layout = html.Div([
    dcc.Store(id='initial-load', data=True),
    dcc.Store(id='clientside-store-data', data=geojson_data),  # GeoJSON en el frontend
    dcc.Store(id='info-visible', data=False),

    # Botón flotante para abrir el panel de sugerencias
    html.Button(
        "☕➕",
        id="btn-abrir-panel",
        className="custom-floating-button",
        title="Sugerir cafetería"
    ),

    # Panel flotante para sugerir cafeterías
    html.Div([
        html.Div([
            html.Button("❌", id="btn-cerrar-panel", className="close-button"),
            html.H3("Informa cafetería faltante", style={'text-align': 'center'}),
            dcc.Input(id="nombre-cafeteria", type="text", placeholder="Nombre de la cafetería *", className="custom-input"),
            dcc.Input(id="direccion-cafeteria", type="text", placeholder="Dirección (opcional)", className="custom-input"),
            html.Button("Enviar", id="enviar-sugerencia", className="custom-button"),
            html.Div(id="mensaje-confirmacion", style={"margin-top": "10px", "color": "green"})
        ], className="suggestion-panel"),
    ], id="panel-sugerencia", style={"display": "none"}),

    # Botón toggle filtros
    html.Button(
        "Mostrar/Ocultar Filtros",
        id='toggle-button',
        className='custom-toggle-button',
        n_clicks=0
    ),

    # Spinner inicial
    html.Div([
        dls.Custom(
            svg=svg_content,
            id='initial-loading-spinner',
        )
    ], id='loading-div', style={
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'display': 'flex',
        'justify-content': 'center',
        'align-items': 'center',
        'background-color': 'rgba(255, 255, 255, 1)',
        'z-index': '3000'
    }),

    # Panel de filtros (arranca oculto con clase 'hidden')
    html.Div(
        id='filters-panel',
        className='controls-container hidden',
        children=[
            html.Div([
                html.Img(src='/assets/buscafes.png',
                         style={'width': '80%', 'height': 'auto', 'margin-bottom': '0px', 'margin-top': '10px'}),
                html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': '10px auto'})
            ], style={'display': 'flex', 'align-items': 'center', 'flex-direction': 'column'}),

            dcc.Dropdown(
                id='barrio-dropdown',
                options=[{'label': b, 'value': b} for b in barrios_unicos],
                value=None,
                placeholder="Selecciona un barrio",
                className='custom-dropdown',
                searchable=False,
                multi=True
            )
            ,

            dcc.Dropdown(
                id='feature-filter',
                options=[
                    {'label': 'Tiene pasteleria casera', 'value': 'Tiene pastelería artesanal'},
                    {'label': 'El café es de especialidad', 'value': 'El café es de especialidad'},
                    {'label': 'Tiene Delivery', 'value': 'Delivery'},
                    {'label': 'Tiene takeaway', 'value': 'Tiene takeaway'},
                    #{'label': 'Para comer en el lugar', 'value': 'Comer en lugar'},
                    {'label': 'Temática: Puesto de diario', 'value': 'Temática: Puesto de diario'},
                    #{'label': 'Desayuno', 'value': 'Desayuno'},
                    #{'label': 'Almuerzo', 'value': 'Almuerzo'},
                    #{'label': 'Cena', 'value': 'Cena'},
                    {'label': 'Brunch', 'value': 'Sirve brunch'},
                    #{'label': 'Sirve Vino', 'value': 'Sirve Vino'},
                    #{'label': 'Sirve Cerveza', 'value': 'Sirve cerveza'},
                    #{'label': 'Sirve postre', 'value': 'Sirve postre'},
                    {'label': 'Con espacio afuera', 'value': 'Espacio afuera'},
                    {'label': 'Es cadena', 'value': 'Es cadena'},
                    {'label': 'No es cadena', 'value': 'No es cadena'},
                    {'label': 'Musica en vivo', 'value': 'Musica en vivo'},
                    {'label': 'Reservable', 'value': 'Reservable'},
                    {'label': 'Tiene comida vegeteriana', 'value': 'Tiene comida vegetariana'},
                    {'label': 'Permite mascotas', 'value': 'Permite mascotas'},
                    {'label': 'Acceso silla de ruedas', 'value': 'Acceso silla de ruedas'},
                    {'label': 'Tiene opciones sin tacc', 'value': 'Tiene opciones sin tacc'}
                ],
                value=[],
                searchable=False,
                multi=True,
                placeholder="Filtrá por Características...",
                className='custom-dropdown'
            ),

            dcc.Dropdown(
                id='dias-apertura-filter',
                options=[{'label': day, 'value': day} for day in
                         ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']],
                value=[],
                multi=True,
                searchable=False,
                placeholder="Filtrá por Días de Apertura...",
                className='custom-dropdown'
            ),

            dcc.Dropdown(
                id='nombre-filter',
                options=[],           # empieza vacío, lo llenamos desde clientside
                value=[],             # multi
                multi=True,
                placeholder="Busca por Nombre...",
                searchable=True,
                className='custom-dropdown',
                style={'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)', 'margin-top': '3px'}
            ),

            html.Label("RATING",
                       style={'color': '#fffff5', 'font-weight': 'bold', 'margin-top': '5px',
                              'margin-bottom': '5px', 'margin-left': '40px'}),

            dcc.RangeSlider(
                id='rating-slider',
                min=rating_min,
                max=rating_max,
                step=0.1,
                marks={str(rating): {'label': str(rating)}
                       for rating in range(int(rating_min), int(rating_max) + 1)},
                value=[rating_min, rating_max],
                tooltip={"placement": "bottom", "always_visible": True},
                className='custom-slider'
            ),

            html.Div(className='color-legend', children=[
                html.Div(className='color-1'),
                html.Div(className='color-2'),
                html.Div(className='color-3'),
                html.Div(className='color-4'),
                html.Div(className='color-5')
            ]),

            dcc.Dropdown(
                id='map-style-dropdown',
                options=[
                    {'label': 'Mapa tradicional', 'value': 'osm'},
                    {'label': 'Modo Claro', 'value': 'carto-positron'},
                    {'label': 'Modo Oscuro', 'value': 'carto-darkmatter'}
                ],
                value='carto-positron',
                placeholder="Estilo de mapa",
                searchable=False,
                className='custom-dropdown',
                style={'margin-top': '15px'},
            ),

            html.Div(id='output-container-slider'),

            html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': 'auto'}),

            html.Div([
                html.A(
                    html.Img(
                        src='https://jsonbuscafe.blob.core.windows.net/contbuscafe/envelope-solid.svg',
                        style={'width': '18px', 'height': '18px',
                               'filter': 'invert(38%) sepia(78%) saturate(292%) hue-rotate(94deg) brightness(97%) contrast(101%)'}
                    ),
                    href="mailto:buscafes.ai@gmail.com",
                    className='contact-button-circle',
                    style={}
                ),
                html.A(
                    html.Img(
                        src='https://jsonbuscafe.blob.core.windows.net/contbuscafe/instagram-brands-solid.svg',
                        style={'width': '18px', 'height': '18px',
                               'filter': 'invert(38%) sepia(78%) saturate(292%) hue-rotate(94deg) brightness(97%) contrast(101%)'}
                    ),
                    href="https://www.instagram.com/buscafes.ai",
                    className='contact-button-circle',
                    style={}
                )
            ], style={'display': 'flex', 'justify-content': 'center', 'align-items': 'center'}),
        ]
    ),

    # Mapa
    dl.Map(
        id='map',
        style={'width': '100%', 'height': '100vh', 'max-height': '100vh'},
        center=[-34.598, -58.436],
        zoomControl=False,
        bounds=[[lat_min, lon_min], [lat_max, lon_max]],
        zoom=12,
        children=[
            dl.TileLayer(
                id="base-layer",
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
                detectRetina=False
            ),
            dl.LocateControl(locateOptions={'enableHighAccuracy': True, 'setView': False},
                             position='topright', showPopup=False),
            dl.ZoomControl(position='topright'),
            dl.GeoJSON(
                id="geojson-layer",
                options=dict(
                    pointToLayer=assign("""
                        function(feature, latlng){
                            let iconUrl = feature.properties.iconUrl;
                            let marker = L.marker(latlng, {
                                icon: L.icon({
                                    iconUrl: iconUrl,
                                    iconSize: [18, 27],
                                    iconAnchor: [12, 23],
                                    popupAnchor: [1, -34],
                                    shadowSize: [0, 0]
                                })
                            }).bindTooltip(feature.properties.tooltipContent, {
                                className: 'marker-tooltip'
                            });

                            marker.on('click', function(){
                                var popup = L.popup({closeOnMove: false})
                                    .setLatLng(latlng)
                                    .setContent(feature.properties.popupContent)
                                    .openOn(marker._map);

                                var zoomLevel = marker._map.getZoom();
                                var latOffset = 0.05 / Math.pow(2, zoomLevel - 12);
                                marker._map.panTo([latlng.lat + latOffset, latlng.lng], {animate: true});
                            });
                            return marker;
                        }
                    """)
                ),
                zoomToBoundsOnClick=True,
            )
        ]
    ),

    # Mensaje de zoom
    html.Div([
        "Haz zoom para ver más cafeterías",
        html.Button('✖', id='close-message-button', style={
            'background': 'none',
            'border': 'none',
            'color': 'black',
            'font-size': '10px',
            'cursor': 'pointer',
            'position': 'absolute',
            'right': '1px',
            'top': '1px'
        })
    ],
        id='zoom-message',
        style={
            'position': 'fixed',
            'bottom': '30px',
            'left': '50%',
            'transform': 'translateX(-50%)',
            'background-color': '#d3d3d3',
            'color': 'black',
            'padding': '10px 20px',
            'border-radius': '8px',
            'box-shadow': '0px 4px 10px rgba(0, 0, 0, 0.1)',
            'font-weight': 'bold',
            'z-index': '2000',
            'font-size': '14px',
            'text-align': 'center',
            'width': 'auto',
            'max-width': '80%'
        }
    ),
])




@app.callback(
    Output('loading-div', 'style'),  # Cambia la visibilidad del spinner
    Input('geojson-layer', 'data'),  # Se dispara cuando los datos están listos
    prevent_initial_call=True
)
def hide_spinner_on_load(data):
    # Ocultar el spinner cuando el mapa se haya cargado
    if data:
        return {'display': 'none'}
    return {'position': 'fixed', 'top': '0', 'left': '0', 'width': '100%', 'height': '100%', 'display': 'flex', 'justify-content': 'center', 'align-items': 'center', 'background-color': 'rgba(255, 255, 255, 0.8)', 'z-index': '2000'}




# Configuración de Azure Blob Storage
BLOB_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER = "contbuscafe"  # Contenedor en tu cuenta de almacenamiento
BLOB_FILENAME = "sugerencias.json"  # Archivo donde se guardarán las sugerencias




# Callback para guardar la sugerencia en Azure Blob Storage
@app.callback(
    Output("mensaje-confirmacion", "children"),
    Input("enviar-sugerencia", "n_clicks"),
    State("nombre-cafeteria", "value"),
    State("direccion-cafeteria", "value"),
    prevent_initial_call=True
)
def guardar_sugerencia(n_clicks, nombre, direccion):
    if not nombre:
        return "❌ El nombre de la cafetería es obligatorio."

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sugerencia = {
        "nombre": nombre,
        "direccion": direccion or "No especificado",
        "timestamp": timestamp
    }

    try:
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
        filename = f"sugerencia_{timestamp}.json"
        blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER, blob=filename)
        blob_client.upload_blob(json.dumps(sugerencia, indent=2), overwrite=True)
        return "✅ ¡Gracias! Sugerencia guardada con éxito."
    except Exception as e:
        return f"❌ Error al guardar la sugerencia: {str(e)}"



app.clientside_callback(
    """
        function(barrios, features, rating, dias, nombre, bounds, zoom, store) {
    
        if (!store || !store.features) {
            return {type:'FeatureCollection', features:[]};
        }
    
        const ctx = dash_clientside.callback_context;
        const triggered = ctx.triggered[0]?.prop_id;
    
        let feats = store.features;
    
        // filtros comunes
        if (barrios?.length) {
            feats = feats.filter(f => barrios.includes(f.properties.Barrio));
        }
        if (features?.length) {
            feats = feats.filter(f => features.every(ff => f.properties[ff] === true));
        }
        if (rating?.length === 2) {
            feats = feats.filter(f =>
                f.properties.Rating >= rating[0] &&
                f.properties.Rating <= rating[1]
            );
        }
        if (dias?.length) {
            feats = feats.filter(f =>
                dias.every(d => f.properties[d + '_open'] && f.properties[d + '_close'])
            );
        }
    
        // 🔒 CASO NOMBRE: PRIORIDAD ABSOLUTA
        if (nombre?.length) {
            return {
                type: 'FeatureCollection',
                features: feats.filter(f => nombre.includes(f.properties.Nombre))
            };
        }
    
        // recién acá aplicar zoom / bounds
        if (zoom < 14) {
            const reviews = feats
                .map(f => f.properties['Cantidad Reviews'] || 0)
                .sort((a,b)=>b-a);
            const t = reviews[Math.floor(reviews.length * 0.07)] || 0;
            return {
                type:'FeatureCollection',
                features: feats.filter(f => f.properties['Cantidad Reviews'] >= t)
            };
        }
    
        if (bounds?.length === 2) {
            const [sw, ne] = bounds;
            feats = feats.filter(f => {
                const [lng, lat] = f.geometry.coordinates;
                return lat>=sw[0] && lat<=ne[0] && lng>=sw[1] && lng<=ne[1];
            });
        }
    
        return {type:'FeatureCollection', features: feats};
    }
    """,
    Output('geojson-layer','data'),
    [
        Input('barrio-dropdown','value'),
        Input('feature-filter','value'),
        Input('rating-slider','value'),
        Input('dias-apertura-filter','value'),
        Input('nombre-filter','value'),
        Input('map','bounds'),
        Input('map','zoom')
    ],
    State('clientside-store-data','data')
)



@app.callback(
    Output('nombre-filter', 'options'),
    Input('nombre-filter', 'search_value'),
    State('nombre-filter', 'value')  # 👈 Agregamos el estado actual
)
def update_nombre_options(search_value, current_value):
    # Si hay valores seleccionados, mantener esas opciones visibles
    if current_value:
        selected_options = [{'label': n, 'value': n} for n in (current_value if isinstance(current_value, list) else [current_value])]
        
        # Si no hay búsqueda, solo mostrar los seleccionados
        if not search_value or len(search_value) < 2:
            return selected_options
        
        # Si hay búsqueda, combinar seleccionados + resultados
        s = search_value.lower()
        results = [n for n in nombres_unicos if s in n.lower() and n not in (current_value if isinstance(current_value, list) else [current_value])]
        return selected_options + [{'label': n, 'value': n} for n in results[:50]]
    
    # Comportamiento original cuando no hay nada seleccionado
    if not search_value or len(search_value) < 2:
        return []
    
    s = search_value.lower()
    results = [n for n in nombres_unicos if s in n.lower()]
    return [{'label': n, 'value': n} for n in results[:50]]



@app.callback(
    Output('filters-panel', 'className'),
    Input('toggle-button', 'n_clicks'),
    State('filters-panel', 'className')
)
def toggle_filters_panel(n_clicks, current_class):
    if not n_clicks:
        return "controls-container hidden"
    if "hidden" in current_class:
        return "controls-container visible"
    return "controls-container hidden"



@app.callback(
    Output("panel-sugerencia", "style"),
    Input("btn-abrir-panel", "n_clicks"),
    Input("btn-cerrar-panel", "n_clicks"),
    State("panel-sugerencia", "style"),
    prevent_initial_call=True
)
def toggle_suggestion_panel(n_clicks_abrir, n_clicks_cerrar, current_style):
    ctx = dash.callback_context  # Ver qué botón fue clickeado

    if not ctx.triggered:
        return current_style  # Si no hay clics, no hacer nada

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == "btn-abrir-panel":
        # Si el panel está visible, ocultarlo. Si está oculto, mostrarlo.
        return {"display": "none"} if current_style["display"] == "block" else {"display": "block"}

    elif triggered_id == "btn-cerrar-panel":
        return {"display": "none"}  # Siempre oculta el panel si se presiona la cruz

    return current_style  # Mantener el estado actual en cualquier otro caso



@app.callback(
    Output('zoom-message', 'style'),
    Input('close-message-button', 'n_clicks'),
    State('zoom-message', 'style'),
    prevent_initial_call=True
)
def hide_message(n_clicks, current_style):
    if n_clicks:
        # Cambiar el estilo para ocultar el mensaje
        current_style['display'] = 'none'
    return current_style


@app.callback(
    Output('base-layer', 'url'),
    Input('map-style-dropdown', 'value')
)
def update_map_style(map_style):
    style_urls = {
        'osm': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    }

    # Default
    return style_urls.get(map_style, style_urls['carto-positron'])
  
    
# Ejecuta la aplicación Dash
if __name__ == "__main__":
    app.run_server(debug=False)
