import subprocess
import platform
import logging
from typing import List, Tuple, Optional

# Налаштування логування
logger = logging.getLogger(__name__)


class SNMPToolsChecker:
    """Клас для перевірки наявності SNMP-інструментів в системі"""

    # Константи для конфігурації
    TIMEOUT = 5
    CHECK_COMMANDS = [
        (
            ["snmpget", "--version"],
            "SNMP-інструменти встановлені (перевірка snmpget)",
            "snmpget"
        ),
        (
            ["snmpwalk", "-V"],
            "SNMP-інструменти встановлені (перевірка snmpwalk)",
            "snmpwalk"
        ),
    ]

    @classmethod
    def is_installed(cls) -> bool:
        """Перевіряє, чи встановлені SNMP-інструменти в системі"""
        for command, success_message in cls.CHECK_COMMANDS:
            try:
                subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=cls.TIMEOUT,
                )
                logger.info(success_message)
                return True
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                continue

        cls._log_installation_instructions()
        return False

    @staticmethod
    def _log_installation_instructions():
        """Повертає інструкції для встановлення SNMP"""
        os_name = platform.system()

        instructions = {
            "Linux": "sudo apt-get install snmp snmp-mibs-downloader",
            "Darwin": "brew install net-snmp",
            "Windows": "Завантажте з https://www.net-snmp.org/download.html",
        }

        instruction = instructions.get(
            os_name, "Встановіть net-snmp пакет для вашої ОС"
        )
        logger.warning(
            "SNMP утиліти не знайдено.\n" "Будь ласка, встановіть їх:\n" "%s",
            instruction,
        )


class SwitchSNMP:
    """Клас для роботи з комутатором через SNMP"""

    def __init__(self, host: str, community: str, version: str):
        self.host = host
        self.community = community
        self.version = version
        self.is_snmp_available = SNMPToolsChecker.is_installed()

    def get_snmp_data(self, oid: str):
        """Отримує дані за допомогою SNMP"""

        # Перевірка, чи доступні SNMP-інструменти
        if not self.is_snmp_available:
            logger.error("SNMP-інструменти недоступні - виконайте інструкції з логів")
            return None

        return None

    # Наприклад: get_system_info(), get_interfaces_stats(), тощо


if __name__ == "__main__":

    ZYXEL_CONFIG = {
        "host": "172.24.132.130",
        "community": "public",
        "version": "2c",
    }
    # Ініціалізація комутатора
    switch = SwitchSNMP(**ZYXEL_CONFIG)

    if switch.is_snmp_available:
        print("SNMP доступний")
        # Виклик методів для роботи з комутатором
    else:
        print("SNMP недоступний - виконайте інструкції з логів")
