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
    frag = fragment_precompiler(TestCheckpointExpFragBase)
    result = run_fragment_once(frag)


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

    frag = fragment_precompiler(TestCheckpointExpFrag)
    result = run_fragment_once(frag)
