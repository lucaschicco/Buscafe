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

url = "https://raw.githubusercontent.com/lucaschicco/MiCafe/main/base_caballito.xlsx"



token = os.getenv('MAPBOX_TOKEN')

response = requests.get(url)
df2 = pd.read_excel(response.content)


# Crea la aplicación Dash
app = dash.Dash(__name__, assets_folder="/assets")
# Asigna la aplicación Dash al objeto 'server'
server = app.server
# Define los valores intermedios del slider
valores_intermedios = [i for i in range(int(df2['Rating'].min() * 10), int(df2['Rating'].max() * 10) + 1)]

cafe_icon = dash.get_asset_url('cafe.svg')

# Define los valores enteros del slider
valores_enteros = list(range(int(df2['Rating'].min()), int(df2['Rating'].max()) + 1))

# Define las marcas del slider
marcas = {**{valor: str(valor) for valor in valores_enteros}, **{valor: str(valor) for valor in valores_intermedios}}

app.layout = html.Div([
    html.Link(rel='stylesheet', href='/assets/bWLwgP.css'),
    html.H1("Mapa de Cafeterías interactivo"),
    html.Div([
        html.Div([
            html.Label("Filtro por Rating"),
            dcc.RangeSlider(
                id='rating-slider',
                min=df2['Rating'].min(),
                max=df2['Rating'].max(),
                step=0.1,
                marks=marcas,
                value=[df2['Rating'].min(), df2['Rating'].max()]
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
                    {'label': 'Reservable', 'value': 'Reservable'}
                ],
                value=[],
                multi=True,
                optionHeight=30,
                placeholder="Seleccione filtros...",
                className='select_box',
                style={'color': 'black'}
            )
        ], className='three columns'),
        html.Div([
            dcc.Graph(id='mapa-cafeterias', style={'width': '100%', 'height': '600px'} )
        ], className='seven columns'),
        html.Div([
            dcc.Input(
                id='search-input',
                type='text',
                placeholder='Buscar cafetería por nombre...',
                className='select_box',
                style={'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)'}
            )
        ], className='two columns', style={'margin-top': '10px', 'color': 'black'})
    ], className='row')
])

# Variable global para almacenar el último nivel de zoom
last_zoom = 12

# Define la callback para actualizar el gráfico según el filtro de rating y características
@app.callback(
    Output('mapa-cafeterias', 'figure'),
    [Input('rating-slider', 'value'),
     Input('feature-filter', 'value'),
     Input('search-input', 'value')]  # Agregar el input del buscador
)
def update_map(selected_range, selected_features,search_input):
    global last_zoom  # Accede a la variable global
    global texto_personalizado  # Accede a la lista de texto personalizado
    
    filtered_df = df2[(df2['Rating'] >= selected_range[0]) & (df2['Rating'] <= selected_range[1])]
    # Aplica los filtros de características seleccionadas
    # Filtrar por el valor ingresado en el buscador
    if search_input:
        filtered_df = filtered_df[filtered_df['Nombre'].str.contains(search_input, case=False)]
    
    for feature in selected_features:
        filtered_df = filtered_df[filtered_df[feature] == True]
    # Limpiar la lista de texto personalizado para evitar duplicados
    texto_personalizado = []
    
    for index, row in filtered_df.iterrows():
        hover_text = f"<b>{row['Nombre']}<br></b><br>"
        hover_text += f"<b>Rating:</b> {row['Rating']}<br>"
        hover_text += f"<b>Cantidad Reviews:</b> {row['Cantidad Reviews']}<br>"
        hover_text += f"<b>Sitio Web:</b> {row['Sitio Web']}<br>"
        hover_text += f"<b>Dirección:</b> {row['Dirección']}<br>"
        texto_personalizado.append(hover_text)
    
    fig = go.Figure(go.Scattermapbox(
        lat=filtered_df['Latitud'],
        lon=filtered_df['Longitud'],
        mode='markers',
        marker=dict(
        size=14,
        symbol=cafe_icon, allowoverlap=True),
        text=texto_personalizado  # Usar el texto personalizado como texto del marcador
    ))
    
    fig.update_layout(
        hovermode='closest',
        showlegend=False,
        autosize=True,
        width=1000,
        height=800,
        mapbox=dict(
            style="streets",
            accesstoken=token,
            bearing=0,
            center=dict(
                lat=filtered_df['Latitud'].mean(),
                lon=filtered_df['Longitud'].mean()
            ),
            pitch=0,
            zoom=12,
        )
    )
    fig.update_traces(hoverinfo='text') 
    fig.update_traces(hoverlabel=dict(bgcolor="gray", font=dict(color="white", family="Arial", size=12)))

    
    return fig 

# Callback para abrir el sitio web al hacer clic en el enlace
@app.callback(
    Output('output-container-slider', 'children'),
    [Input('mapa-cafeterias', 'clickData')]
)
def display_click_data(clickData):
    global texto_personalizado
    
    if clickData:
        indice_marcador = clickData['points'][0]['pointIndex']
        texto = texto_personalizado[indice_marcador]
        texto_sin_html = texto.replace('<br>', '\n').replace('<b>', '**').replace('</b>', '**')
        
        return html.Div([
            html.H4("Información de la cafetería"),
            dcc.Markdown(texto_sin_html)
        ])
    else:
        return ''

# Ejecuta la aplicación Dash
if __name__ == '__main__':
    app.run_server(debug=True)
