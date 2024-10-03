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

# Crear la aplicación Dash



app = dash.Dash(__name__, title="Buscafes")
server = app.server  # Esto expone el servidor de Flask
app._favicon = ("coffee-solid.ico")
# Habilitar la compresión
Compress(server)

# Agregar el atributo lang al elemento <html>
app.index_string = '''
<!DOCTYPE html>
<html lang="es">
<head>
  {%metas%}
  <title>{%title%}</title>
  {%favicon%}
  {%css%}
</head>
<body>
  <div id="react-entry-point">
    {%app_entry%}
  </div>
  <footer>
    {%config%}
    {%scripts%}
    {%renderer%}
  </footer>
</body>
</html>
'''

# Cargar datos
file_path = 'https://jsonbuscafe.blob.core.windows.net/contbuscafe/base_todos_barrios_vf2.xlsx'
data = pd.read_excel(file_path)

# URL of the JSON file
url = 'https://jsonbuscafe.blob.core.windows.net/contbuscafe/geojson_data2.json'
# Fetch the content from the URL
response = requests.get(url)
# Load the content into a Python dictionary
geojson_data = response.json()


lat_min = data['Latitud'].min()
lat_max = data['Latitud'].max()
lon_min = data['Longitud'].min()
lon_max = data['Longitud'].max()

with open('assets/cafeinit.svg', 'r') as file:
    svg_content = file.read()

# Layout de la aplicación
app.layout = html.Div([
    dcc.Store(id='initial-load', data=True),
    dcc.Store(id='clientside-store-data', data=geojson_data),  # Almacenar los datos GeoJSON directamente en el frontend
    dcc.Store(id='info-visible', data=False),
    html.Button("Mostrar/Ocultar Filtros", id='toggle-button', className='custom-toggle-button', n_clicks=0),
    # Spinner de carga inicial
    html.Div([
        dls.Custom(
            svg=svg_content,
            #color="#119DFF",  # Puedes personalizar el color
            #size=80,  # Ajusta el tamaño del spinner
            id='initial-loading-spinner',  # Le damos un id para controlarlo
        )
    ], id='loading-div', style={'position': 'fixed', 'top': '0', 'left': '0', 'width': '100%', 'height': '100%', 'display': 'flex', 'justify-content': 'center', 'align-items': 'center', 'background-color': 'rgba(255, 255, 255, 1)', 'z-index': '3000'}),

    # Pantalla de carga para los filtros y el mapa
    html.Div([
        html.Div([
            html.Img(src='/assets/buscafes.png', style={'width': '80%', 'height': 'auto', 'margin-bottom': '0px', 'margin-top': '10px'}),
            html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': '10px auto'})  # Línea blanca superior
        ], style={'display': 'flex', 'align-items': 'center', 'flex-direction': 'column'}),

        dcc.Dropdown(
            id='barrio-dropdown',
            options=[{'label': barrio, 'value': barrio} for barrio in data['Barrio'].unique()],
            value=None,
            placeholder="Selecciona un barrio",
            className='custom-dropdown',
            multi=True
        ),
        dcc.Dropdown(
            id='feature-filter',
            options=[
                {'label': 'Tiene Delivery', 'value': 'Delivery'},
                {'label': 'Para comer en el lugar', 'value': 'Comer en lugar'},
                {'label': 'Almuerzo', 'value': 'Almuerzo'},
                {'label': 'Cena', 'value': 'Cena'},
                {'label': 'Brunch', 'value': 'Brunch'},
                {'label': 'Vino', 'value': 'Vino'},
                {'label': 'Con espacio afuera', 'value': 'Espacio afuera'},
                {'label': 'Sirve postre', 'value': 'Sirve postre'},
                {'label': 'Musica en vivo', 'value': 'Musica en vivo'},
                {'label': 'Desayuno', 'value': 'Desayuno'},
                {'label': 'Reservable', 'value': 'Reservable'},
                {'label': 'Tiene takeaway', 'value': 'Tiene takeaway'}
            ],
            value=[],
            multi=True,
            placeholder="Filtrá por Características...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='dias-apertura-filter',
            options=[{'label': day, 'value': day} for day in ['Domingo', 'Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado']],
            value=[],
            multi=True,
            placeholder="Filtrá por Días de Apertura...",
            className='custom-dropdown'
        ),
        dcc.Dropdown(
            id='nombre-filter',
            options=[{'label': nombre, 'value': nombre} for nombre in sorted(data['Nombre'].unique())],
            value=[],
            multi=True,
            placeholder="Busca por Nombre...",
            className='custom-dropdown',
            style={
                'box-shadow': '0px 0px 5px 2px rgba(0, 0, 0, 0.1)',
                'margin-top': '3px'
            }
        ),
        html.Label("RATING", style={'color': '#fffff5', 'font-weight': 'bold', 'margin-top': '5px', 'margin-bottom': '5px',  'margin-left': '40px'}),
        dcc.RangeSlider(
            id='rating-slider',
            min=data['Rating'].min(),
            max=data['Rating'].max(),
            step=0.1,
            marks={str(rating): {'label': str(rating)} for rating in range(int(data['Rating'].min()), int(data['Rating'].max()) + 1)},
            value=[data['Rating'].min(), data['Rating'].max()],
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
                {'label': 'Modo Claro', 'value': 'carto-positron'},
                {'label': 'Modo Oscuro', 'value': 'carto-darkmatter'}
            ],
            value='carto-positron',
            placeholder="Estilo de mapa",
            className='custom-dropdown',
            style={'margin-top': '15px'},
        ),
        html.Div(id='output-container-slider'),
        html.Hr(style={'border-top': '2px solid #fffff5', 'width': '80%', 'margin': 'auto'}),
        html.Div([
            html.A(
                html.Img(src='https://jsonbuscafe.blob.core.windows.net/contbuscafe/envelope-solid.svg',
                         style={'width': '18px', 'height': '18px', 'filter': 'invert(38%) sepia(78%) saturate(292%) hue-rotate(94deg) brightness(97%) contrast(101%)'}),
                href="mailto:buscafes.ai@gmail.com",
                className='contact-button-circle',
                style={}
            ),
            html.A(
                html.Img(src='https://jsonbuscafe.blob.core.windows.net/contbuscafe/instagram-brands-solid.svg',
                         style={'width': '18px', 'height': '18px', 'filter': 'invert(38%) sepia(78%) saturate(292%) hue-rotate(94deg) brightness(97%) contrast(101%)'}),
                href="https://www.instagram.com/lucas.chicco",
                className='contact-button-circle',
                style={}
            )
        ], style={'display': 'flex', 'justify-content': 'center', 'align-items': 'center'}),
    ], id='filters-panel', className='controls-container'),

    # Usamos el spinner de dash-loading-spinners
    dl.Map(
            id='map',
                style={'width': '100%', 'height': '100vh', 'max-height': '100vh'},
                center=[-34.598, -58.436],
                zoomControl=False,
                bounds=[[lat_min, lon_min], [lat_max, lon_max]],
                zoom=12,
                children=[
                    dl.TileLayer(id="base-layer", url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"),
                    dl.LocateControl(locateOptions={'enableHighAccuracy': True,'setView': False}, position='topright', showPopup=False),
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
                                    
                                    // Añadir un evento de click al marker para mostrar el Popup
                                    marker.on('click', function(){
                                        var popup = L.popup({closeOnMove: false})
                                            .setLatLng(latlng)
                                            .setContent(feature.properties.popupContent)
                                            .openOn(marker._map);  // Asegura que el popup se mantenga abierto
                        
                                        // Asegura que el mapa no se centre automáticamente en el marker
                                        marker._map.panTo(latlng, {animate: true});
                                    });
                        
                                    return marker;
                                }
                                """)
                        ),
                        zoomToBoundsOnClick=True,
                    )
                ]
            )
        ,html.Div([
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
            'bottom': '30px',  # A 30px del "piso"
            'left': '50%',
            'transform': 'translateX(-50%)',  # Centra el recuadro horizontalmente
            'background-color': '#d3d3d3',  # Fondo gris claro
            'color': 'black',  # Letra negra
            'padding': '10px 20px',  # Espaciado interno
            'border-radius': '8px',  # Bordes redondeados
            'box-shadow': '0px 4px 10px rgba(0, 0, 0, 0.1)',  # Sombra suave
            'font-weight': 'bold',
            'z-index': '2000',  # Asegura que esté por encima del mapa y otros elementos
            'font-size': '14px',  # Ajusta el tamaño de letra
            'text-align': 'center',
            'width': 'auto',  # No ocupar todo el ancho de la pantalla
            'max-width': '80%'  # Ajustar un máximo de ancho si es necesario
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



app.clientside_callback(
    """
    function(barriosSeleccionados, featureFilter, ratingRange, diasApertura, nombreFilter, bounds, zoom, geojsonData) {
        if (!geojsonData) {
            return geojsonData;
        }

        var filteredFeatures = geojsonData.features;
        var top20Features = [];

        // Filtrar por barrios
        if (barriosSeleccionados && barriosSeleccionados.length > 0) {
            filteredFeatures = filteredFeatures.filter(function(feature) {
                return barriosSeleccionados.includes(feature.properties.Barrio);
            });
        }

        // Filtrar por características
        if (featureFilter && featureFilter.length > 0) {
            filteredFeatures = filteredFeatures.filter(function(feature) {
                return featureFilter.every(function(filter) {
                    return feature.properties[filter] === 1.0;
                });
            });
        }

        // Filtrar por Rating
        if (ratingRange && ratingRange.length === 2) {
            filteredFeatures = filteredFeatures.filter(function(feature) {
                var rating = feature.properties.Rating;
                return rating >= ratingRange[0] && rating <= ratingRange[1];
            });
        }

        // Filtrar por días de apertura
        if (diasApertura && diasApertura.length > 0) {
            filteredFeatures = filteredFeatures.filter(function(feature) {
                return diasApertura.every(function(day) {
                    return feature.properties[day + '_open'] && feature.properties[day + '_close'];
                });
            });
        }

        // Filtrar por nombre
        if (nombreFilter && nombreFilter.length > 0) {
            filteredFeatures = filteredFeatures.filter(function(feature) {
                return nombreFilter.includes(feature.properties.Nombre);
            });
        }

        if (zoom < 15) {
            // Si el zoom es menor a 15, calcular el top 10% fijo
            var reviewsList = filteredFeatures.map(function(feature) {
                return feature.properties['Cantidad Reviews'] !== 'Sin datos' ? feature.properties['Cantidad Reviews'] : 0;
            });

            // Calcular el umbral del top 10%
            reviewsList.sort(function(a, b) { return b - a; });
            var thresholdIndex = Math.floor(reviewsList.length * 0.1);
            var threshold = reviewsList[thresholdIndex] || 0;

            top20Features = filteredFeatures.filter(function(feature) {
                return feature.properties['Cantidad Reviews'] >= threshold;
            });

            return {type: 'FeatureCollection', features: top20Features};
        } else {
            // Si el zoom es mayor o igual a 15, filtrar por límites del mapa
            if (bounds && bounds.length === 2) {
                var swLat = bounds[0][0];
                var swLng = bounds[0][1];
                var neLat = bounds[1][0];
                var neLng = bounds[1][1];

                filteredFeatures = filteredFeatures.filter(function(feature) {
                    var lat = feature.geometry.coordinates[1];
                    var lng = feature.geometry.coordinates[0];
                    return lat >= swLat && lat <= neLat && lng >= swLng && lng <= neLng;
                });
            }
            return {type: 'FeatureCollection', features: filteredFeatures};
        }
    }
    """,
    Output('geojson-layer', 'data'),
    [Input('barrio-dropdown', 'value'),
     Input('feature-filter', 'value'),
     Input('rating-slider', 'value'),
     Input('dias-apertura-filter', 'value'),
     Input('nombre-filter', 'value'),
     Input('map', 'bounds'),
     Input('map', 'zoom')],
    State('clientside-store-data', 'data')
)

@app.callback(
    Output('filters-panel', 'style'),
    Input('toggle-button', 'n_clicks'),
    State('filters-panel', 'style')
)
def toggle_filters_panel(n_clicks, current_style):
    if n_clicks % 2 == 1:  # Si el número de clicks es impar, muestra los filtros
        return {'display': 'block'}
    else:  # Si es par, oculta los filtros
        return {'display': 'none'}

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
        'carto-positron': 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
        'carto-darkmatter': 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    }
    # Si map_style es None, usar 'carto-positron' como estilo por defecto
    return style_urls.get(map_style, style_urls['carto-positron'])

    
# Ejecuta la aplicación Dash
if __name__ == "__main__":
    app.run_server(debug=False)
