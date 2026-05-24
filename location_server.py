from flask import Flask, jsonify, request

app = Flask(__name__)

# Хранилище координат: { driver_id: { 'lat': ..., 'lon': ..., 'timestamp': ... } }
driver_locations = {}

# Вспомогательная функция для CORS
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, ngrok-skip-browser-warning'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@app.route('/update_location', methods=['POST', 'OPTIONS'])
def update_location():
    if request.method == 'OPTIONS':
        return add_cors_headers(jsonify({'status': 'ok'}))
    data = request.get_json()
    if not data:
        return add_cors_headers(jsonify({'error': 'Invalid data'}), 400)
    driver_id = str(data.get('driver_id'))
    lat = data.get('lat')
    lon = data.get('lon')
    if driver_id and lat is not None and lon is not None:
        driver_locations[driver_id] = {
            'lat': lat,
            'lon': lon,
            'timestamp': data.get('timestamp', '')
        }
        return add_cors_headers(jsonify({'status': 'ok'}))
    return add_cors_headers(jsonify({'error': 'Missing fields'}), 400)

@app.route('/get_driver_location', methods=['GET', 'OPTIONS'])
def get_driver_location():
    if request.method == 'OPTIONS':
        return add_cors_headers(jsonify({'status': 'ok'}))
    driver_id = request.args.get('driver_id')
    if driver_id and driver_id in driver_locations:
        return add_cors_headers(jsonify(driver_locations[driver_id]))
    return add_cors_headers(jsonify({'error': 'Driver not found'}), 404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)