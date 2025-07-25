import logging
from flask import Flask, jsonify
from flask_cors import CORS
from flask import render_template

from devices.switch_snmp import SwitchSNMP

app = Flask(__name__)
CORS(app)


@app.route("/")
def index():
    """Головна сторінка з HTML інтерфейсом"""
    return render_template("index.html")


@app.route("/api/device/ports")
def get_ports_device():
    """"""
    try:
        ZYXEL_CONFIG = {
            "host": "172.24.72.90",
            "community": "public",
            "version": "2c",
        }
        # Ініціалізація комутатора
        switch = SwitchSNMP(**ZYXEL_CONFIG)
        ports_data = switch.get_interfaces_stats()
        return jsonify(ports_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run()
