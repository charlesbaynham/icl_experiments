"""
Thread-safe, asyncio-wrapped and executorised interfaces for world-touching
interactions

These allow an asyncio event loop to schedule experiments, wait for their
results and query datasets. They must all be passed a `HasEnvironment` instance
which has:

* An artiq_thread_lock attribute (probably a threading.RLock)
* A scheduler attribute (an instance of
  :class:`artiq.master.scheduler.Scheduler`)
"""

import asyncio
import logging
import os
from typing import Callable

from artiq.experiment import HasEnvironment
from artiq.master.scheduler import Scheduler
from sipyco.sync_struct import Subscriber

# Get the IP address for connecting to the ARTIQ master from the environment
# variable ARTIQ_CONNECTION_IP. TODO: this isn't very portable - it would be
# better to get the bind address from the master instance somehow
SCHEDULER_PUBLISHER_HOST = os.getenv("ARTIQ_CONNECTION_IP", "::1")
SCHEDULER_PUBLISHER_PORT = 3250

logger = logging.getLogger(__name__)


def bind_inputs(loop: asyncio.AbstractEventLoop, artiq_hasenv: HasEnvironment):
    return {
        "get_dataset": _bind_get_dataset(loop, artiq_hasenv),
        "scheduler": _bind_SchedulerWrapper(loop, artiq_hasenv),
    }


def bind_outputs(loop: asyncio.AbstractEventLoop, artiq_hasenv: HasEnvironment):
    return {
        "scheduler": _bind_SchedulerWrapper(loop, artiq_hasenv),
        "run_and_wait": _bind_run_and_wait(loop, artiq_hasenv),
    }


def _bind_get_dataset(
    loop: asyncio.AbstractEventLoop, artiq_hasenv: HasEnvironment
) -> Callable:
    async def get_dataset(dataset):
        def f():
            with artiq_hasenv.artiq_thread_lock:
                return artiq_hasenv.get_dataset(dataset, archive=False)

        return await loop.run_in_executor(None, f)

    return get_dataset


def _bind_SchedulerWrapper(
    loop: asyncio.AbstractEventLoop, artiq_hasenv: HasEnvironment
) -> Scheduler:
    class SchedulerWrapper:
        def __getattr__(obj, attr):
            scheduler_attr = getattr(artiq_hasenv.scheduler, attr)

            async def f(*args, **kwargs):
                if callable(scheduler_attr):

                    def thread():
                        with artiq_hasenv.artiq_thread_lock:
                            return scheduler_attr(*args, **kwargs)

                    return await loop.run_in_executor(None, thread)
                else:
                    return scheduler_attr

            return f

    return SchedulerWrapper()


def _bind_run_and_wait(
    loop: asyncio.AbstractEventLoop, artiq_hasenv: HasEnvironment
) -> Callable:
    """
    Create a ``run_and_wait`` method which will run an Experiment and wait for
    it to conclude before returning
    """

    async def run_experiment(
        module_path: str, class_name: str, pipeline: str, args=None
    ):
        def thread():
            with artiq_hasenv.artiq_thread_lock:
                log_level = artiq_hasenv.scheduler.expid["log_level"]
                repo_rev = artiq_hasenv.scheduler.expid["repo_rev"]

                new_expid = {
                    "file": module_path,
                    "class_name": class_name,
                    "arguments": args or {},
                    "log_level": log_level,
                    "repo_rev": repo_rev,
                }

                return artiq_hasenv.scheduler.submit(pipeline, new_expid)

        rid = await loop.run_in_executor(None, thread)

        logger.debug("Submitted experiment %s with rid %s", class_name, rid)
        logger.debug("Full args: %s", args)

        return rid

    async def wait_for_rid(rid):
        logger.debug("Starting scheduler Subscriber for run_and_wait")

        latest_schedule = dict()

        rid_in_schedule = asyncio.Event()
        rid_completed = asyncio.Event()
        rid_did_run_done_stage = asyncio.Event()

        def update_schedule(x):
            latest_schedule.clear()
            latest_schedule.update(x)
            return latest_schedule

        def check_schedule(d):
            logger.debug("schedule: %s", [(k, i["status"]) for k, i in d.items()])

            if not rid_in_schedule.is_set() and rid in d:
                rid_in_schedule.set()

            if rid in d and d[rid]["status"] == "run_done":
                rid_did_run_done_stage.set()

            if rid_in_schedule.is_set() and rid not in d:
                rid_completed.set()

        schedule_subscriber = Subscriber(
            "schedule", update_schedule, lambda _: check_schedule(latest_schedule)
        )
        await schedule_subscriber.connect(
            SCHEDULER_PUBLISHER_HOST, SCHEDULER_PUBLISHER_PORT
        )

        try:
            logger.debug("Waiting for rid %s to be scheduled", rid)
            await rid_in_schedule.wait()
            logger.debug("Waiting for rid %s to be completed", rid)
            await rid_completed.wait()

            if rid_did_run_done_stage.is_set():
                logger.debug("rid %s ran successfully", rid)
            else:
                raise RuntimeError(f"rid {rid} failed to complete")
        finally:
            await schedule_subscriber.close()
            logger.debug("scheduler Subscriber shut down for run_and_wait")

    async def run_and_wait(module_path: str, class_name: str, pipeline: str):
        rid = await run_experiment(module_path, class_name, pipeline)
        await wait_for_rid(rid)

    return run_and_wait
