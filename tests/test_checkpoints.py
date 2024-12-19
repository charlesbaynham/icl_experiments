from ndscan.experiment import ExpFragment
from ndscan.experiment import portable
from ndscan.experiment import run_fragment_once

from repository.lib.fragments.checkpoint_fragment import CheckpointFragment


class TestCheckpointFrag(CheckpointFragment):
    checkpoint_method_names = [
        "test_checkpoint_1",
        "test_checkpoint_2",
    ]

    @portable
    def test_checkpoint_1(self):
        self.test_checkpoint_1_subfragments()

    @portable
    def test_checkpoint_1_subfragments(self):
        pass

    @portable
    def test_checkpoint_2(self):
        self.test_checkpoint_2_subfragments()

    @portable
    def test_checkpoint_2_subfragments(self):
        pass


class TestCheckpointExpFragBase(TestCheckpointFrag, ExpFragment):
    def build_fragment(self):
        pass

    def run_once(self):
        # Run all the checkpoints in order for this test. Note that run_once is
        # not a kernel method here, so this will run on the host as all the
        # checkpoints are @portable
        self.test_checkpoint_1()
        self.test_checkpoint_2()


def test_can_run_with_default_implementations(fragment_precompiler):
    frag = fragment_precompiler(TestCheckpointExpFragBase)
    run_fragment_once(frag)


def test_default_implementations_call_subfragments(fragment_precompiler):
    sentinel = False

    class SubfragWithCheckpoint(TestCheckpointFrag):
        def build_fragment(self):
            pass

        @portable
        def test_checkpoint_1(self):
            nonlocal sentinel
            sentinel = True

            self.test_checkpoint_1_subfragments()

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

    class Bottom1(TestCheckpointFrag):
        def build_fragment(self):
            pass

        def test_checkpoint_1(self):
            nonlocal sentinel_1
            sentinel_1 = True

            self.test_checkpoint_1_subfragments()

    class Bottom2(TestCheckpointFrag):
        def build_fragment(self):
            pass

        def test_checkpoint_2(self):
            nonlocal sentinel_2
            sentinel_2 = True

            self.test_checkpoint_1_subfragments()

    class Middle(TestCheckpointFrag):
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
