import inspect
from threading import Thread

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.requirements import async_process_requirements
from homeassistant.util import package

from . import utils

DOMAIN = "dataplicity"


async def async_setup(hass: HomeAssistant, hass_config: dict):
    real_install = package.install_package

    def fake_install(pkg: str, *args, **kwargs):
        if pkg == "dataplicity==0.4.40":
            return utils.install_package(pkg, *args, **kwargs)
        return real_install(pkg, *args, **kwargs)

    try:
        package.install_package = fake_install

        # latest dataplicity has bug with redirect_port
        await async_process_requirements(hass, DOMAIN, ["dataplicity==0.4.40"])

        # fix Python 3.11 support
        if not hasattr(inspect, "getargspec"):

            def getargspec(*args):
                spec = inspect.getfullargspec(*args)
                return spec.args, spec.varargs, spec.varkw, spec.defaults

            inspect.getargspec = getargspec

        return True
    except:
        return False
    finally:
        package.install_package = real_install


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # fix https://github.com/AlexxIT/Dataplicity/issues/29
    Client = await hass.async_add_executor_job(utils.import_client)

    hass.data[DOMAIN] = client = Client(
        serial=entry.data["serial"], auth_token=entry.data["auth"]
    )
    # replace default 80 port to Hass port (usual 8123)
    client.port_forward.add_service("web", hass.config.api.port)
    Thread(name=DOMAIN, target=client.run_forever).start()

    async def hass_stop(event):
        client.exit()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hass_stop)

    await utils.fix_middleware(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    client = hass.data[DOMAIN]
    client.exit()
    return True
