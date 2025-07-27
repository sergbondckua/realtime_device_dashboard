import asyncio
import logging
from datetime import datetime

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


# Фільтри для Jinja2
@app.template_filter("format_bytes")
def format_bytes_filter(value):
    if value >= 10**9:
        return f"{value / 10**9:.2f} GB"
    elif value >= 10**6:
        return f"{value / 10**6:.2f} MB"
    elif value >= 10**3:
        return f"{value / 10**3:.2f} KB"
    return f"{value} B"


@app.template_filter("format_packets")
def format_packets_filter(value):
    if value >= 10**6:
        return f"{value / 10**6:.2f}M"
    elif value >= 10**3:
        return f"{value / 10**3:.1f}K"
    return f"{value}"


@app.template_filter("format_speed")
def format_speed_filter(value):
    if value >= 10**9:
        return f"{value / 10**9:.1f} Gbps"
    return f"{value / 10**6:.0f} Mbps"


async def get_devices_data() -> dict:
    """Функція для отримання даних про пристрої"""
    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0][0]
        if not device_ip:
            return {}

        # Ініціалізація комутатора з отриманою IP-адресою
        switch = AsyncSwitchSNMP(device_ip)

        return await switch.get_multiple_switches_stats(DEVICES_IP_MAP)
    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        logger.error("Помилка при отриманні даних: %s", str(e))
        return {}


@app.route("/")
async def index():
    """Головна сторінка з HTML інтерфейсом"""
    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0][0]
        if not device_ip:
            return {}

        devices_data = list(status.values())
        online_count = sum(1 for device in devices_data if device["alive"])
        offline_count = len(devices_data) - online_count

        # Повернення даних у форматі JSON
        return render_template(
            "network_monitor/index.html",
            devices=devices_data,
            online_count=online_count,
            offline_count=offline_count,
            last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        logger.error("Помилка при отриманні даних: %s", str(e))
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500


# Сторінка деталей пристрою
@app.route("/device/<ip>")
async def device_details(ip):
    switch = AsyncSwitchSNMP(ip)
    if not switch:
        return "Device not found", 404

    # Отримання статистики комутатора
    stats, system_info = await asyncio.gather(
        switch.get_interfaces_stats(), switch.get_system_info()
    )
    active_ports = [
        iface for iface in stats.values() if iface.oper_status == 1
    ]

    return render_template(
        "network_monitor/device_details.html",
        device_ip=ip,
        system_info=system_info,
        interfaces=stats,
        active_ports_count=len(active_ports),
        total_ports_count=len(stats),
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/api/devices/")
async def get_devices():
    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0][0]
        if not device_ip:
            return {}

        devices_data = {}
        for device in DEVICES_IP_MAP:
            switch = AsyncSwitchSNMP(*device)
            devices_data[device[0]] = dict(
                system_info=await switch.get_system_info()
            )
    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        logger.error("Помилка при отриманні даних: %s", str(e))
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500
    return jsonify(devices_data)


@app.route("/api/devices/stats", methods=["GET"])
async def get_devices_stats():
    """
    Отримання інформації про порти комутатора за його ID.

    Приймає device_id як параметр шляху та повертає JSON-об'єкт
    з даними портів або повідомленням про помилку.
    """

    try:
        # Перевірка наявності device_id в мапі IP-адрес
        device_ip = DEVICES_IP_MAP[0][0]
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


@app.route("/api/device/stats/<device_ip>", methods=["GET"])
async def get_device_stats(device_ip):
    try:
        # Ініціалізація комутатора з отриманою IP-адресою
        switch = AsyncSwitchSNMP(device_ip)

        # Отримання статистики комутатора
        stats, system_info = await asyncio.gather(
            switch.get_interfaces_stats(), switch.get_system_info()
        )

        # Повернення статистики у форматі JSON
        return jsonify(system_info=system_info, interfaces=stats)

    except Exception as e:
        # Обробка винятків та повернення повідомлення про помилку з кодом 500
        # Логування помилки тут було б доречним.
        logger.error("Помилка при отриманні даних: %s", str(e))
        return jsonify({"error": f"Внутрішня помилка сервера: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
