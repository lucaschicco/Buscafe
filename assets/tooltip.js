window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.timestampToDate = function(value) {
    var date = new Date(value * 1000); // Convertir el timestamp a milisegundos
    var year = date.getFullYear();
    var month = ("0" + (date.getMonth() + 1)).slice(-2);
    var day = ("0" + date.getDate()).slice(-2);
    return year + '-' + month + '-' + day;
};