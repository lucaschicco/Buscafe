#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
import openpyxl
import os
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from flask_caching import Cache
import gzip
import json
from dash_extensions.javascript import assign
import dash_leaflet.express as dlx

external_stylesheets = [dbc.themes.BOOTSTRAP, 
                        'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',
                       'https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
# Asignar la aplicación Dash al objeto 'server'
server = app.server

cache = Cache(app.server, config={
    'CACHE_TYPE': 'filesystem',  # Puedes usar 'redis' si prefieres usar Redis
    'CACHE_DIR': 'cache-directory',  # Directorio para almacenar archivos de caché
    'CACHE_DEFAULT_TIMEOUT': 300  # Tiempo en segundos que los datos permanecerán en caché
})

# Leer el archivo Excel
@cache.memoize()
def load_data():
    url = "https://jsonbuscafe.blob.core.windows.net/contbuscafe/base_todos_barrios_vf2.xlsx"
    response = requests.get(url)
    df = pd.read_excel(response.content)
    return df
df = load_data() 

df.Barrio.fillna('sin datos', inplace=True)

# Crear las opciones del dropdown
barrios = df['Barrio'].unique()
dd_options = [dict(value=barrio, label=barrio) for barrio in barrios]
dd_defaults = [o["value"] for o in dd_options]

## Función para generar estrellas basadas en el rating
def generate_stars(rating):
    stars = int(rating)
    return '★' * stars + '☆' * (5 - stars)


# Función para determinar la URL del ícono basado en el rating
def get_icon_url(rating):
    base_url = "https://jsonbuscafe.blob.core.windows.net/contbuscafe/"
    if 0 <= rating <= 0.9:
        return base_url + "markrojo.svg"
    elif 1 <= rating <= 1.9:
        return base_url + "markvioleta.svg"
    elif 2 <= rating <= 2.9:
        return base_url + "markceleste.svg"
    elif 3 <= rating <= 3.9:
        return base_url + "markbeige.svg"
    elif 4 <= rating <= 5:
        return base_url + "markverde.svg"
    return base_url + "markrojo.svg"

def format_hours(row):
    days = ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']
    hours = []
    for day in days:
        open_time = row[f'{day}_open']
        close_time = row[f'{day}_close']
        if pd.isna(open_time) and pd.isna(close_time):
            hours.append(f"{day}: No abre")
        else:
            hours.append(f"{day}: {open_time if not pd.isna(open_time) else 'No abre'} - {close_time if not pd.isna(close_time) else 'No abre'}")
    if all(hour.endswith('No abre') for hour in hours):
        return None
    return ["<strong>Horarios:</strong>"] + [hour for hour in hours]


# Convertir los datos a GeoJSON
geojson_data = dlx.dicts_to_geojson([{
    "name": row["Barrio"],
    "lat": row["Latitud"],
    "lon": row["Longitud"],
    "tooltip": f"""
        <p class='nombre'>{row['Nombre']}</p>
        <p class='stars'>{generate_stars(row['Rating'])}</p>
        <p><span class='bold-text'>Reviews: </span>{row['Cantidad Reviews']}</p>
        <p><span class='bold-text'>Dirección: </span>{row['Dirección']}</p>
    """,
    "popup": f"""
        <h4 style='font-family: Montserrat; font-size: 16px; font-weight: bold;'><u>{row['Nombre']}</u></h4>
        <p style='font-family: Montserrat; font-size: 14px;'><strong>Rating: </strong>{row['Rating']}</p>
        <p style='font-family: Montserrat; font-size: 14px;'><strong>Cantidad Reviews: </strong>{row['Cantidad Reviews']}</p>
        <p style='font-family: Montserrat; font-size: 14px;'><strong>Sitio Web: </strong>{f"<a href='{row['Sitio Web']}' target='_blank'>{row['Sitio Web']}</a>" if pd.notna(row['Sitio Web']) else 'Sin datos'}</p>
        <p style='font-family: Montserrat; font-size: 14px;'><strong>Dirección: </strong>{'Sin datos' if pd.isna(row['Dirección']) else row['Dirección']}</p>
        {'<div style="font-family: Montserrat; font-size: 14px;">' + '<br>'.join(format_hours(row)) + '</div>' if format_hours(row) else ''}
    """,
    "icon_url": get_icon_url(row["Rating"])
} for _, row in df.iterrows()])

# Crear una función JavaScript para filtrar según el barrio
geojson_filter = assign("function(feature, context){return context.hideout.includes(feature.properties.name);}")

app.layout = html.Div(id="root", children=[
    dcc.Location(id='url', refresh=True),
    dcc.Store(id='panel-visible', data=False),
    dcc.Store(id='info-visible', data=False),
    dcc.Store(id='current-location-store'),
    dcc.Store(id='filtered-data'),
    dcc.Store(id='sampled-data', data=[]),
    html.Button("Filtros", id='toggle-button', className='custom-toggle-button', n_clicks=0),
    html.Div([
        html.Div([
            html.Img(src='/assets/buscafes.png', style={'width': '80%', 'height': 'auto', 'marginBottom': '0px', 'marginTop': '10px'}),
            html.Hr(style={'borderTop': '2px solid #fffff5', 'width': '80%', 'margin': '10px auto'})  # Línea blanca superior
        ], style={'display': 'flex', 'alignItems': 'center', 'flexDirection': 'column'}),
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
            options=[{'label': barrio, 'value': barrio} for barrio in df['Barrio'].unique()],
            value=[],
            multi=True,
            placeholder="Barrios...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='search-input',
            options=[{'label': nombre, 'value': nombre} for nombre in sorted(df['Nombre'].unique())],
            placeholder='Buscar cafetería por nombre...',
            className='custom-dropdown',
            style={
                'boxShadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)',
                'marginTop': '3px'
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
        html.Label("RATING", style={'color': '#fffff5', 'fontWeight': 'bold', 'marginTop': '5px','marginBottom': '5px', 'width': '80%', 'marginLeft': 'auto', 'marginRight': 'auto'}),
        dcc.RangeSlider(
            tooltip={"placement": "bottom", "always_visible": True},
            id='rating-slider',
            min=df['Rating'].min(),
            max=df['Rating'].max(),
            step=0.1,
            marks={str(rating): {'label': str(rating), 'style': {'color': '#fffff5'}} for rating in range(int(df['Rating'].min()), int(df['Rating'].max()) + 1)},
            value=[df['Rating'].min(), df['Rating'].max()],
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
        html.Hr(style={'borderTop': '2px solid #fffff5', 'width': '80%', 'margin': 'auto'}),  # Línea blanca inferior
        html.Div([
            html.A(
                html.I(className="fas fa-envelope"),
                href="mailto:buscafes.ai@gmail.com",
                className='contact-button-circle',
                style={
                    'marginTop': '0px',
                    'marginBottom': '10px',
                    'display': 'flex',
                    'justifyContent': 'center',
                    'alignItems': 'center',
                    'width': '40px',
                    'height': '40px',
                    'border': '2px solid #fffff5',
                    'borderRadius': '50%',
                    'backgroundColor': 'rgba(255, 255, 255, 1)',
                    'color': '#194d33',
                    'textDecoration': 'none',
                    'marginLeft': 'auto',
                    'marginRight': '10px'
                }
            ),
            html.A(
                html.I(className="fab fa-instagram"),
                href="https://www.instagram.com/lucas.chicco",
                className='contact-button-circle',
                style={
                    'marginTop': '0px',
                    'marginBottom': '10px',
                    'display': 'flex',
                    'justifyContent': 'center',
                    'alignItems': 'center',
                    'width': '40px',
                    'height': '40px',
                    'border': '2px solid #fffff5',
                    'borderRadius': '50%',
                    'backgroundColor': 'rgba(255, 255, 255, 1)',
                    'color': '#194d33',
                    'textDecoration': 'none',
                    'marginLeft': '10px',
                    'marginRight': 'auto'
                }
            )
        ], style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center'}),
    ], id='filters-panel', className='controls-container'),
    html.Div([
        dl.Map(
            center=[-34.620000, -58.440000],
            zoom=13,
            zoomControl=False,
            style={'width': '100%', 'height': '100vh'},
            id='map',
            children=[
                dl.TileLayer(id="base-layer", url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
                dl.LocateControl(locateOptions={'enableHighAccuracy': True}, position='bottomright', showPopup=False),
                dl.LayerGroup(id='markers-layer'),
                dl.LayerGroup(id='current-location'),
                dl.GeoJSON(id='geojson', data=geojson_data, filter=geojson_filter, hideout=dd_defaults, zoomToBounds=False,
                           options=dict(pointToLayer=assign(
                                """function(feature, latlng){
                                       return L.marker(latlng, {
                                           icon: L.icon({
                                               iconUrl: feature.properties.icon_url,
                                               iconSize: [15, 23],
                                               iconAnchor: [12, 23],
                                               popupAnchor: [1, -34],
                                               shadowSize: [41, 41]
                                           })
                                       }).bindTooltip(feature.properties.tooltip, {direction: "top", offset: L.point(0, -20), opacity: 0.9, className: 'marker-tooltip'})
                                         .bindPopup(feature.properties.popup);
                                }""")))
            ]
        )
    ], style={'position': 'relative', 'height': '100vh'}),
    html.Div(id='info-registro', children=[
        html.Button('X', id='close-info-button', className='close-info-button', n_clicks=0),
        html.Div(id='info-content')
    ],)
])

# Callback para actualizar la capa del mapa según los filtros
@app.callback(
    [Output('geojson', 'data'), Output('sampled-data', 'data')],
    [Input('map', 'bounds'),
     Input('map', 'zoom'),
     Input('feature-filter', 'value'),
     Input('filtro-dias', 'value'),
     Input('filtro-barrios', 'value'),
     Input('search-input', 'value'),
     Input('rating-slider', 'value')],
    [State('sampled-data', 'data')]
)
def update_map(bounds, zoom, features, days, barrios, search, rating, sampled_data):
    filtered_df = df.copy()

    if features:
        for feature in features:
            filtered_df = filtered_df[filtered_df[feature] == True]

    if days:
        day_filters = [f"{day}_open" for day in days]
        filtered_df = filtered_df.dropna(subset=day_filters, how='all')

    if barrios:
        filtered_df = filtered_df[filtered_df['Barrio'].isin(barrios)]

    if search:
        filtered_df = filtered_df[filtered_df['Nombre'].str.contains(search, case=False)]

    if rating:
        filtered_df = filtered_df[(filtered_df['Rating'] >= rating[0]) & (filtered_df['Rating'] <= rating[1])]

    if bounds:
        south_west = bounds[0]
        north_east = bounds[1]
        filtered_df = filtered_df[
            (filtered_df['Latitud'] >= south_west[0]) & (filtered_df['Latitud'] <= north_east[0]) &
            (filtered_df['Longitud'] >= south_west[1]) & (filtered_df['Longitud'] <= north_east[1])
        ]

    if zoom < 15:
        if not sampled_data:
            sampled_df = filtered_df.sample(frac=0.3)
            sampled_data = sampled_df.to_dict('records')
        else:
            sampled_df = pd.DataFrame(sampled_data)
    else:
        sampled_df = filtered_df

    geojson_data = dlx.dicts_to_geojson([{
        "name": row["Barrio"],
        "lat": row["Latitud"],
        "lon": row["Longitud"],
        "tooltip": f"""
            <p class='nombre'>{row['Nombre']}</p>
            <p class='stars'>{generate_stars(row['Rating'])}</p>
            <p><span class='bold-text'>Reviews: </span>{row['Cantidad Reviews']}</p>
            <p><span class='bold-text'>Dirección: </span>{row['Dirección']}</p>
        """,
        "popup": f"""
            <h4 style='font-family: Montserrat; font-size: 16px; font-weight: bold;'><u>{row['Nombre']}</u></h4>
            <p style='font-family: Montserrat; font-size: 14px;'><strong>Rating: </strong>{row['Rating']}</p>
            <p style='font-family: Montserrat; font-size: 14px;'><strong>Cantidad Reviews: </strong>{row['Cantidad Reviews']}</p>
            <p style='font-family: Montserrat; font-size: 14px;'><strong>Sitio Web: </strong>{f"<a href='{row['Sitio Web']}' target='_blank'>{row['Sitio Web']}</a>" if pd.notna(row['Sitio Web']) else 'Sin datos'}</p>
             <p style='font-family: Montserrat; font-size: 14px;'><strong>Dirección: </strong>{'Sin datos' if pd.isna(row['Dirección']) else row['Dirección']}</p>
            {'<div style="font-family: Montserrat; font-size: 14px;">' + '<br>'.join(format_hours(row)) + '</div>' if format_hours(row) else ''}
        """,
        "icon_url": get_icon_url(row["Rating"])
    } for _, row in sampled_df.iterrows()])

    return geojson_data, sampled_data

@app.callback(
    Output('base-layer', 'url'),
    Input('map-style-dropdown', 'value')
)
@cache.memoize()
def update_map_style(map_style):
    style_urls = {
        'open-street-map': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    }
    return style_urls[map_style]

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
