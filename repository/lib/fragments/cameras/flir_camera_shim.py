from typing import Any
from unittest.mock import MagicMock

PASSTHROUGH_NAMES = [
    "set_feature",
    "get_feature",
    "execute_command",
    "shutdown",
    "set_exposure_time",
    "try_pop_frame",
    "start_acquisition",
    "trigger",
]


class Camera:
    def __init__(self, device_mgr, name, loglevel):
        from aravis import Camera as _Camera

        self.cam = _Camera(name=name, loglevel=loglevel)

    def __getattr__(self, name):
        if name in PASSTHROUGH_NAMES:
            return getattr(self.cam, name)
        else:
            raise AttributeError


class MockCamera(MagicMock):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__()

        # Set our mock to return no frames, otherwise we'll loop forever trying to empty its buffer
        self.try_pop_frame = MagicMock()
        self.try_pop_frame.return_value = None
