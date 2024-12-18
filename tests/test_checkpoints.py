from repository.lib.fragments.checkpoint_fragment import CheckpointFragment
from ndscan.experiment import *


class TestCheckpointExpFragBase(CheckpointFragment, ExpFragment):
    def build_fragment(self):
        pass

    def run_once(self):
        # Run all the checkpoints in order
        # FIXME more
        self.test_checkpoint()


def test_can_run_with_default_implementations(fragment_precompiler):
    fragment_precompiler(TestCheckpointExpFragBase)
