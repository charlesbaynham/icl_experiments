from typing import Any
from unittest.mock import MagicMock


class MockAndorCamera(MagicMock):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__()

        # Set our mock to return no frames, otherwise we'll loop forever trying to empty its buffer
        self.get_vsspeed = MagicMock()
        self.get_vsspeed.return_value = 3.3

        self.vsspeed = 3.3

        self.get_EMCCD_gain = MagicMock()
        self.get_EMCCD_gain.return_value = (0, False)
