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
    run_fragment_once(TestCheckpointExpFragBase)


def test_default_implementations_call_subfragments(fragment_precompiler):
    herald = False

    class SubfragWithCheckpoint(CheckpointFragment):
        def build_fragment(self):
            pass

        def test_checkpoint(self):
            nonlocal herald
            herald = True

            self.test_checkpoint_subfragments()

    class TestCheckpointExpFrag(TestCheckpointExpFragBase):
        def build_fragment(self):
            super().build_fragment()

            self.setattr_fragment("subfrag", SubfragWithCheckpoint)
            self.subfrag: SubfragWithCheckpoint

    result = run_fragment_once(TestCheckpointExpFrag)
