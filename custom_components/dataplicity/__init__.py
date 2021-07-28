from threading import Thread

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.requirements import async_process_requirements
from homeassistant.util import package

from . import utils

DOMAIN = 'dataplicity'


async def async_setup(hass: HomeAssistant, hass_config: dict):
    # fix problems with `enum34==1000000000.0.0` constraint in Hass
    # https://github.com/home-assistant/core/commit/45f6f4443aa897a9c9c89cedbf3be6c7748cca94
    # but it's not a problem in latest python versions
    real_install = package.install_package

    def fake_install(*args, **kwargs):
        kwargs.pop('constraints')
        return real_install(*args, **kwargs)

    try:
        package.install_package = fake_install
        # latest dataplicity has bug with redirect_port
        await async_process_requirements(hass, DOMAIN, ['dataplicity==0.4.40'])
        return True
    except:
        return False
    finally:
        package.install_package = real_install


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # fix: type object 'array.array' has no attribute 'tostring'
    from dataplicity import iptool
    iptool.get_all_interfaces = lambda: [('lo', '127.0.0.1')]

    # fix: module 'platform' has no attribute 'linux_distribution'
    from dataplicity import device_meta
    device_meta.get_os_version = lambda: "Linux"

    from dataplicity.client import Client

    hass.data[DOMAIN] = client = Client(serial=entry.data['serial'],
                                        auth_token=entry.data['auth'])
    # replace default 80 port to Hass port (usual 8123)
    client.port_forward.add_service('web', hass.config.api.port)
    Thread(name=DOMAIN, target=client.run_forever).start()

    async def hass_stop(event):
        client.exit()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hass_stop)

    await utils.fix_middleware(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    from dataplicity.client import Client

    client: Client = hass.data[DOMAIN]
    client.exit()

    return True
