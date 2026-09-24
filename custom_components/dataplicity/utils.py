import logging
import os
import re
import sys
import threading
from ipaddress import IPv4Network
from subprocess import Popen, PIPE

from aiohttp import ClientSession
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

RE_DEVICE_CLASS_HASH = re.compile(r"device_class_hash=([a-f0-9]{64})")


async def fetch_device_class_hash(session: ClientSession, token: str):
    try:
        r = await session.get(f"https://dataplicity.com/{token}.sh")
        if r.status != 200:
            _LOGGER.error(f"Can't fetch install wrapper for token: {r.status}")
            return None

        text = await r.text()
        if m := RE_DEVICE_CLASS_HASH.search(text):
            return m.group(1)

        _LOGGER.error("device_class_hash not found in install wrapper")
    except Exception as e:
        _LOGGER.error("Can't fetch device_class_hash", exc_info=e)

    return None


async def register_device(session: ClientSession, token: str, device_class_hash: str):
    try:
        r = await session.post(
            "https://app-api.dataplicity.com/device-gateway/provision/",
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

        data = await r.json()
        serial = data.get("hash_id") or data.get("serial")
        auth = data.get("device_secret") or data.get("auth")
        if serial and auth:
            device_url = data.get("device_url") or "https://www.dataplicity.com/"
            return {"serial": serial, "auth": auth, "device_url": device_url}

        _LOGGER.error(f"Provisioning response missing creds: keys={list(data)}")
    except Exception as e:
        _LOGGER.error("Can't register dataplicity device", exc_info=e)

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
        if getattr(f, "__name__", None) != "forwarded_middleware":
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


class _ConnectionEOF(BaseException):
    """Signals that a forwarded socket has reached EOF.

    Deliberately not an Exception: `portforward.Connection.run` wraps recv()
    in `except Exception`, which would swallow the signal.
    """


class _EOFAwareSocket:
    """Socket proxy that raises _ConnectionEOF on a zero byte recv()."""

    def __init__(self, sock):
        self._sock = sock

    def recv(self, *args, **kwargs):
        data = self._sock.recv(*args, **kwargs)
        if not data:
            raise _ConnectionEOF
        return data

    def __getattr__(self, name):
        return getattr(self._sock, name)


def fix_portforward_eof():
    """Stop a peer closed socket from spinning a CPU core at 100%.

    In dataplicity 0.4.40 `portforward.Connection.run` reacts to a zero byte
    recv() with a `break` that leaves only the inner `for` loop over the poll
    results, not the outer `while`. EOF keeps the socket permanently readable,
    so poll() returns immediately and the thread calls recv() forever.

    The loop's only per connection exit is `self.channel.is_closed`, but
    `Channel.close()` merely *requests* a close - `is_closed` flips when the
    m2m server answers with notify_close. While the tunnel is unhealthy, which
    is exactly when sockets get aborted, that answer never arrives and the
    thread keeps burning a core. `close_event` is no alternative: it is shared
    by the whole port forwarding service, so a single connection must not set
    it. Reloading the config entry does not help either, the orphaned thread
    just keeps running.

    The connection therefore leaves the loop on its own: recv() raises a
    BaseException that escapes the `except Exception` around it, still runs the
    `finally` cleanup of run(), and is swallowed by a wrapper.
    """
    from dataplicity import portforward

    if getattr(portforward, "_eof_fix_applied", False):
        return

    connect = portforward.Connection._connect
    run = portforward.Connection.run

    def _connect(self) -> bool:
        connected = connect(self)
        if connected and self.socket is not None:
            self.socket = _EOFAwareSocket(self.socket)
        return connected

    def _run(self):
        try:
            run(self)
        except _ConnectionEOF:
            _LOGGER.debug("Port forward connection closed by peer")

    portforward.Connection._connect = _connect
    portforward.Connection.run = _run
    portforward._eof_fix_applied = True


# lomond sends a ping every 30 s by default; drop the connection when no pong
# came back for three ping periods (lomond suggests "double ping_rate").
M2M_PING_TIMEOUT = 90


def fix_m2m_lifecycle():
    """Make the m2m websocket stoppable and detect dead connections.

    `Client.exit()` only stops the agent's poll loop. `Client.close()`, which the
    loop calls on the way out, is a no-op in the agent, so the m2m websocket
    thread keeps running. It could not be stopped anyway: `WSClient.run` calls
    lomond's `persist()` without an `exit_event`, and `WSClient.close()` only
    closes the current socket, after which `persist()` reconnects. Every config
    entry reload therefore leaks one more m2m connection that keeps
    re-associating the device with the Dataplicity server.

    `persist()` is also called with `ping_timeout=None`, so a half-open
    connection (e.g. after the router drops the NAT mapping) is never noticed:
    the thread waits forever on a dead socket and the tunnel shows "Device not
    connected" until Home Assistant restarts.

    Fix both by giving every `WSClient` an exit event, passing it and a ping
    timeout to `persist()`, and making `Client.close()` shut down the m2m and
    port forwarding parts.
    """
    from dataplicity import client as dp_client
    from dataplicity.m2m import wsclient
    from lomond.persist import persist

    if getattr(wsclient, "_lifecycle_fix_applied", False):
        return

    WSClient = wsclient.WSClient
    init = WSClient.__init__
    close = WSClient.close

    def _init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        self.exit_event = threading.Event()

    def _run(self):
        try:
            with self.websocket:
                for event in persist(
                    self.websocket,
                    ping_timeout=M2M_PING_TIMEOUT,
                    exit_event=self.exit_event,
                ):
                    try:
                        self.on_event(event)
                    except Exception:
                        _LOGGER.exception("Error handling m2m websocket event")
        except Exception:
            _LOGGER.exception("Unhandled error from m2m websocket")
        # The agent's run() ends with self.on_close(), which WSClient doesn't
        # have - it was never reached before. persist() already emitted
        # "disconnected" (-> on_disconnected), so just let the manager close
        # its terminals.
        self.manager.on_client_close()

    def _close(self, *args, **kwargs):
        # set first: persist() checks the event once the socket is closed
        self.exit_event.set()
        close(self, *args, **kwargs)

    def _client_close(self):
        # called from Client.run_forever() after exit(), in the agent thread
        if port_forward := getattr(self, "port_forward", None):
            port_forward.close_event.set()
        if m2m := getattr(self, "m2m", None):
            m2m.close()

    WSClient.__init__ = _init
    WSClient.run = _run
    WSClient.close = _close
    dp_client.Client.close = _client_close
    wsclient._lifecycle_fix_applied = True


def import_client():
    # fix: type object 'array.array' has no attribute 'tostring'
    from dataplicity import iptool

    iptool.get_all_interfaces = lambda: [("lo", "127.0.0.1")]

    # fix: module 'platform' has no attribute 'linux_distribution'
    from dataplicity import device_meta

    device_meta.get_os_version = lambda: "Linux"

    # fix: 100% CPU spin when a forwarded socket is closed by the peer
    fix_portforward_eof()

    # fix: leaked m2m connections on reload, dead tunnel after network blips
    fix_m2m_lifecycle()

    from dataplicity.client import Client

    return Client
