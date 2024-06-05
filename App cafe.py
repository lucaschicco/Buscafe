#!/usr/bin/env python
# coding: utf-8


import requests
import time
import pandas as pd
import openpyxl
import os
import dash
import numpy as np
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go

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

# Crea la aplicación Dash
app = dash.Dash(__name__,meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ])

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

# Estilos para elementos con fondo propio
estilos_con_fondo = {
    'background-color': 'rgba(255, 255, 255, 0.8)',
    'padding': '10px',
    'border-radius': '5px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.1)',
    'margin': '10px',
    'z-index': '1000'
}

# Estilos específicos
estilo_titulo = {
    'text-align': 'center',
    **estilos_con_fondo,
    'position': 'absolute',
    'top': '10px',
    'left': '50%',
    'transform': 'translateX(-50%)',
    'border': '2px solid #000000'
}

estilo_panel_filtros = {
    'position': 'absolute',
    'top': '100px',
    'left': '10px',
    'z-index': '1000',
    'width': '20%',  # Ajusta este valor según sea necesario
    'background-color': 'rgba(255, 255, 255, 0.8)',
    'border-radius': '12px',
    'padding': '10px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.1)',
    'display': 'flex',
    'flex-direction': 'column',
    'gap': '20px'
}
# Añade este estilo específico para el título del panel de filtros
estilo_titulo_panel_filtros = {
    'font-weight': 'bold',
    'text-decoration': 'underline',
    'font-size': '24px',  # Ajusta el tamaño según tus necesidades
    'color': 'black',
    'text-align': 'center',
    'margin-bottom': '10px'
}

estilo_info_registro = {
    'position': 'absolute',
    'top': '60px',
    'right': '110px',
    'width': '15%',
    'border': '2px solid #404040',
    'background-color': 'rgba(255, 255, 255, 0.9)',
    'padding': '10px',
    'border-radius': '5px',
    'box-shadow': '0px 0px 10px rgba(0, 0, 0, 0.1)',
    'z-index': '1000',
    'display': 'none'  # Initially hidden
}

app.layout = html.Div([
    html.H1("Mapa de Cafeterías", style=estilo_titulo),
    html.Div([
        html.H2("Filtros", style=estilo_titulo_panel_filtros),  # Título del panel de filtros
        html.Label("Rating", style={'color': 'black', 'font-weight': 'bold'}),
        dcc.RangeSlider(
            id='rating-slider',
            min=df2['Rating'].min(),
            max=df2['Rating'].max(),
            step=0.1,
            marks={str(rating): {'label': str(rating), 'style': {'color': 'black'}} for rating in marcas},
            value=[df2['Rating'].min(), df2['Rating'].max()],
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
            style={'color': 'black'}
        ),
        dcc.Dropdown(
            id='filtro-barrios',
            options=[{'label': barrio, 'value': barrio} for barrio in df2['Barrio'].unique()],
            value=[],
            multi=True,
            placeholder="Seleccione barrios...",
            style={'color': 'black'}
        ),
        dcc.Input(
            id='search-input',
            type='text',
            placeholder='Buscar cafetería por nombre...',
            style={
                'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)',
                'margin-top': '10px'
            }
        ),
        html.Button("Cambiar tipo de mapa", id='cambiar-estilo-mapa', n_clicks=0, style={
            'text-align': 'center',
            'background-color': '#D2B48C',
            'border': '2px solid #000000',
            'margin-top': '10px'
        })
    ], style=estilo_panel_filtros),
    dcc.Graph(id='mapa-cafeterias', className='map-container', style={
        'height': '100vh',
        'width': '100vw',
        'position': 'absolute',
        'top': '0',
        'left': '0',
        'z-index': '0'
    }),
    html.Div(id='info-registro', style=estilo_info_registro)
])

# Variable global para almacenar el último nivel de zoom
last_zoom = 12
uirevision = 'constant'
# Variable para el estilo del mapa
estilo_inicial = 'carto-positron'

@app.callback(
    Output('mapa-cafeterias', 'figure'),
    Output('info-registro', 'style'),
    Output('info-registro', 'children'),
    [Input('rating-slider', 'value'),
     Input('feature-filter', 'value'),
     Input('filtro-dias', 'value'),
     Input('filtro-barrios', 'value'),
     Input('search-input', 'value'),
     Input('mapa-cafeterias', 'clickData'),
     Input('cambiar-estilo-mapa', 'n_clicks')]
)
def update_map(selected_range, selected_features, selected_days, selected_barrios, search_input, clickData, n_clicks):
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

    if clickData:
        selected_point = clickData['points'][0]
        lat = selected_point['lat']
        lon = selected_point['lon']
        selected_record = filtered_df[(filtered_df['Latitud'] == lat) & (filtered_df['Longitud'] == lon)]

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
        else:
            info_html = None
            info_style = estilo_info_registro.copy()
            info_style['display'] = 'none'
    else:
        info_html = None
        info_style = estilo_info_registro.copy()
        info_style['display'] = 'none'

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
        text=filtered_df.apply(lambda row: f"<b>{row['Nombre']}<br></b><br><b>Rating:</b> {row['Rating']}<br><b>Cantidad Reviews:</b> {row['Cantidad Reviews']}<br><b>Sitio Web:</b> {row['Sitio Web']}<br><b>Dirección:</b> {row['Dirección']}", axis=1),
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

    return fig, info_style, info_html

# Ejecuta la aplicación Dash
if __name__ == '__main__':
    app.run_server(debug=False)
