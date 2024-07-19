#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
import openpyxl
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from flask_caching import Cache

# Crear la aplicación Dash
external_stylesheets = [dbc.themes.BOOTSTRAP, 
                        'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',
                       'https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
# Asignar la aplicación Dash al objeto 'server'
server = app.server
# Configuración del caché
cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',  # Puedes usar 'redis' si prefieres usar Redis
    'CACHE_DEFAULT_TIMEOUT': 300  # Tiempo en segundos que los datos permanecerán en caché
})
# Función para cargar los datos con caché

@cache.memoize()
def load_data():
    url = "https://raw.githubusercontent.com/lucaschicco/MiCafe/main/base_todos_barrios_vf.xlsx"
    response = requests.get(url)
    df = pd.read_excel(response.content)
    return df
df2 = load_data()

# Crear una función para analizar los horarios de apertura
def parse_hours(hours):
    if pd.isna(hours):
        return None, None
    open_time, close_time = hours.split('-')
    open_time = open_time.strip()
    close_time = close_time.strip()
    return pd.to_datetime(open_time, format='%H:%M').strftime('%H:%M'), pd.to_datetime(close_time, format='%H:%M').strftime('%H:%M')
    
# Aplicar la función a cada columna de día
for day in ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']:
    df2[[f'{day}_open', f'{day}_close']] = df2[day].apply(lambda x: pd.Series(parse_hours(x)))
    
# Eliminar las columnas originales de los días
df2.drop(columns=['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado'], inplace=True)


app.layout = html.Div(id="root", children=[
    dcc.Location(id='url', refresh=True),
    dcc.Store(id='panel-visible', data=False),
    dcc.Store(id='info-visible', data=False),
    dcc.Store(id='current-location-store'),
    dcc.Store(id='filtered-data'),
    html.Button("Filtros", id='toggle-button', className='custom-toggle-button', n_clicks=0),
    html.Div([
        html.Div([
            html.Img(src='/assets/buscafes.png', style={'width': '80%', 'height': 'auto', 'margin-bottom': '0px', 'margin-top': '10px'}),
            html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': '10px auto'})  # Línea blanca superior
        ], style={'display': 'flex', 'align-items': 'center', 'flex-direction': 'column'}),
        dcc.Dropdown(
            id='feature-filter',
            options=[
                {'label': 'Tiene Delivery', 'value': 'Delivery'},
                {'label': 'Tiene Takeaway', 'value': 'Tiene takeaway'},
                {'label': 'Para comer en el lugar', 'value': 'Comer en lugar'},
                {'label': 'Desayuno', 'value': 'Desayuno'},
                {'label': 'Almuerzo', 'value': 'Almuerzo'},
                {'label': 'Cena', 'value': 'Cena'},
                {'label': 'Brunch', 'value': 'Brunch'},
                {'label': 'Vino', 'value': 'Vino'},
                {'label': 'Con espacio afuera', 'value': 'Espacio afuera'},
                {'label': 'Accesible para silla de ruedas', 'value': 'Accesible para silla de ruedas'},
                {'label': 'Sirve postre', 'value': 'Sirve postre'},
                {'label': 'Musica en vivo', 'value': 'Musica en vivo'},    
                {'label': 'Reservable', 'value': 'Reservable'}
            ],
            value=[],
            multi=True,
            optionHeight=30,
            placeholder="Filtrá por Características...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='filtro-dias',
            options=[
                {'label': 'Domingo', 'value': 'Domingo'},
                {'label': 'Lunes', 'value': 'Lunes'},
                {'label': 'Martes', 'value': 'Martes'},
                {'label': 'Miercoles', 'value': 'Miercoles'},
                {'label': 'Jueves', 'value': 'Jueves'},
                {'label': 'Viernes', 'value': 'Viernes'},
                {'label': 'Sabado', 'value': 'Sabado'},
            ],
            value=[],
            multi=True,
            optionHeight=30,
            placeholder="Días de apertura...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='filtro-barrios',
            options=[{'label': barrio, 'value': barrio} for barrio in df2['Barrio'].unique()],
            value=[],
            multi=True,
            placeholder="Barrios...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='search-input',
            options=[{'label': nombre, 'value': nombre} for nombre in sorted(df2['Nombre'].unique())],
            placeholder='Buscar cafetería por nombre...',
            className='custom-dropdown',
            style={
                'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)',
                'margin-top': '3px'
            }
        ),
        dcc.Dropdown(
            id='map-style-dropdown',
            options=[
                {'label': 'Modo Clásico', 'value': 'open-street-map'},
                {'label': 'Modo Claro', 'value': 'carto-positron'},
                {'label': 'Modo Oscuro', 'value': 'carto-darkmatter'}
            ],
            value='carto-positron',
            placeholder="Tipo de mapa",
            className='custom-dropdown'
        ),
        html.Label("RATING", style={'color': '#fffff5', 'font-weight': 'bold', 'margin-top': '5px','margin-bottom': '5px', 'width': '80%', 'margin-left': 'auto', 'margin-right': 'auto'}),
        dcc.RangeSlider(
            tooltip={"placement": "bottom", "always_visible": True},
            id='rating-slider',
            min=df2['Rating'].min(),
            max=df2['Rating'].max(),
            step=0.1,
            marks={str(rating): {'label': str(rating), 'style': {'color': '#fffff5'}} for rating in range(int(df2['Rating'].min()), int(df2['Rating'].max()) + 1)},
            value=[df2['Rating'].min(), df2['Rating'].max()],
            className='custom-slider'
        ),
        html.Div(className='color-legend', children=[
            html.Div(className='color-1'),
            html.Div(className='color-2'),
            html.Div(className='color-3'),
            html.Div(className='color-4'),
            html.Div(className='color-5')
        ]),
        html.Div(id='output-container-slider'),
        html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': 'auto'}),  # Línea blanca inferior
        html.Div([
            html.A(
                html.I(className="fas fa-envelope"),
                href="mailto:buscafes.ai@gmail.com",
                className='contact-button-circle',
                style={
                    'margin-top': '0px',
                    'margin-bottom': '10px',
                    'display': 'flex',
                    'justify-content': 'center',
                    'align-items': 'center',
                    'width': '40px',
                    'height': '40px',
                    'border': '2px solid #fffff5',
                    'border-radius': '50%',
                    'background-color': 'rgba(255, 255, 255, 1)',
                    'color': '#194d33',
                    'text-decoration': 'none',
                    'margin-left': 'auto',
                    'margin-right': '10px'
                }
            ),
            html.A(
                html.I(className="fab fa-instagram"),
                href="https://www.instagram.com/lucas.chicco",
                className='contact-button-circle',
                style={
                    'margin-top': '0px',
                    'margin-bottom': '10px',
                    'display': 'flex',
                    'justify-content': 'center',
                    'align-items': 'center',
                    'width': '40px',
                    'height': '40px',
                    'border': '2px solid #fffff5',
                    'border-radius': '50%',
                    'background-color': 'rgba(255, 255, 255, 1)',
                    'color': '#194d33',
                    'text-decoration': 'none',
                    'margin-left': '10px',
                    'margin-right': 'auto'
                }
            )
        ], style={'display': 'flex', 'justify-content': 'center', 'align-items': 'center'}),
    ], id='filters-panel', className='controls-container'),
    html.Div([
        dl.Map(
            center=[-34.620000, -58.440000],
            zoom=13,
            zoomControl=False,
            style={'width': '100%', 'height': '100vh'},
            children=[
                dl.TileLayer(id="base-layer", url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
                dl.LocateControl(locateOptions={'enableHighAccuracy': True}, position='bottomright', showPopup=False),
                dl.GeoJSON(id='layer'),
                dl.LayerGroup(id='current-location')
            ]
        )
    ], style={'position': 'relative', 'height': '100vh'}),
    html.Div(id='info-registro', children=[
        html.Button('X', id='close-info-button', className='close-info-button', n_clicks=0),
        html.Div(id='info-content')
    ],)
])

def format_hours(row):
    days = ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']
    hours = []
    for day in days:
        open_time = row[f'{day}_open']
        close_time = row[f'{day}_close']
        if open_time == 'None' and close_time == 'None':
            hours.append(f"{day}: No abre")
        else:
            hours.append(f"{day}: {open_time} - {close_time}")
    if all(hour.endswith('None - None') for hour in hours):
        return html.P("Horarios: Sin datos", style={'font-family': 'Montserrat', 'font-size': '14px'})
    return [html.U(html.Strong("Horarios:", style={'font-family': 'Montserrat', 'font-size': '14px'}))] + [html.P(hour.replace('None - None','No abre'), style={'font-family': 'Montserrat', 'font-size': '14px'}) for hour in hours]
def get_marker_icon(rating):
    if 0 <= rating <= 0.9:
        return "assets/markrojo.svg"
    elif 1 <= rating <= 1.9:
        return "assets/markvioleta.svg"
    elif 2 <= rating <= 2.9:
        return "assets/markceleste.svg"
    elif 3 <= rating <= 3.9:
        return "assets/markbeige.svg"
    elif 4 <= rating <= 5:
        return "assets/markverde.svg"
    return "assets/markrojo.svg"  # Default icon if no condition is met

# Función para generar datos GeoJSON
@cache.memoize()
def generate_geojson(dataframe):
    features = []
    for i, row in dataframe.iterrows():
        properties = {col: row[col] for col in dataframe.columns if col not in ['Latitud', 'Longitud']}
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row['Longitud'], row['Latitud']]
            },
            "properties": properties
        }
        features.append(feature)
    return {
        "type": "FeatureCollection",
        "features": features
    }

# Función para generar un marcador a partir de un GeoJSON feature
@cache.memoize()
def generate_marker(feature):
    properties = feature['properties']
    tooltip = dl.Tooltip([
        html.P(properties['Nombre'], className='nombre'),
        html.P(properties['Rating'], className='stars'),
        html.P([html.Span("Reviews: ", className='bold-text'), properties['Cantidad Reviews']]),
        html.P([html.Span("Dirección: ", className='bold-text'), properties['Dirección']])
    ], className='marker-tooltip')

    popup = dl.Popup([
        html.H4(html.U(properties['Nombre']), style={'font-family': 'Montserrat', 'font-size': '16px', 'font-weight': 'bold'}),
        html.P([html.Strong("Rating: "), str(properties['Rating'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
        html.P([html.Strong("Cantidad Reviews: "), str(properties['Cantidad Reviews'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
        html.P([html.Strong("Sitio Web: "), html.A(properties['Sitio Web'], href=properties['Sitio Web'], target="_blank")], style={'font-family': 'Montserrat', 'font-size': '14px'}),
        html.P([html.Strong("Dirección: "), str(properties['Dirección'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
        *format_hours(properties)
    ])

    return dl.Marker(
        position=[feature['geometry']['coordinates'][1], feature['geometry']['coordinates'][0]],
        icon={
            'iconUrl': get_marker_icon(properties['Rating']),
            'iconSize': [15, 20],
            #'iconAnchor': [2, 5],
        },
        children=[tooltip, popup]
    )



# Actualiza la función filter_data para retornar GeoJSON
@app.callback(
    Output('filtered-data', 'data'),
    [Input('rating-slider', 'value'), Input('feature-filter', 'value'), Input('filtro-dias', 'value'), Input('filtro-barrios', 'value'), Input('search-input', 'value')]
)
@cache.memoize()
def filter_data(rating_range, selected_features, selected_days, selected_barrios, search_input):
    filtered_df = df2[(df2['Rating'] >= rating_range[0]) & (df2['Rating'] <= rating_range[1])]
    if search_input and isinstance(search_input, str):
        filtered_df = filtered_df[filtered_df['Nombre'].str.contains(search_input, case=False)]
    for feature in selected_features:
        filtered_df = filtered_df[filtered_df[feature] == True]
    for day in selected_days:
        open_column = f'{day}_open'
        close_column = f'{day}_close'
        filtered_df = filtered_df[(~filtered_df[open_column].isna()) & (~filtered_df[close_column].isna())]
    if selected_barrios:
        filtered_df = filtered_df[filtered_df['Barrio'].isin(selected_barrios)]
    
    geojson_data = generate_geojson(filtered_df)
    return geojson_data

# Actualiza la función update_map para usar el GeoJSON
@app.callback(
    Output('layer', 'children'),
    Input('filtered-data', 'data')
)
@cache.memoize()
def update_map(geojson_data):
    markers = [generate_marker(feature) for feature in geojson_data["features"]]
    return markers
  
@app.callback(
    Output('base-layer', 'url'),
    Input('map-style-dropdown', 'value')
)
def update_map_style(style):
    style_urls = {
        'open-street-map': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    }
    return style_urls.get(style, 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png')
@app.callback(
    Output('filters-panel', 'style'),
    Output('panel-visible', 'data'),
    Input('toggle-button', 'n_clicks'),
    State('panel-visible', 'data')
)
def toggle_filters(n_clicks, visible):
    if visible is None:
        visible = False
    if n_clicks > 0:
        visible = not visible
    style = {  # Ajustar altura máxima del panel
        'overflow-y': 'auto',
        'display': 'flex' if visible else 'none',  # Habilitar scroll si el contenido es demasiado largo
    }
    return style, visible
    
    
# Ejecuta la aplicación Dash
if __name__ == "__main__":
    app.run_server(debug=False)
