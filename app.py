import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

import ros_api
from environs import Env
from flask import Flask, jsonify
from flask_cors import CORS
from flask import render_template

from config import DEVICES_IP_MAP
from protocols.api import get_ros
from protocols.snmp import AsyncSwitchSNMP
from monitor.devices import start_monitoring, status

app = Flask(__name__)
CORS(app)

# Прочитайте змінні середовища
env = Env()
env.read_env()

start_monitoring()
router = ros_api.Api(*env.list("ROOT_ROUTER"))

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


@app.route("/ros-control")
async def ros_control_page():
    """Сторінка управління RouterOS Provisioning"""
    try:
        # Перевіряємо поточний стан для обох інтерфейсів
        current_config = router.talk("/interface/wifi/provisioning/print")

        # Визначаємо чи увімкнено provisioning для кожного інтерфейсу
        interface_0_enabled = False
        interface_1_enabled = False
        interface_0_config = ""
        interface_1_config = ""

        if current_config:
            for item in current_config:
                if item.get("master-configuration") == "cfg-2-staff-N":
                    interface_0_config = item.get("slave-configurations", "")
                    interface_0_enabled = bool(interface_0_config)
                elif item.get("master-configuration") == "cfg-5-staff-AC":
                    interface_1_config = item.get("slave-configurations", "")
                    interface_1_enabled = bool(interface_1_config)

        # Загальний статус - обидва інтерфейси повинні бути увімкнені
        is_enabled = interface_0_enabled and interface_1_enabled

        return render_template(
            "network_monitor/ros_control.html",
            is_enabled=is_enabled,
            interface_0_enabled=interface_0_enabled,
            interface_1_enabled=interface_1_enabled,
            interface_0_config=interface_0_config,
            interface_1_config=interface_1_config,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    except Exception as e:
        logger.error("Помилка при отриманні стану RouterOS: %s", str(e), exc_info=True)
        return render_template(
            "network_monitor/ros_control.html",
            is_enabled=False,
            interface_0_enabled=False,
            interface_1_enabled=False,
            interface_0_config="",
            interface_1_config="",
            error=str(e),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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


@app.route("/api/ros/provisioning/enable", methods=["POST"])
async def enable_provisioning():
    """API для вмикання WiFi Provisioning"""
    try:
        # Вмикаємо provisioning для обох інтерфейсів
        result1 = router.talk(
            "/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations=cfg-2-free-N"
        )
        result2 = router.talk(
            "/interface/wifi/provisioning/set\n=numbers=1\n=slave-configurations=cfg-5-free-AC"
        )

        # Список всіх Remote Cap інтерфейсів
        remote_cap_interfaces = router.talk(
            "/interface/wifi/capsman/remote-cap/print"
        )

        # Виконуємо provision-all для Remote Cap
        for interface in remote_cap_interfaces:
            id_iface = interface[".id"]
            router.talk(
                f"/interface/wifi/capsman/remote-cap/provision\n=.id={id_iface}"
            )

        logger.info(
            "WiFi Provisioning увімкнено для обох інтерфейсів та виконано provision-all"
        )

        return jsonify(
            {
                "success": True,
                "message": "WiFi Provisioning успішно увімкнено для обох інтерфейсів",
                "status": "enabled",
                "details": {
                    "interface_0": "cfg-2-free-N",
                    "interface_1": "cfg-5-free-AC",
                    "provision_all": "executed",
                },
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    except Exception as e:
        logger.error("Помилка при вмиканні provisioning: %s", str(e))
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Помилка при вмиканні: {str(e)}",
                    "status": "error",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ),
            500,
        )


@app.route("/api/ros/provisioning/disable", methods=["POST"])
async def disable_provisioning():
    """API для вимикання WiFi Provisioning"""
    try:
        # Вимикаємо provisioning для обох інтерфейсів
        result1 = router.talk(
            "/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations="
        )
        result2 = router.talk(
            "/interface/wifi/provisioning/set\n=numbers=1\n=slave-configurations="
        )

        # Список всіх Remote Cap інтерфейсів
        remote_cap_interfaces = router.talk(
            "/interface/wifi/capsman/remote-cap/print"
        )

        # Виконуємо provision-all для Remote Cap
        for interface in remote_cap_interfaces:
            id_iface = interface[".id"]
            router.talk(
                f"/interface/wifi/capsman/remote-cap/provision\n=.id={id_iface}"
            )

        logger.info(
            "WiFi Provisioning вимкнено для обох інтерфейсів та виконано provision-all"
        )

        return jsonify(
            {
                "success": True,
                "message": "WiFi Provisioning успішно вимкнено для обох інтерфейсів",
                "status": "disabled",
                "details": {
                    "interface_0": "disabled",
                    "interface_1": "disabled",
                    "provision_all": "executed",
                },
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    except Exception as e:
        logger.error("Помилка при вимиканні provisioning: %s", str(e))
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Помилка при вимиканні: {str(e)}",
                    "status": "error",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ),
            500,
        )


@app.route("/api/ros/provisioning/status", methods=["GET"])
async def get_provisioning_status():
    """API для отримання поточного стану provisioning"""
    try:
        # Отримуємо поточну конфігурацію
        current_config = router.talk("/interface/wifi/provisioning/print")

        interface_0_enabled = False
        interface_1_enabled = False
        interface_0_config = ""
        interface_1_config = ""
        config_details = []

        if current_config:
            for item in current_config:
                config_details.append(item)
                if "numbers" in item:
                    if (
                        item["numbers"] == "0"
                        and "slave-configurations" in item
                    ):
                        interface_0_config = item.get(
                            "slave-configurations", ""
                        )
                        interface_0_enabled = bool(interface_0_config)
                    elif (
                        item["numbers"] == "1"
                        and "slave-configurations" in item
                    ):
                        interface_1_config = item.get(
                            "slave-configurations", ""
                        )
                        interface_1_enabled = bool(interface_1_config)

        # Загальний статус
        is_enabled = interface_0_enabled and interface_1_enabled

        return jsonify(
            {
                "success": True,
                "is_enabled": is_enabled,
                "interfaces": {
                    "interface_0": {
                        "enabled": interface_0_enabled,
                        "config": interface_0_config or "disabled",
                    },
                    "interface_1": {
                        "enabled": interface_1_enabled,
                        "config": interface_1_config or "disabled",
                    },
                },
                "config_details": config_details,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    except Exception as e:
        logger.error("Помилка при отриманні статусу: %s", str(e))
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Помилка при отриманні статусу: {str(e)}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ),
            500,
        )


@app.errorhandler(404)
def not_found(error):
    return (
        render_template(
            "network_monitor/error.html",
            error_message=f"Сторінка не знайдена, {error}",
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(error):
    return (
        render_template(
            "network_monitor/error.html",
            error_message=f"Внутрішня помилка сервера, {error}",
        ),
        500,
    )


@app.template_filter("human_speed")
def human_speed(value):
    try:
        value = int(value)
        if value >= 1_000_000_000:
            return f"{value // 1_000_000_000} Gbps"
        elif value >= 1_000_000:
            return f"{value // 1_000_000} Mbps"
        elif value >= 1_000:
            return f"{value // 1_000} kbps"
        else:
            return f"{value} bps"
    except:
        return "0"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
