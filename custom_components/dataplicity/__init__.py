from threading import Thread

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.requirements import async_process_requirements
from homeassistant.util import package

DOMAIN = 'dataplicity'


async def async_setup(hass: HomeAssistant, hass_config: dict):
    # fix problems with `enum34==1000000000.0.0` constraint in Hass
    real_install = package.install_package

    def fake_install(*args, **kwargs):
        kwargs.pop('constraints')
        return real_install(*args, **kwargs)

    try:
        package.install_package = fake_install
        await async_process_requirements(hass, DOMAIN, [DOMAIN])
        return True
    except:
        return False
    finally:
        package.install_package = real_install


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # fix: module 'platform' has no attribute 'linux_distribution'
    from dataplicity import device_meta
    device_meta.get_os_version = lambda: "Linux"

    from dataplicity.client import Client

    hass.data[DOMAIN] = client = Client(serial=entry.data['serial'],
                                        auth_token=entry.data['auth'])
    # replace default 80 port to 8123
    client.port_forward.add_service('web', 8123)
    Thread(name=DOMAIN, target=client.run_forever).start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    from dataplicity.client import Client

    client: Client = hass.data[DOMAIN]
    client.exit()

    return True
