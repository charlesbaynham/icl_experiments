import logging

import pytest
from fixtures import *  # noqa

logging.basicConfig(level=logging.WARNING)
logging.getLogger("qbutler").setLevel(logging.DEBUG)


def _patch_urukul_init_deterministic_ids():
    """Give pyaion's UrukulInit deterministic device IDs under test.

    pyaion's ``UrukulInit.host_setup`` computes ``hash(device)`` (a memory
    address) for its channel-dedup IDs and orders its CPLD list via
    ``list(set(...))`` (address order). Both values are embedded into the
    compiled kernel, which makes otherwise identical test compiles produce
    different binaries from process to process, defeating the kernel
    compilation cache (see "Kernel Caching" in AGENTS.md). Within the test
    suite the IDs are arbitrary (they only need to be unique per device and
    stable within the process), so replace them with sequence numbers and
    canonicalize the CPLD order. The proper fix is the same change in
    pyaion itself.
    """
    try:
        from pyaion.fragments.urukul_init import UrukulInit
    except ImportError:
        return

    assigned_ids = {}

    def device_id(device):
        return assigned_ids.setdefault(id(device), len(assigned_ids) + 1)

    original_host_setup = UrukulInit.host_setup

    def host_setup(self):
        original_host_setup(self)
        # Re-establish a deterministic CPLD order (first encounter over the
        # deterministically ordered channel list; the dummy fallback, which
        # has no associated channel, keeps its place).
        encounter_order = {}
        for channel in self.ad9910s + self.ad9912s:
            cpld = getattr(channel, "cpld", None)
            if cpld is not None and id(cpld) not in encounter_order:
                encounter_order[id(cpld)] = len(encounter_order)
        self.urukuls.sort(key=lambda cpld: encounter_order.get(id(cpld), -1))
        self.ad9910_ids = [device_id(d) for d in self.ad9910s]
        self.ad9912_ids = [device_id(d) for d in self.ad9912s]
        self.urukul_ids = [device_id(d) for d in self.urukuls]

    UrukulInit.host_setup = host_setup


_patch_urukul_init_deterministic_ids()


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
