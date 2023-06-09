import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from artiq.experiment import TBool
from ndscan.experiment import Fragment


class DebugLogger(Fragment):
    """
    A :class:`~.Fragment` for logging debug message during kernel execution

    Kernel logger messages break ARTIQ's realtime timings because they involve
    RPCs. However, it's still sometimes useful to have them in your code, and to
    `break_realtime()` after each call when you're debugging, but avoiding the
    penalty of calling RPCs or doing calculations that are not required most of
    the time.

    This Fragment implements a log method :meth:`.log` which will only print if
    the experiment is running at DEBUG level, but will be logged at INFO level
    to seperate it from the background noise of DEBUG messages. It guards these
    statements so that you can be sure that they're not present at compile-time
    when running at any other level

    It also exposes :meth:`.is_active()` to detect whether this logger is active, equivalent to::

        logger.isEnabledFor(logging.DEBUG)

    in normal python code.
    """

    kernel_invariants = {"_active"}

    def build_fragment(self, name=None):
        if name is None:
            name = __file__

        self.setattr_device("core")
        self.core: Core

        self.logger = logging.getLogger(name)

        self._active = self.logger.isEnabledFor(logging.DEBUG)

    @kernel
    def is_active(self) -> TBool:
        return self._active

    @kernel
    def log(self, msg, *args):
        if self._active:
            self.logger.info(msg, *args)
            self.core.break_realtime()
