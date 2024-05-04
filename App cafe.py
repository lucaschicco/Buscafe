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

external_stylesheets = [
    'https://cdnjs.cloudflare.com/ajax/libs/normalize/7.0.0/normalize.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/skeleton/2.0.4/skeleton.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css',
    'https://fonts.googleapis.com/css?family=Roboto:400,300,500,700',
    'https://codepen.io/bcd/pen/KQrXdb.css',
    'https://codepen.io/chriddyp/pen/bWLwgP.css'
]

#token = os.getenv('MAPBOX_TOKEN')

response = requests.get(url)
df2 = pd.read_excel(response.content)


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

app.layout = html.Div([
    html.H1("Mapa de Cafeterías interactivo"),
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
    ),
    dcc.Graph(id='mapa-cafeterias', className='map-container'),
    dcc.Input(
        id='search-input',
        type='text',
        placeholder='Buscar cafetería por nombre...',
        className='search-box',
        style={'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)'}
    )
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
    
    fig = px.scatter_mapbox(filtered_df, lat="Latitud", lon="Longitud", hover_name="Nombre", 
                             hover_data={"Rating": True, "Cantidad Reviews": True, 
                                         "Sitio Web": True, "Dirección": True,'Latitud': False,'Longitud':False},
                            #color_discrete_sequence=["black"],
                            color="Rating",zoom=12, height=700,width=1400,
                            color_continuous_scale=px.colors.cyclical.IceFire,
                            range_color=[1,5],
                           size='Rating'    
                           )
                            
                        
    fig.update_layout(mapbox_style="open-street-map")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.update_traces(marker={'size': 12})

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
            html.H6("Información de la cafetería"),
            dcc.Markdown(texto_sin_html)
        ])
    else:
        return ''

# Ejecuta la aplicación Dash
if __name__ == '__main__':
    app.run_server(debug=False)
