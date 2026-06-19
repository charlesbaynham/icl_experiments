import asyncio
import logging
import threading
from typing import Awaitable
from typing import Callable

from artiq.experiment import EnvExperiment
from artiq.master.scheduler import Scheduler

from repository.lib.io import bind_inputs
from repository.lib.io import bind_outputs

logger = logging.getLogger(__name__)


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
        from repository.tests.test_echo import TestEcho

        test_experiment = TestEcho

        run_and_wait = self.io_outputs["run_and_wait"]
        run_and_wait: Callable[[str, str, str], Awaitable[None]]

        module = test_experiment.__module__
        class_name = test_experiment.__name__

        import importlib

        module_path = importlib.util.find_spec(module).origin

        logger.info(
            "Running %s experiment from %s via run_and_wait",
            class_name,
            module_path,
        )

        await run_and_wait(
            module_path=module_path,
            class_name=class_name,
            pipeline="scheduler_test",
        )
