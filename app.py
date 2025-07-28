import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from flask import Flask, jsonify
from flask_cors import CORS
from flask import render_template

from config import DEVICES_IP_MAP
from devices.switch_snmp import AsyncSwitchSNMP
from monitor.devices import start_monitoring, status

app = Flask(__name__)
CORS(app)
start_monitoring()

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@app.context_processor
def inject_now():
    return {"now": datetime.now()}


async def get_list_devices_data() -> Dict[str, Any]:
    """Отримати дані про всі пристрої"""

    # Отримання даних
    devices = list(status.values())

    # Оновлення timestamp
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for device in devices:
        device["timestamp"] = current_time

    online_count = sum(1 for device in devices if device["alive"])
    offline_count = len(devices) - online_count

    return {
        "devices": devices,
        "online_count": online_count,
        "offline_count": offline_count,
        "total_count": len(devices),
        "timestamp": current_time,
    }


async def get_device_data(device_ip: str) -> Dict[str, Any]:
    """Функція для отримання даних про пристрій"""

    # Знаходимо пристрій за IP
    device = next(
        (d for d in list(status.values()) if d["ip"] == device_ip), None
    )
    if not device:
        return {}

    # Ініціалізація комутатора з отриманою IP-адресою
    switch = AsyncSwitchSNMP(device_ip)
    if not switch:
        return {}

    # Отримання статистики комутатора
    stats, system_info = await asyncio.gather(
        switch.get_interfaces_stats(), switch.get_system_info()
    )

    if device["alive"]:
        return {
            "device_ip": device_ip,
            "device_name": device["name"],
            "device_status": device["alive"],
            "interfaces": stats,
            "system_info": system_info,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    else:
        return {
            "device_ip": device_ip,
            "device_name": device["name"],
            "device_status": False,
            "interfaces": None,
            "system_info": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


@app.route("/")
async def index():
    """Головна сторінка з HTML інтерфейсом"""
    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0]["ip"]
        if not device_ip:
            return {}

        data = await get_list_devices_data()

        # Повернення даних у форматі JSON
        return render_template(
            "network_monitor/index.html",
            devices=data["devices"],
            online_count=data["online_count"],
            offline_count=data["offline_count"],
            total_count=data["total_count"],
            timestamp=data["timestamp"],
        )

    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        logger.error("Помилка при отриманні даних: %s", str(e))
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500


# Сторінка деталей пристрою
@app.route("/device/<device_ip>")
async def device_detail(device_ip: str):
    """Сторінка деталей конкретного пристрою"""
    device_data = await get_device_data(device_ip)

    if not device_data:
        return (
            render_template(
                "network_monitor/error.html",
                error_message=f"Пристрій з IP {device_ip} не знайдено",
            ),
            404,
        )

    return render_template(
        "network_monitor/device_details.html", **device_data
    )


@app.route("/api/devices")
async def api_devices():
    """API endpoint для отримання списку пристроїв (для AJAX)"""
    try:
        data = await get_list_devices_data()
        return jsonify(data)
    except Exception as e:
        logger.error("Помилка при отриманні даних: %s", str(e))
        return (
            jsonify(
                {
                    "error": str(e),
                    "devices": [],
                    "online_count": 0,
                    "offline_count": 0,
                    "total_count": 0,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ),
            500,
        )


@app.route("/api/device/<device_ip>")
async def api_device_detail(device_ip: str):
    """API endpoint для отримання деталей пристрою (для AJAX)"""
    try:
        device_data = await get_device_data(device_ip)
        if not device_data:
            return (
                jsonify({"error": f"Пристрій з IP {device_ip} не знайдено"}),
                404,
            )
        return jsonify(device_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/devices/all", methods=["GET"])
async def get_devices_stats():
    """
    Отримання інформації про порти комутатора за його ID.

    Приймає device_id як параметр шляху та повертає JSON-об'єкт
    з даними портів або повідомленням про помилку.
    """

    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0]["ip"]
        if not device_ip:
            return (
                jsonify({"error": f"Пристрій не знайдено."}),
                404,
            )

        # Ініціалізація комутатора з отриманою IP-адресою
        switch = AsyncSwitchSNMP(device_ip)

        multi_results = await switch.get_multiple_switches_stats(
            DEVICES_IP_MAP
        )

        # Повернення даних у форматі JSON
        return jsonify(multi_results)

    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        # Логування помилки тут було б доречним.
        logger.error("Помилка при отриманні даних: %s", str(e))
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500


@app.errorhandler(404)
def not_found(error):
    return (
        render_template(
            "network_monitor/error.html", error_message="Сторінка не знайдена"
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(error):
    return (
        render_template(
            "network_monitor/error.html",
            error_message="Внутрішня помилка сервера",
        ),
        500,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
