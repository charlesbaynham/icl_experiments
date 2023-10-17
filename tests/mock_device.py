from typing import Any
from unittest.mock import MagicMock


class MockDevice(MagicMock):
    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__()
