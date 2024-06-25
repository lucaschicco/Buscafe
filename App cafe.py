#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
import openpyxl
import os
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import dash_bootstrap_components as dbc

url = "https://raw.githubusercontent.com/lucaschicco/MiCafe/main/base_todos_barrios_vf.xlsx"

response = requests.get(url)
df2 = pd.read_excel(response.content)

# Create a function to parse the opening hours
def parse_hours(hours):
    if pd.isna(hours):
        return None, None
    open_time, close_time = hours.split('-')
    open_time = open_time.strip()
    close_time = close_time.strip()
    return pd.to_datetime(open_time, format='%H:%M').strftime('%H:%M'), pd.to_datetime(close_time, format='%H:%M').strftime('%H:%M')

# Apply the function to each day column
for day in ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']:
    df2[[f'{day}_open', f'{day}_close']] = df2[day].apply(lambda x: pd.Series(parse_hours(x)))

# Drop the original day columns
df2.drop(columns=['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado'], inplace=True)

external_stylesheets = ['https://github.com/lucaschicco/MiCafe/raw/main/assets/bWLwgP.css']

# Crea la aplicación Dash
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

# Asigna la aplicación Dash al objeto 'server'
server = app.server

# Define los valores intermedios del slider
valores_intermedios = [i for i in range(int(df2['Rating'].min() * 10), int(df2['Rating'].max() * 10) + 1)]

# Define los valores enteros del slider
valores_enteros = list(range(int(df2['Rating'].min()), int(df2['Rating'].max()) + 1))

# Define las marcas del slider
marcas = {**{valor: str(valor) for valor in valores_enteros}, **{valor: str(valor) for valor in valores_intermedios}}

# Estilos de mapa
map_styles = ['open-street-map', 'carto-positron', 'carto-darkmatter']

estilo_info_registro = {
    'position': 'absolute',
    'top': '60px',
    'right': '110px',
    'width': '15%',
    'border': '2px solid #404040',
    'background-color': 'rgba(255, 255, 255, 1)',
    'padding': '10px',
    'border-radius': '5px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.5)',
    'z-index': '1000',
    'display': 'none'  # Initially hidden
}
control_containers = {
    'position': 'absolute',
    'top': '100px',
    'left': '10px',
    'z-index': '1000',
    'background-color': 'rgba(255, 255, 255, 1)',
    'border-radius': '12px',
    'padding': '10px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.4)',
    'display': 'flex',
    'flex-direction': 'column',
    'gap': '20px'
}

app.layout = html.Div([
    dcc.Store(id='panel-visible', data=False),  # Almacenamiento del estado del panel de filtros
    dcc.Store(id='info-visible', data=False),  # Almacenamiento del estado del panel de información
    html.Button("Filtros", id='toggle-button', className='custom-toggle-button', n_clicks=0),
    html.Div([
        html.Label("Rating", style={'color': 'black', 'font-weight': 'bold'}),
        dcc.RangeSlider(
            tooltip={"placement": "bottom", "always_visible": True},
            id='rating-slider',
            min=df2['Rating'].min(),
            max=df2['Rating'].max(),
            step=0.1,
            marks={str(rating): {'label': str(rating), 'style': {'color': 'black'}} for rating in range(int(df2['Rating'].min()), int(df2['Rating'].max()) + 1)},
            value=[df2['Rating'].min(), df2['Rating'].max()],
            className='custom-slider'        
        ),
        html.Div(id='output-container-slider'),
        dcc.Dropdown(
            id='feature-filter',
            options=[
                {'label': 'Delivery', 'value': 'Delivery'},
                {'label': 'Para comer en el lugar', 'value': 'Comer en lugar'},
                {'label': 'Almuerzo', 'value': 'Almuerzo'},
                {'label': 'Cena', 'value': 'Cena'},
                {'label': 'Brunch', 'value': 'Brunch'},
                {'label': 'Vino', 'value': 'Vino'},
                {'label': 'Con espacio afuera', 'value': 'Espacio afuera'},
                {'label': 'Accesible para silla de ruedas', 'value': 'Accesible para silla de ruedas'},
                {'label': 'Sirve postre', 'value': 'Sirve postre'},
                {'label': 'Musica en vivo', 'value': 'Musica en vivo'},
                {'label': 'Desayuno', 'value': 'Desayuno'},
                {'label': 'Reservable', 'value': 'Reservable'},
                {'label': 'Tiene Takeaway', 'value': 'Tiene takeaway'}
            ],
            value=[],
            multi=True,
            optionHeight=30,
            placeholder="Seleccione filtros...",
            className='custom-dropdown',
            style={'color': 'black'}
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
            className='custom-dropdown',
            style={'color': 'black'}
        ),
        dcc.Dropdown(
            id='filtro-barrios',
            options=[{'label': barrio, 'value': barrio} for barrio in df2['Barrio'].unique()],
            value=[],
            multi=True,
            placeholder="Seleccione barrios...",
            className='custom-dropdown',
            style={'color': 'black'}
        ),
        dcc.Input(
            id='search-input',
            type='text',
            placeholder='Buscar cafetería por nombre...',
            className='custom-input',
            style={
                'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)',
                'margin-top': '10px'
            }
        ),
        html.Button("Cambiar tipo de mapa", id='cambiar-estilo-mapa', n_clicks=0, className='custom-button')
    ], id='filters-panel', className='controls-container'),  # Usa la clase CSS aquí
    dcc.Graph(id='mapa-cafeterias', className='map-container', style={
        'height': '100vh',
        'width': '100vw',
        'position': 'relative',
        'top': '0',
        'left': '0',
        'z-index': '0'
    }),
    html.Div(id='info-registro', children=[
        html.Button('X', id='close-info-button', className='close-info-button', n_clicks=0),
        html.Div(id='info-content')
    ])
])

# Variable global para almacenar el último nivel de zoom
last_zoom = 12
uirevision = 'constant'
# Variable para el estilo del mapa
estilo_inicial = 'carto-positron'

@app.callback(
    Output('mapa-cafeterias', 'figure'),
    [Input('rating-slider', 'value'),
     Input('feature-filter', 'value'),
     Input('filtro-dias', 'value'),
     Input('filtro-barrios', 'value'),
     Input('search-input', 'value'),
     Input('cambiar-estilo-mapa', 'n_clicks')]
)
def update_map(selected_range, selected_features, selected_days, selected_barrios, search_input, n_clicks):
    global last_zoom
    global estilo_inicial

    estilos = ['carto-positron', 'carto-darkmatter','open-street-map']
    estilo = estilos[n_clicks % len(estilos)]
    
    filtered_df = df2[(df2['Rating'] >= selected_range[0]) & (df2['Rating'] <= selected_range[1])]
    
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

    size = filtered_df['Rating'] * 3.5
    size = size.where(size != 0, 16)
    fig = go.Figure(go.Scattermapbox(
        lat=filtered_df['Latitud'],
        lon=filtered_df['Longitud'],
        mode='markers',
        marker=go.scattermapbox.Marker(
            allowoverlap=True,
            sizemin=1,
            size=size,
            color=filtered_df['Rating'],
            colorscale='IceFire',
            showscale=True,
            colorbar=dict(title='Rating'),
            cmin=1,
            cmax=5,
        ),
        text=filtered_df.apply(lambda row: f"<b>{row['Nombre']}<br></b><br><b>Rating:</b> {row['Rating']}<br><b>Cantidad Reviews:</b> {row['Cantidad Reviews']}<br><b>Dirección:</b> {row['Dirección']}", axis=1),
        hoverinfo='text'
    ))

    fig.update_layout(
        mapbox=dict(
            style=estilo,
            zoom=last_zoom,
            center=dict(lat=-34.620000, lon=-58.440000)
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        uirevision=uirevision
    )

    return fig

@app.callback(
    Output('info-registro', 'style'),
    Output('info-content', 'children'),
    Output('info-visible', 'data'),
    [Input('mapa-cafeterias', 'clickData'),
     Input('close-info-button', 'n_clicks')],
    [State('info-visible', 'data')]
)
def update_info_panel(clickData, close_n_clicks, info_visible):
    ctx = dash.callback_context

    if not ctx.triggered:
        return estilo_info_registro.copy(), None, info_visible

    button_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if button_id == 'close-info-button' and info_visible:
        info_html = None
        info_style = estilo_info_registro.copy()
        info_style['display'] = 'none'
        info_visible = False
    elif button_id == 'mapa-cafeterias':
        selected_point = clickData['points'][0]
        lat = selected_point['lat']
        lon = selected_point['lon']
        selected_record = df2[(df2['Latitud'] == lat) & (df2['Longitud'] == lon)]

        if not selected_record.empty:
            record = selected_record.iloc[0]
            info_html = [
                html.H4(html.U(record['Nombre'])),
                html.P([html.Strong("Rating: "), str(record['Rating'])]),
                html.P([html.Strong("Cantidad Reviews: "), str(record['Cantidad Reviews'])]),
                html.P([html.Strong("Sitio Web: "), html.A(record['Sitio Web'], href=record['Sitio Web'], target="_blank")]),
                html.P([html.Strong("Dirección: "), str(record['Dirección'])]),
                html.P(html.U(html.Strong("Horarios:"))),
                html.P([html.Strong("Domingo: "), f"{record['Domingo_open']} - {record['Domingo_close']}"]),
                html.P([html.Strong("Lunes: "), f"{record['Lunes_open']} - {record['Lunes_close']}"]),
                html.P([html.Strong("Martes: "), f"{record['Martes_open']} - {record['Martes_close']}"]),
                html.P([html.Strong("Miércoles: "), f"{record['Miercoles_open']} - {record['Miercoles_close']}"]),
                html.P([html.Strong("Jueves: "), f"{record['Jueves_open']} - {record['Jueves_close']}"]),
                html.P([html.Strong("Viernes: "), f"{record['Viernes_open']} - {record['Viernes_close']}"]),
                html.P([html.Strong("Sábado: "), f"{record['Sabado_open']} - {record['Sabado_close']}"]),
            ]
            info_style = estilo_info_registro.copy()
            info_style['display'] = 'block'
            info_visible = True
        else:
            info_html = None
            info_style = estilo_info_registro.copy()
            info_style['display'] = 'none'
            info_visible = False
    else:
        info_html = None
        info_style = estilo_info_registro.copy()
        info_style['display'] = 'none'
        info_visible = False

    return info_style, info_html, info_visible

# Callback para mostrar/ocultar el panel de filtros
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

    style = control_containers.copy()
    style['display'] = 'flex' if visible else 'none'
    
    return style, visible

# Ejecuta la aplicación Dash
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run_server(host='0.0.0.0', port=port)
