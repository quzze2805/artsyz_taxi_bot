from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)

# Хранилище: { driver_id: { lat, lon, timestamp } }
driver_locations = {}

@app.route('/get_driver_location')
def get_driver_location():
    driver_id = request.args.get('driver_id')
    if driver_id and driver_id in driver_locations:
        return jsonify(driver_locations[driver_id])
    return jsonify({'error': 'Driver not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)