from ndscan.experiment import *

from repository.lib.fragments.checkpoint_fragment import CheckpointFragment


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
        # self.setattr_fragment("sub", DoInPostNarrowbandB)
        pass

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am fragment C")


class _CallAllHooksBase(CheckpointFragment, ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

    @kernel
    def run_once(self):
        self.end_of_blue_3d_mot_loading_hook()
        self.start_of_red_broadband_hook()
        self.end_of_broadband_mot_hook()
        self.post_narrowband_hook()
        self.pre_expansion_hook()
        self.post_sequence_cleanup_hook()
        self.after_data_saved_checkpoint()


class TestCheckpointsSingleFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)


class TestCheckpointsDefaultFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)

        self.subA: DoInPostNarrowbandA
        self.subC: DoInPostNarrowbandC

    @kernel
    def end_of_blue_3d_mot_loading_hook(self):
        self.subA.end_of_blue_3d_mot_loading_hook()
        self.subC.end_of_blue_3d_mot_loading_hook()


class TestCheckpointsOverriddenFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)

    def post_narrowband_hook(self):
        self.post_narrowband_hook_subfragments()
        print("Hello from post_narrowband_hook, I am TestCheckpointsOverridden")


TestCheckpointsSingle = make_fragment_scan_exp(TestCheckpointsSingleFrag)
TestCheckpointsDefault = make_fragment_scan_exp(TestCheckpointsDefaultFrag)
TestCheckpointsOverridden = make_fragment_scan_exp(TestCheckpointsOverriddenFrag)
