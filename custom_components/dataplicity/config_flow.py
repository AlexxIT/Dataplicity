import logging
import re
import sys

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN, utils

_LOGGER = logging.getLogger(__name__)

RE_TOKEN = re.compile(r'https://www\.dataplicity\.com/([a-z0-9]+)\.py')


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, data=None, error=None):
        if sys.platform == 'win32':
            return self.async_abort(reason='win32')

        if self.hass.config.api.use_ssl:
            return self.async_abort(reason='ssl')

        if data is None:
            return self.async_show_form(
                step_id='user',
                data_schema=vol.Schema({
                    vol.Required('token'): str,
                }),
                errors={'base': error} if error else None
            )

        m = RE_TOKEN.search(data['token'])
        token = m[1] if m else data['token']

        if not token.isalnum():
            return await self.async_step_user(error='token')

        session = async_get_clientsession(self.hass)
        resp = await utils.register_device(session, token)
        if resp:
            return self.async_create_entry(title="Dataplicity", data={
                'auth': resp['auth'],
                'serial': resp['serial']
            }, description_placeholders={
                'device_url': resp['device_url']
            })

        return await self.async_step_user(error='auth')
