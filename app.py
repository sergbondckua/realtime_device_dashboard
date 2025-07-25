import logging

from flask import Flask, jsonify
from flask_cors import CORS
from flask import render_template

from config import DEVICE_IP_MAP
from devices.switch_snmp import SwitchSNMP

app = Flask(__name__)
CORS(app)

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    """Головна сторінка з HTML інтерфейсом"""
    return render_template("network_monitor/index.html")

@app.route("/api/devices/")
def get_devices():
    return jsonify(DEVICE_IP_MAP)


@app.route("/api/device/<device_id>/", methods=["GET"])
def get_device_monitoring(device_id):
    """
    Отримання інформації про порти комутатора за його ID.

    Приймає device_id як параметр шляху та повертає JSON-об'єкт
    з даними портів або повідомленням про помилку.
    """

    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICE_IP_MAP.get(device_id)
        if not device_ip:
            return (
                jsonify(
                    {"error": f"Пристрій з ID '{device_id}' не знайдено."}
                ),
                404,
            )

        # Ініціалізація комутатора з отриманою IP-адресою
        switch = SwitchSNMP(device_ip)

        # Отримання статистики інтерфейсів
        system_info = switch.get_system_info()
        ports_data = switch.get_interfaces_stats()

        # Повернення даних у форматі JSON
        return jsonify(system_info=system_info, interfaces=ports_data)

    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        # Логування помилки тут було б доречним.
        logger.error(
            "Помилка при отриманні даних для пристрою %s: %s",
            device_id,
            str(e),
        )
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
