import logging
import os
import re
import sys
from subprocess import Popen, PIPE

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from ipaddress import IPv4Network

_LOGGER = logging.getLogger(__name__)


def install_package(
    package: str,
    upgrade: bool = True,
    target: str | None = None,
    constraints: str | None = None,
    timeout: int | None = None,
) -> bool:
    """Install dataplicity package via pip subprocess (avoids recursion with fake_install)."""
    args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        package,
        "--no-deps",
        "lomond==0.3.3",
    ]
    env = os.environ.copy()
    if timeout:
        args += ["--timeout", str(timeout)]
    if upgrade:
        args.append("--upgrade")
    if constraints is not None:
        args += ["--constraint", constraints]
    if target:
        args += ["--user"]
        env["PYTHONUSERBASE"] = os.path.abspath(target)

    _LOGGER.debug("Running pip command: args=%s", args)

    with Popen(
        args,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
        close_fds=False,
    ) as process:
        _, stderr = process.communicate()
        if process.returncode != 0:
            _LOGGER.error(
                "Unable to install package %s: %s",
                package,
                stderr.decode("utf-8").lstrip().strip(),
            )
            return False
    return True

PROVISION_URL = "https://app-api.dataplicity.com/device-gateway/provision/"
SH_URL_TEMPLATE = "https://dataplicity.com/{token}.sh"
RE_DEVICE_CLASS_HASH = re.compile(r"device_class_hash=([a-f0-9]{64})")


async def fetch_device_class_hash(session: ClientSession, token: str):
    try:
        r = await session.get(SH_URL_TEMPLATE.format(token=token))
        if r.status != 200:
            _LOGGER.error(f"Can't fetch install wrapper for token: {r.status}")
            return None
        text = await r.text()
        m = RE_DEVICE_CLASS_HASH.search(text)
        if not m:
            _LOGGER.error("device_class_hash not found in install wrapper")
            return None
        return m.group(1)
    except Exception:
        _LOGGER.exception("Can't fetch device_class_hash")
        return None


async def register_device(session: ClientSession, token: str, device_class_hash: str):
    try:
        r = await session.post(
            PROVISION_URL,
            data={
                "provisioning_key": token,
                "name": "Home Assistant",
                "device_class_hash": device_class_hash,
            },
            headers={"User-Agent": "Python-urllib/3.11"},
        )
        if r.status != 200:
            _LOGGER.error(f"Can't register dataplicity device: {r.status}")
            return None
        body = await r.json()
        serial = body.get("hash_id") or body.get("serial")
        auth = body.get("device_secret") or body.get("auth")
        if not serial or not auth:
            _LOGGER.error(f"Provisioning response missing creds: keys={list(body)}")
            return None
        return {"serial": serial, "auth": auth, "device_url": body.get("device_url", "")}
    except Exception:
        _LOGGER.exception("Can't register dataplicity device")
        return None


async def fix_middleware(hass: HomeAssistant):
    """Silent hack to allow Dataplicity wormhole (reverse proxy from 127.0.0.1)."""
    for f in hass.http.app.middlewares:
        if getattr(f, "__name__", None) != "forwarded_middleware":
            continue
        for i, var in enumerate(f.__code__.co_freevars):
            cell = f.__closure__[i]
            if var == "use_x_forwarded_for":
                if not cell.cell_contents:
                    cell.cell_contents = True
            elif var == "trusted_proxies":
                if not cell.cell_contents:
                    cell.cell_contents = [IPv4Network("127.0.0.1/32")]
        break


def import_client():
    try:
        from dataplicity import iptool
    except ImportError:
        pass
    else:
        iptool.get_all_interfaces = lambda: [("lo", "127.0.0.1")]

    try:
        from dataplicity import device_meta
    except ImportError:
        pass
    else:
        device_meta.get_os_version = lambda: "Linux"

    from dataplicity.client import Client

    return Client