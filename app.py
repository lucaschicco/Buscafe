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
    'CACHE_DIR': 'cache-directory',  # Directorio para almacenar archivos de caché
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

estilo_info_registro = {
    'position': 'absolute',
    'top': '60px',
    'right': '110px',
    'width': '15%',
    'border': '2px solid #404040',
    'background-color': 'rgba(255, 255, 255, 1)',
    'padding': '0px',
    'border-radius': '5px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.5)',
    'z-index': '1000',
    'display': 'none'  # Initially hidden
}

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
                dl.LayerGroup(id='markers-layer'),
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

def create_markers(filtered_df):
    def generate_stars(rating):
        full_star = '★'
        empty_star = '☆'
        return full_star * int(rating) + empty_star * (5 - int(rating))
    
    markers = []
    for _, row in filtered_df.iterrows():
        tooltip_content = html.Div(children=[
            html.P(row['Nombre'], className='nombre'),  
            html.P(generate_stars(row['Rating']), className='stars'),  
            html.P([html.Span("Reviews: ", className='bold-text'), row['Cantidad Reviews']]),
            html.P([html.Span("Dirección: ", className='bold-text'), row['Dirección']])
        ], className='marker-tooltip')  # Agregando className aquí
        
        popup_content = html.Div(
            children=[
                html.H4(html.U(row['Nombre']), style={'font-family': 'Montserrat', 'font-size': '16px', 'font-weight': 'bold'}),
                html.P([html.Strong("Rating: "), str(row['Rating'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
                html.P([html.Strong("Cantidad Reviews: "), str(row['Cantidad Reviews'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
                html.P([html.Strong("Sitio Web: "), html.A(row['Sitio Web'], href=row['Sitio Web'], target="_blank")], style={'font-family': 'Montserrat', 'font-size': '14px'}),
                html.P([html.Strong("Dirección: "), str(row['Dirección'])], style={'font-family': 'Montserrat', 'font-size': '14px'}),
                *format_hours(row)  
            ],
            className='marker-popup'
        )
        
        marker = dl.Marker(
            position=[row['Latitud'], row['Longitud']],
            icon={
                "iconUrl": get_marker_icon(row['Rating']),
                "iconSize": [20, 20],
                "iconAnchor": [10, 20],
            },
            children=[
                dl.Tooltip(tooltip_content),
                dl.Popup(popup_content)
            ]
        )
        markers.append(marker)
    return markers

@app.callback(
    [Output('filtered-data', 'data'),
     Output('filters-panel', 'style'),
     Output('panel-visible', 'data')],
    [Input('rating-slider', 'value'),
     Input('feature-filter', 'value'),
     Input('filtro-dias', 'value'),
     Input('filtro-barrios', 'value'),
     Input('search-input', 'value'),
     Input('toggle-button', 'n_clicks')],
    [State('panel-visible', 'data')]
)
@cache.memoize()
def filter_data(rating_range, selected_features, selected_days, selected_barrios, search_input, n_clicks, visible):
    # Filtrar los datos
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

    # Manejar la visibilidad del panel
    if visible is None:
        visible = False
    # Solo cambiar la visibilidad si se hace clic en el botón de toggle
    changed_id = [p['prop_id'] for p in dash.callback_context.triggered][0]
    if 'toggle-button' in changed_id:
        visible = not visible
    
    style = {  # Ajustar altura máxima del panel
        'overflow-y': 'auto',
        'display': 'flex' if visible else 'none',  # Habilitar scroll si el contenido es demasiado largo
    }

    return filtered_df.to_dict('records'), style, visible

@app.callback(
    Output('markers-layer', 'children'),
    Input('filtered-data', 'data')
)
def update_map(filtered_data):
    filtered_df = pd.DataFrame(filtered_data)
    markers = create_markers(filtered_df)
    return markers

# Clientside callback para cambiar el estilo del mapa
app.clientside_callback(
    """
    function(style) {
        const styleUrls = {
            'open-street-map': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
        };
        return styleUrls[style] || styleUrls['open-street-map'];
    }
    """,
    Output('base-layer', 'url'),
    Input('map-style-dropdown', 'value')
)
    
# Ejecuta la aplicación Dash
if __name__ == "__main__":
    app.run_server(debug=False)
