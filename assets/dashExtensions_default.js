window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(cluster) {
            var zoom = cluster.getAllChildMarkers()[0]._map.getZoom();
            var size = Math.min(zoom * 4, 40); // Ajusta el tamaño según el nivel de zoom
            return L.divIcon({
                html: '<img src="' + cluster.getAllChildMarkers()[0].options.icon.options.iconUrl + '" style="width:' + size + 'px; height:' + size + 'px;"/>',
                className: 'custom-icon',
                iconSize: [size, size]
            });
        }

    }
});