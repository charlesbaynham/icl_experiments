import asyncio
import logging
import threading
from typing import Awaitable
from typing import Callable

from artiq.experiment import EnvExperiment
from artiq.master.scheduler import Scheduler

from repository.lib.io import bind_inputs
from repository.lib.io import bind_outputs
from repository.tests.test_echo import TestEcho

logger = logging.getLogger(__name__)
TEST_EXPERIMENT = TestEcho


class TestScheduling(EnvExperiment):
    def build(self):
        self.setattr_device("scheduler")
        self.scheduler: Scheduler

    def prepare(self):
        self.artiq_thread_lock = threading.RLock()
        loop = asyncio.get_event_loop()
        self.io_inputs = bind_inputs(loop, self)
        self.io_outputs = bind_outputs(loop, self)

    def run(self):
        # Launch an asyncio loop
        loop = asyncio.get_event_loop()
        logger.info("Starting TestScheduling")
        loop.run_until_complete(self.async_run())
        logger.info("TestScheduling completed")

    async def async_run(self):
        run_and_wait = self.io_outputs["run_and_wait"]
        run_and_wait: Callable[[str, str, str], Awaitable[None]]

        logger.info("Running %s experiment via run_and_wait", TEST_EXPERIMENT.__name__)

        await run_and_wait(
            module_path=TEST_EXPERIMENT.__module__.__file__,
            class_name=TEST_EXPERIMENT.__name__,
            pipeline="scheduler_test",
        )
