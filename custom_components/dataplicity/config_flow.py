import logging
import re
import sys

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN, utils

_LOGGER = logging.getLogger(__name__)

RE_INSTALL_URL = re.compile(r"dataplicity\.com/([A-Za-z0-9_-]+)")
RE_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_-]+$")
RE_RECOVERY = re.compile(r"^([A-Za-z0-9_-]{8,}):(.+)$")


class ConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, data=None, error=None):
        if sys.platform == "win32":
            return self.async_abort(reason="win32")

        if self.hass.config.api.use_ssl:
            return self.async_abort(reason="ssl")

        if data is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("token"): str,
                    }
                ),
                errors={"base": error} if error else None,
            )

        token = data["token"].strip()

        if m := RE_RECOVERY.match(token):
            serial, auth = m.group(1), m.group(2).strip()
            return self.async_create_entry(
                title="Dataplicity",
                data={"auth": auth, "serial": serial},
                description_placeholders={"device_url": ""},
            )

        # 2026.05 link format https://app-api.dataplicity.com/3-XXXXXXXX.py
        if m := RE_INSTALL_URL.search(token):
            token = m.group(1)

        token = re.sub(r"^\d-", "", token)

        if not RE_TOKEN_CHARS.match(token):
            return await self.async_step_user(error="token")

        session = async_get_clientsession(self.hass)

        device_class_hash = await utils.fetch_device_class_hash(session, token)
        if device_class_hash is None:
            return await self.async_step_user(error="token")

        if resp := await utils.register_device(session, token, device_class_hash):
            return self.async_create_entry(
                title="Dataplicity",
                data={"auth": resp["auth"], "serial": resp["serial"]},
                description_placeholders={"device_url": resp["device_url"]},
            )

        return await self.async_step_user(error="auth")
