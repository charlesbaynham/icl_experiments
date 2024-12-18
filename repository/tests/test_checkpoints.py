from repository.lib.fragments.checkpoint_fragment import CheckpointFragment
from ndscan.experiment import *


class DoInPostNarrowbandA(CheckpointFragment):
    def build_fragment(self):
        pass

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am fragment A")


class DoInPostNarrowbandB(CheckpointFragment):
    def build_fragment(self):
        pass

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am fragment B")


class DoInPostNarrowbandC(CheckpointFragment):
    def build_fragment(self):
        self.setattr_fragment("sub", DoInPostNarrowbandB)

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am fragment C")


class TestCheckpointsDefaultFrag(CheckpointFragment, ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)


class TestCheckpointsOverriddenFrag(CheckpointFragment, ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)

    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am TestCheckpointsOverridden")


TestCheckpointsDefault = make_fragment_scan_exp(TestCheckpointsDefaultFrag)
TestCheckpointsOverridden = make_fragment_scan_exp(TestCheckpointsOverriddenFrag)
