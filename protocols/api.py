import logging

import ros_api
from environs import Env

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Прочитайте змінні середовища
env = Env()
env.read_env()

router = ros_api.Api(*env.list("ROOT_ROUTER"))
# r = router.talk("/interface/wifi/capsman/remote-cap/provision\n=.id=*F")
r = router.talk("/interface/wifi/provisioning/print")
# r = router.talk("/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations=cfg-2-free-N")
# r = router.talk("/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations=")
print(r)


async def get_ros():
    return {}