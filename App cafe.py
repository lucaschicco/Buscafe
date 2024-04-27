#!/usr/bin/env python
# coding: utf-8


import requests
import time
import pandas as pd
import openpyxl

url = "https://raw.githubusercontent.com/lucaschicco/MiCafe/main/base_caballito.xlsx"

response = requests.get(url)
df2 = pd.read_excel(response.content)


import dash
import numpy as np
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px

# Crea la aplicación Dash
app = dash.Dash(__name__)
# Asigna la aplicación Dash al objeto 'server'
server = app.server
# Define los valores intermedios del slider
valores_intermedios = [i / 10 for i in range(int(df2['Rating'].min() * 10), int(df2['Rating'].max() * 10) + 1)]

# Define los valores enteros del slider
valores_enteros = list(range(int(df2['Rating'].min()), int(df2['Rating'].max()) + 1))

# Define las marcas del slider
marcas = {**{valor: str(valor) for valor in valores_enteros}, **{valor: str(valor) for valor in valores_intermedios}}

# Define el layout de la aplicación
app.layout = html.Div([
    html.H1("Filtro de Cafeterías por Rating y Características"),
    dcc.RangeSlider(
        id='rating-slider',
        min=df2['Rating'].min(),
        max=df2['Rating'].max(),
        step=0.01,  # Ajusta el paso para incluir valores intermedios
        marks=marcas,
        value=[df2['Rating'].min(), df2['Rating'].max()]
    ),
    html.Div(id='output-container-slider'),
    html.Div([
        dcc.Checklist(
            id='feature-filter',
            options=[
                {'label': 'Delivery', 'value': 'Delivery'},
                {'label': 'Comer en lugar', 'value': 'Comer en lugar'},
                {'label': 'Almuerzo', 'value': 'Almuerzo'},
                {'label': 'Cena', 'value': 'Cena'},
                {'label': 'Brunch', 'value': 'Brunch'},
                {'label': 'Vino', 'value': 'Vino'},
                {'label': 'Espacio afuera', 'value': 'Espacio afuera'},
                {'label': 'Accesible para silla de ruedas', 'value': 'Accesible para silla de ruedas'},
                {'label': 'Sirve postre', 'value': 'Sirve postre'},
                {'label': 'Musica en vivo', 'value': 'Musica en vivo'},
                {'label': 'Desayuno', 'value': 'Desayuno'},
                {'label': 'Reservable', 'value': 'Reservable'}
            ],
            value=[]
        )
    ]),
    dcc.Graph(id='mapa-cafeterias')
])

# Define la callback para actualizar el gráfico según el filtro de rating y características
@app.callback(
    Output('mapa-cafeterias', 'figure'),
    [Input('rating-slider', 'value'),
     Input('feature-filter', 'value')]
)
def update_map(selected_range, selected_features):
    filtered_df = df2[(df2['Rating'] >= selected_range[0]) & (df2['Rating'] <= selected_range[1])]
    
    # Aplica los filtros de características seleccionadas
    for feature in selected_features:
        filtered_df = filtered_df[filtered_df[feature] == True]
    
    fig = px.scatter_mapbox(filtered_df, lat="Latitud", lon="Longitud", hover_name="Nombre", 
                             hover_data={"Rating": True, "Cantidad Reviews": True, 
                                         "Sitio Web": True, "Dirección": True,'Latitud': False,'Longitud':False},
                            color_discrete_sequence=["black"], zoom=10, height=500)
    fig.update_layout(mapbox_style="open-street-map")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.update_traces(marker={'size': 8})

    return fig

# Callback para abrir el sitio web al hacer clic en el enlace
@app.callback(
    Output('output-container-slider', 'children'),
    [Input('mapa-cafeterias', 'clickData')]
)
def display_click_data(clickData):
    if clickData:
        nombre_cafeteria = clickData['points'][0]['hovertext']
        sitio_web = df2[df2['Nombre'] == nombre_cafeteria]['Sitio Web'].iloc[0]
        return html.Div([
            html.H4(nombre_cafeteria),
            html.P("Sitio Web: "),
            dcc.Link(sitio_web, href=sitio_web),
            html.P("Rating: " + str(df2[df2['Nombre'] == nombre_cafeteria]['Rating'].iloc[0])),
            html.P("Cantidad Reviews: " + str(df2[df2['Nombre'] == nombre_cafeteria]['Cantidad Reviews'].iloc[0])),
            html.P("Dirección: " + str(df2[df2['Nombre'] == nombre_cafeteria]['Dirección'].iloc[0]))
        ])
    else:
        return ''

# Ejecuta la aplicación Dash
if __name__ == '__main__':
    app.run_server(debug=False)
