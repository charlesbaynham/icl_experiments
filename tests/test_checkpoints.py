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
    run_fragment_once(frag)


def test_default_implementations_call_subfragments(fragment_precompiler):
    sentinel = False

    class SubfragWithCheckpoint(CheckpointFragment):
        def build_fragment(self):
            pass

        def test_checkpoint(self):
            nonlocal sentinel
            sentinel = True

            self.test_checkpoint_subfragments()

    class TestCheckpointExpFrag(TestCheckpointExpFragBase):
        def build_fragment(self):
            super().build_fragment()

            self.setattr_fragment("subfrag", SubfragWithCheckpoint)
            self.subfrag: SubfragWithCheckpoint

    frag = fragment_precompiler(TestCheckpointExpFrag)
    assert not sentinel
    run_fragment_once(frag)
    assert sentinel


def test_default_implementations_call_subfragments_squared(fragment_precompiler):
    sentinel_1 = False
    sentinel_2 = False

    class Bottom1(CheckpointFragment):
        def build_fragment(self):
            pass

        def test_checkpoint(self):
            nonlocal sentinel_1
            sentinel_1 = True

            self.test_checkpoint_subfragments()

    class Bottom2(CheckpointFragment):
        def build_fragment(self):
            pass

        def test_checkpoint(self):
            nonlocal sentinel_2
            sentinel_2 = True

            self.test_checkpoint_subfragments()

    class Middle(CheckpointFragment):
        def build_fragment(self):
            self.setattr_fragment("subfrag1", Bottom1)
            self.setattr_fragment("subfrag2", Bottom2)

    class Top(TestCheckpointExpFragBase):
        def build_fragment(self):
            super().build_fragment()

            self.setattr_fragment("subfrag", Middle)

    frag = fragment_precompiler(Top)
    assert not sentinel_1
    assert not sentinel_2
    run_fragment_once(frag)
    assert sentinel_1
    assert sentinel_2
