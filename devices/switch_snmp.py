import logging
import re
import subprocess
import platform
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Any

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class InterfaceType(Enum):
    """Типи інтерфейсів за RFC 1213"""

    ETHERNET = "6"  # ethernetCsmacd
    FAST_ETHERNET = "62"  # fastEther
    GIGABIT_ETHERNET = "117"  # gigabitEthernet
    OTHER = "1"  # other
    PPPOE = "23"  # pppoe
    WIRELESS = "71"  # wireless
    SOFTWARE_LOOPBACK = "24"  # softwareLoopback


class OSInstructions(Enum):
    """Інструкції для встановлення SNMP на різних ОС"""

    DEBIAN_UBUNTU = "sudo apt-get install snmp snmp-mibs-downloader"
    DARWIN = "brew install net-snmp"
    WINDOWS = "Завантажте з https://www.net-snmp.org/download.html"
    REDHAT_CENTOS = "sudo yum install net-snmp-utils"
    ARCH = "sudo pacman -S net-snmp"
    DEFAULT = "Встановіть net-snmp пакет для вашої ОС"


@dataclass
class SNMPConfig:
    """Конфігурація для SNMP з'єднання"""

    # Таймаути
    COMMAND_TIMEOUT: int = 5
    SNMP_TIMEOUT: int = 10

    # Обмеження
    MAX_PHYSICAL_INTERFACES: int = 48
    MAX_RETRIES: int = 3

    # Підтримувані версії SNMP
    SUPPORTED_VERSIONS: tuple = ("1", "2c", "3")

    # Типи інтерфейсів для фільтрації (фізичні інтерфейси)
    PHYSICAL_INTERFACE_TYPES: tuple = (
        InterfaceType.ETHERNET.value,
        InterfaceType.FAST_ETHERNET.value,
        InterfaceType.GIGABIT_ETHERNET.value,
        InterfaceType.PPPOE.value,
        InterfaceType.WIRELESS.value,
    )


class SNMPToolsChecker:
    """Клас для перевірки наявності SNMP-інструментів в системі"""

    @classmethod
    def is_installed(cls) -> bool:
        """
        Перевіряє, чи встановлені ВСІ необхідні SNMP-інструменти в системі.
        Повертає True, лише якщо всі інструменти доступні.
        """
        config = SNMPConfig()

        try:
            # Перевіряємо кожну команду, передаючи її назву
            subprocess.run(
                ["snmpwalk", "-V"],  # "-V" для перевірки версії
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=config.COMMAND_TIMEOUT,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as e:
            # Якщо команда не знайдена або виконується з помилкою,
            # логуємо це та одразу повертаємо False.
            logger.error(f"Помилка перевірки інструмента SNMP: {e}")
            cls._log_installation_instructions()
            return False

        # Якщо цикл завершився без помилок, значить всі інструменти на місці.
        logger.debug("Усі необхідні SNMP-інструменти успішно знайдені.")
        return True

    @classmethod
    def _log_installation_instructions(cls):
        """Виводить інструкції для встановлення SNMP залежно від ОС"""
        os_name = platform.system()

        # Маппінг ОС на інструкції
        os_instructions = {
            "Linux": cls._get_linux_instruction(),
            "Darwin": OSInstructions.DARWIN.value,
            "Windows": OSInstructions.WINDOWS.value,
        }

        instruction = os_instructions.get(
            os_name, OSInstructions.DEFAULT.value
        )
        logger.warning(
            "SNMP утиліти не знайдено.\n" "Будь ласка, встановіть їх:\n" "%s",
            instruction,
        )

    @staticmethod
    def _get_linux_instruction() -> str:
        """Повертає специфічну інструкцію для Linux дистрибутивів"""
        try:
            # Визначаємо дистрибутив
            with open("/etc/os-release", "r") as f:
                content = f.read().lower()
                if "ubuntu" in content or "debian" in content:
                    return OSInstructions.DEBIAN_UBUNTU.value
                elif (
                    "centos" in content
                    or "rhel" in content
                    or "fedora" in content
                ):
                    return OSInstructions.REDHAT_CENTOS.value
                elif "arch" in content:
                    return OSInstructions.ARCH.value
        except FileNotFoundError:
            pass

        return OSInstructions.DEFAULT.value


class SwitchSNMP:
    """Клас для роботи з комутатором через SNMP
    Args:
        host (str): IP-адреса комутатора
        community (str): Community-строка для доступу до комутатора
        version (str): Версія SNMP-протоколу (2c)
    """

    # Системні OID
    OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"  # sysDescr (Модель, прошивка)
    OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"  # sysName (Системне ім'я)
    OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"  # sysUpTime (Uptime)
    OID_SYS_MAC = "1.3.6.1.2.1.2.2.1.6"  # ifPhysAddress (базова MAC-адреса)

    # Константи OID для статистики інтерфейсів
    OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"  # ifIndex
    OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"  # ifType
    OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"  # ifSpeed
    OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr
    OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"  # ifInOctets
    OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"  # ifOutOctets
    OID_IF_IN_PKTS = "1.3.6.1.2.1.2.2.1.11"  # ifInUcastPkts
    OID_IF_OUT_PKTS = "1.3.6.1.2.1.2.2.1.17"  # ifOutUcastPkts
    OID_IF_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus
    OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"  # ifAdminStatus
    OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias
    OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"  # ifInErrors
    OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"  # ifOutErrors

    def __init__(
        self, host: str, community: str = "public", version: str = "2c"
    ):
        self.host = host
        self.community = community
        self.version = version
        self.config = SNMPConfig()
        self.is_snmp_available = SNMPToolsChecker.is_installed()

    def get_system_info(self) -> Dict[str, Optional[str]]:
        """
        Отримує основну системну інформацію про пристрій.
        """
        if not self.is_snmp_available:
            logger.error(
                "Спроба отримати інформацію про систему при відсутніх SNMP інструментах"
            )
            return {}

        info = {}
        try:
            # Отримання системної інформації
            info["model"] = self._snmp_get(self.OID_SYS_DESCR)
            info["system_name"] = self._snmp_get(self.OID_SYS_NAME)
            info["uptime"] = self._snmp_get(self.OID_SYS_UPTIME)

            # Отримання базової MAC-адреси
            # Для цього потрібно пройтися по інтерфейсах і знайти один з базовим типом
            if_types = self._snmp_walk(self.OID_IF_TYPE)
            mac_address_found = False
            for index, if_type in if_types.items():
                # Зазвичай, MAC-адреса VLAN-інтерфейсу або першого фізичного
                # є базовою. Тут ми беремо перший, що має MAC-адресу.
                if if_type in ("6", "62", "117"):
                    mac_oid = f"{self.OID_SYS_MAC}.{index}"
                    mac_addr = self._snmp_get(mac_oid).strip()
                    if mac_addr:
                        info["mac_address"] = mac_addr.replace(" ", ":")
                        mac_address_found = True
                        break
            if not mac_address_found:
                info["mac_address"] = "00:00:00:00:00:00"

        except Exception as e:
            logger.error(
                f"Критична помилка при отриманні системної інформації: {e}",
                exc_info=True,
            )
            return {}

        logger.info("Системна інформація успішно отримана.")
        return info

    def get_interfaces_stats(self) -> Dict[int, Dict[str, Any]]:
        """
        Отримує статистику всіх інтерфейсів комутатора через SNMP

        Returns:
            Словник зі статистикою інтерфейсів, де ключ - індекс інтерфейсу,
            значення - словник з параметрами інтерфейсу
        """
        if not self.is_snmp_available:
            logger.error(
                "Спроба отримати статистику при відсутніх SNMP інструментах"
            )
            return {}

        try:
            # Отримуємо індекси інтерфейсів
            if_indexes = self._get_interface_indexes()
            if not if_indexes:
                logger.warning("Не знайдено жодного інтерфейсу")
                return {}

            # Список всіх OID для збору даних
            target_oids = [
                self.OID_IF_DESCR,
                self.OID_IF_ALIAS,
                self.OID_IF_SPEED,
                self.OID_IF_IN_OCTETS,
                self.OID_IF_OUT_OCTETS,
                self.OID_IF_IN_PKTS,
                self.OID_IF_OUT_PKTS,
                self.OID_IF_IN_ERRORS,
                self.OID_IF_OUT_ERRORS,
                self.OID_IF_STATUS,
                self.OID_IF_ADMIN_STATUS,
            ]

            # Збираємо всі дані за один прохід
            oid_data = {}
            for oid in target_oids:
                oid_data[oid] = self._snmp_walk(oid)

            # Формуємо результат для кожного інтерфейсу
            interfaces = {}
            for index in if_indexes:
                interfaces[index] = {
                    "name": oid_data[self.OID_IF_DESCR].get(index, ""),
                    "alias": oid_data[self.OID_IF_ALIAS].get(index, ""),
                    "speed": self._safe_int(oid_data[self.OID_IF_SPEED].get(index, "")),
                    "in_octets": self._safe_int(oid_data[self.OID_IF_IN_OCTETS].get(index)),
                    "out_octets": self._safe_int(oid_data[self.OID_IF_OUT_OCTETS].get(index)),
                    "in_pkts": self._safe_int(oid_data[self.OID_IF_IN_PKTS].get(index)),
                    "out_pkts": self._safe_int(oid_data[self.OID_IF_OUT_PKTS].get(index)),
                    "in_errors": self._safe_int(oid_data[self.OID_IF_IN_ERRORS].get(index)),
                    "out_errors": self._safe_int(oid_data[self.OID_IF_OUT_ERRORS].get(index)),
                    "admin_status": self._safe_int(oid_data[self.OID_IF_ADMIN_STATUS].get(index)),
                    "status": self._safe_int(oid_data[self.OID_IF_STATUS].get(index)),
                }

            logger.info(
                "Отримано статистику для %d інтерфейсів", len(interfaces)
            )
            return interfaces

        except Exception as e:
            logger.error(
                f"Критична помилка при отриманні статистики: {e}",
                exc_info=True,
            )
            return {}

    def _get_interface_indexes(self) -> List[int]:
        """Отримує список індексів фізичних інтерфейсів"""
        indexes = self._snmp_walk(self.OID_IF_TYPE)
        return [
            index
            for index, value_raw in indexes.items()
            if (value_raw in self.config.PHYSICAL_INTERFACE_TYPES and
                index <= self.config.MAX_PHYSICAL_INTERFACES)
        ]

    @staticmethod
    def _safe_int(value_raw: Optional[str]) -> int:
        """Безпечне перетворення в ціле число"""
        try:
            return int(value_raw) if value_raw else 0
        except (ValueError, TypeError):
            return 0

    def _snmp_walk(self, base_oid: str) -> Dict[int, str]:
        """
        Виконує SNMP walk для вказаного базового OID і повертає результати

        Args:
            base_oid: Базовий OID для walk

        Returns:
            Словник {index: value} для всіх знайдених інстансів
        """
        try:
            command = [
                "snmpwalk",
                "-v",
                self.version,
                "-c",
                self.community,
                "-OQ",  # Тільки OID та значення
                "-On",  # Числовий формат
                self.host,
                base_oid,
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return self._parse_snmp_walk_output(result.stdout)

        except subprocess.CalledProcessError as e:
            logger.error(
                f"SNMP помилка (код {e.returncode}): {e.stderr.strip()}"
            )
            return {}
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут виконання SNMP walk для OID {base_oid}")
            return {}
        except Exception as e:
            logger.error(f"Невідома помилка при виконанні SNMP walk: {e}")
            return {}

    def _snmp_get(self, oid: str) -> Optional[str]:
        """
        Виконує SNMP get для вказаного OID і повертає значення.

        Args:
            oid: OID для запиту.

        Returns:
            Значення або None, якщо сталася помилка.
        """
        try:
            command = [
                "snmpget",
                "-v",
                self.version,
                "-c",
                self.community,
                "-Oqv",  # Вивід лише значення
                self.host,
                oid,
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            value_raw = result.stdout.strip()
            # Видаляємо лапки зі значення якщо вони є
            if value_raw.startswith('"') and value_raw.endswith('"'):
                value_raw = value_raw[1:-1]
            return value_raw

        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Не вдалося отримати OID {oid}. Помилка: {e.stderr.strip()}"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Таймаут виконання SNMP get для OID {oid}")
            return None
        except Exception as e:
            logger.warning(f"Невідома помилка при SNMP get для OID {oid}: {e}")
            return None

    @staticmethod
    def _parse_snmp_walk_output(output: str) -> Dict[int, str]:
        """Парсить вивід SNMP walk у словник {index: value}"""
        results = {}
        pattern = r"\.(\d+)\s*=\s*(.*?)$"

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            # Шукаємо останню цифрову групу в OID
            match = re.search(pattern, line)
            if not match:
                continue

            index = int(match.group(1))
            value_raw = match.group(2).strip()

            # Видаляємо лапки зі значення якщо вони є
            if value_raw.startswith('"') and value_raw.endswith('"'):
                value_raw = value_raw[1:-1]

            results[index] = value_raw

        return results


if __name__ == "__main__":

    # Ініціалізація комутатора
    switch = SwitchSNMP("172.16.127.147")

    if switch.is_snmp_available:
        # Виклик методів для роботи з комутатором
        stats = switch.get_interfaces_stats()

        # Отримуємо та виводимо системну інформацію
        system_info = switch.get_system_info()
        print("--- Системна інформація ---")
        for key, value in system_info.items():
            print(f"{key}: {value}")
        print("-" * 40)

        for idx, data in stats.items():
            print(f"Інтерфейс {idx}:")
            print(f"  Ім'я: {data['name']}")
            print(f"  Alias: {data['alias']}")
            print(f"  Вхідні байти: {data['in_octets']}")
            print(f"  Вихідні байти: {data['out_octets']}")
            print(f"  Помилки: {data['in_errors']} / {data['out_errors']}")
            print(f"  Статус: {data['status']}")
            print("-" * 40)
    else:
        print("SNMP недоступний - виконайте інструкції з логів")
