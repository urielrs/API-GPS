from flask import Flask, request, jsonify, render_template
import os
import requests
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)
MAPQUEST_KEY = os.getenv('MAPQUEST_KEY')


"""
<!DOCTYPE html>
<html>
<head>
    <title> ¡Ooops! Error</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 50px; text-align: center; }
        .error-message { color: #d32f2f; background: #ffebee; padding: 20px; border-radius: 8px; display: inline-block; }
    </style>
</head>
<body>
    <div class="error-message">
        <h1>¡Oops! Ha ocurrido un error.</h1>
        <p>{{ error }}</p>
        <p>Por favor, intenta de nuevo más tarde.</p>
    </div>
</body>
</html>
"""

def validate_location_input(location_str):
    """
    Validates if the location string is a valid coordinate format (and range) or a general string.
    This helps in providing better feedback *before* sending to MapQuest.
    """
    regex_coords = r"^-?\d{1,3}\.\d+\s*,\s*-?\d{1,3}\.\d+$"
    if re.match(regex_coords, location_str):
        try:
            lat_str, lng_str = location_str.replace(' ', '').split(',')
            lat = float(lat_str)
            lng = float(lng_str)
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                return False, "Coordenadas fuera de rango."
            return True, None 
        except ValueError:
            return False, "Formato de coordenada inválido."
    
  
    if len(location_str) < 3: 
        return False, "La dirección es demasiado corta o inválida."
    
    return True, None 

@app.route('/')
def index():
    """Renders the main page."""
    if not MAPQUEST_KEY:
        return render_template('error.html',
                            error="Error de configuración: La API Key de MapQuest no se ha encontrado.")
    return render_template('index.html',
                         mapquest_key=MAPQUEST_KEY)

@app.route('/ruta', methods=['POST'])
def calcular_ruta():
    """Endpoint for calculating routes."""
    try:
        data = request.get_json()
        origen = data.get('origen', '').strip()
        destino = data.get('destino', '').strip()

        if not origen or not destino:
            return jsonify({'error': 'Se requieren origen y destino'}), 400

        
        is_origen_valid, origen_error = validate_location_input(origen)
        is_destino_valid, destino_error = validate_location_input(destino)

        if not is_origen_valid:
            return jsonify({'error': f'Origen inválido: {origen_error}'}), 400
        if not is_destino_valid:
            return jsonify({'error': f'Destino inválido: {destino_error}'}), 400

        params = {
            'key': MAPQUEST_KEY,
            'routeType': 'fastest',
            'unit': 'k', 
            'narrativeType': 'text',
            'locale': 'es_MX',
            'fullShape': True, 
            'generalize': 0 
        }

        params['from'] = origen
        params['to'] = destino

        response = requests.get(
            'https://www.mapquestapi.com/directions/v2/route',
            params=params,
            timeout=15 
        )
        response_data = response.json()

        
        if response.status_code != 200 or response_data.get('info', {}).get('statuscode') != 0:
            status_code = response_data.get('info', {}).get('statuscode', 'N/A')
            messages = response_data.get('info', {}).get('messages', [])
            error_msg = f"MapQuest API error (Status {status_code}): {' '.join(messages) if messages else 'Error desconocido'}"
            
            if "Cannot route from" in error_msg or "Cannot route to" in error_msg or "At least two locations are required" in error_msg:
                 error_msg = "No se pudo encontrar una ruta para las ubicaciones proporcionadas. Por favor, verifica las direcciones o coordenadas e intenta de nuevo."
            
            if response_data.get('info', {}).get('statuscode') == 400 and "One or more of the locations provided are not routable." in " ".join(messages):
                error_msg = "Una o ambas ubicaciones proporcionadas no son válidas."
            return jsonify({'error': error_msg}), 400

        route = response_data.get('route')
        if not route:
            return jsonify({'error': 'No se encontró la ruta en la respuesta de MapQuest.'}), 400

        
        if not route.get('shape', {}).get('shapePoints'):
            return jsonify({'error': 'La ruta no contiene datos válidos para dibujar en el mapa.'}), 400

        
        locations = route.get('locations')
        if not locations or len(locations) < 2:
            return jsonify({'error': 'No se pudieron obtener las coordenadas de origen y destino de la ruta.'}), 400

        start_lat_lng = (locations[0]['latLng']['lat'], locations[0]['latLng']['lng'])
        end_lat_lng = (locations[1]['latLng']['lat'], locations[1]['latLng']['lng'])

        return jsonify({
            'directions': [m['narrative'] for m in route['legs'][0]['maneuvers']],
            'distance_km': round(route['distance'], 2),
            'time_minutes': round(route['time'] / 60, 1), 
            'fuel_used_gal': round(route.get('fuelUsed', 0), 2), 
            'toll_distance_km': round(route.get('tollRoadDistance', 0), 2), 
            'shape': route['shape']['shapePoints'],
            'start_lat_lng': start_lat_lng, 
            'end_lat_lng': end_lat_lng      
        })

    except requests.exceptions.Timeout:
        return jsonify({'error': 'El servidor de MapQuest no respondió a tiempo. Intenta de nuevo más tarde.'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Error de conexión con la API de MapQuest: {str(e)}'}), 500
    except Exception as e:
        
        return jsonify({'error': f'Error interno del servidor: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)