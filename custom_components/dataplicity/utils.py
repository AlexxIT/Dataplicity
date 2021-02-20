import logging

from aiohttp import ClientSession

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
