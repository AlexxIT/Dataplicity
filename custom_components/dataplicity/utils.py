import logging
from ipaddress import IPv4Network

from aiohttp import ClientSession
from homeassistant.helpers.typing import HomeAssistantType

_LOGGER = logging.getLogger(__name__)


async def register_device(session: ClientSession, token: str):
    try:
        r = await session.post('https://www.dataplicity.com/install/', data={
            'name': "Home Assistant", 'serial': 'None', 'token': token
        })
        if r.status != 200:
            _LOGGER.error(f"Can't register dataplicity device: {r.status}")
            return None
        return await r.json()
    except:
        _LOGGER.exception("Can't register dataplicity device")
        return None


async def fix_middleware(hass: HomeAssistantType):
    """Dirty hack for HTTP integration. Plug and play for usual users...

    [v2021.7] Home Assistant will now block HTTP requests when a misconfigured
    reverse proxy, or misconfigured Home Assistant instance when using a
    reverse proxy, has been detected.

    http:
      use_x_forwarded_for: true
      trusted_proxies:
      - 127.0.0.1
    """
    for f in hass.http.app.middlewares:
        if f.__name__ != 'forwarded_middleware':
            continue
        #  https://til.hashrocket.com/posts/ykhyhplxjh-examining-the-closure
        for i, var in enumerate(f.__code__.co_freevars):
            cell = f.__closure__[i]
            if var == 'use_x_forwarded_for':
                if not cell.cell_contents:
                    cell.cell_contents = True
            elif var == 'trusted_proxies':
                if not cell.cell_contents:
                    cell.cell_contents = [IPv4Network('127.0.0.1/32')]
