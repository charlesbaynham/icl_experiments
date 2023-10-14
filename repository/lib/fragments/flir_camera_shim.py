from typing import Any
from unittest.mock import MagicMock

from aravis import Camera as _Camera


class Camera(_Camera):
    def __init__(self, device_mgr, name, loglevel):
        super().__init__(name, loglevel)


class MockCamera(MagicMock):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__()

        # Set our mock to return no frames, otherwise we'll loop forever trying to empty its buffer
        self.try_pop_frame = MagicMock()
        self.try_pop_frame.return_value = None
