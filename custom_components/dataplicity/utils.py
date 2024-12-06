import logging
import os
import sys
from ipaddress import IPv4Network
from subprocess import Popen, PIPE

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def register_device(session: ClientSession, token: str):
    try:
        r = await session.post(
            "https://www.dataplicity.com/install/",
            data={"name": "Home Assistant", "serial": "None", "token": token},
        )
        if r.status != 200:
            _LOGGER.error(f"Can't register dataplicity device: {r.status}")
            return None
        return await r.json()
    except:
        _LOGGER.exception("Can't register dataplicity device")
        return None


async def fix_middleware(hass: HomeAssistant):
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
        if f.__name__ != "forwarded_middleware":
            continue
        #  https://til.hashrocket.com/posts/ykhyhplxjh-examining-the-closure
        for i, var in enumerate(f.__code__.co_freevars):
            cell = f.__closure__[i]
            if var == "use_x_forwarded_for":
                if not cell.cell_contents:
                    cell.cell_contents = True
            elif var == "trusted_proxies":
                if not cell.cell_contents:
                    cell.cell_contents = [IPv4Network("127.0.0.1/32")]


def install_package(
    package: str,
    upgrade: bool = True,
    target: str | None = None,
    constraints: str | None = None,
    timeout: int | None = None,
) -> bool:
    # important to use no-deps, because:
    # - enum34 has problems with Hass constraints
    # - six has problmes with Python 3.12
    args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        package,
        "--no-deps",
        # "enum34==1.1.6",
        # "six==1.10.0",
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
        close_fds=False,  # required for posix_spawn
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
