import ros_api

router = ros_api.Api("0.0.0.0", user="", password="")
# r = router.talk("/interface/wifi/capsman/remote-cap/print")
# r = router.talk("/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations=cfg-2-free-N")
r = router.talk("/interface/wifi/provisioning/set\n=numbers=0\n=slave-configurations=")
print(r)


async def get_ros():
    return router.talk("/interface/wifi/provisioning/set/0/slave-configurations=cfg-2-free-N")