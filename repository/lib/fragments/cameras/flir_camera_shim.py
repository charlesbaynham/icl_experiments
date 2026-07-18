import gc
import logging
import time
from typing import Any
from unittest.mock import MagicMock

logger = logging.getLogger(__name__)

PASSTHROUGH_NAMES = [
    "set_feature",
    "get_feature",
    "execute_command",
    "set_exposure_time",
    "try_pop_frame",
    "start_acquisition",
    "stop_acquisition",
    "trigger",
]

# A controller that died uncleanly holds the GigE control channel until the
# camera's heartbeat expires (measured ~2.7 s on the Blackfly S)
OPEN_RETRY_TIMEOUT = 10.0
OPEN_RETRY_INTERVAL = 0.5


class Camera:
    """Owns the aravis connection lifecycle for a device-manager-cached camera.

    The ARTIQ device manager caches this object for the worker's lifetime, but
    ndscan's pause protocol runs ``host_cleanup`` (shutdown) then
    ``host_setup`` on resume against the same instance - so ``shutdown`` must
    be idempotent and ``reopen`` must bring the connection back. Without this,
    resuming a paused camera experiment hit an infinite ``__getattr__``
    recursion inside ``aravis.Camera`` (whose ``shutdown`` deletes ``cam``/
    ``dev``/``stream`` and whose ``__getattr__`` dereferences ``self.cam``).
    """

    def __init__(self, device_mgr, name, loglevel):
        self._name = name
        self._loglevel = loglevel
        self.cam = None
        self.reopen()

    def reopen(self):
        """(Re-)establish the camera connection; no-op when already open.

        Retries briefly: the control channel of a camera whose previous
        controller died uncleanly frees up on the heartbeat timeout.
        """
        if self.cam is not None:
            return

        from aravis import Camera as _Camera

        deadline = time.monotonic() + OPEN_RETRY_TIMEOUT
        while True:
            try:
                self.cam = _Camera(name=self._name, loglevel=self._loglevel)
                return
            except Exception as e:
                if time.monotonic() >= deadline:
                    raise
                logger.info("Camera %r not available (%s); retrying", self._name, e)
                time.sleep(OPEN_RETRY_INTERVAL)

    def shutdown(self):
        """Release the camera and its GigE control channel. Idempotent."""
        cam, self.cam = self.cam, None
        if cam is None:
            return

        try:
            cam.stop_acquisition()
        except Exception:
            logger.debug("stop_acquisition during shutdown failed", exc_info=True)
        try:
            cam.shutdown()
        except AttributeError:
            # aravis.Camera.shutdown() del's its attributes, so it is not
            # re-entrant if something already tore the object down
            pass

        del cam
        # aravis only drops python references; collect now so the GObjects
        # finalise and the control channel is surrendered immediately rather
        # than at some later gc
        gc.collect()

    def __getattr__(self, name):
        if name in PASSTHROUGH_NAMES:
            cam = self.__dict__.get("cam")
            if cam is None:
                raise RuntimeError(
                    f"FLIR camera {self._name!r} used after shutdown() - "
                    "reopen() it first (host_setup does this)"
                )
            return getattr(cam, name)
        raise AttributeError(name)


class MockCamera(MagicMock):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__()

        # Set our mock to return no frames, otherwise we'll loop forever trying to empty its buffer
        self.try_pop_frame = MagicMock()
        self.try_pop_frame.return_value = None
