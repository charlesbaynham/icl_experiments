from ndscan.experiment import ExpFragment
from ndscan.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints


class DoInPostNarrowbandA(RedMOTCheckpoints):
    def build_fragment(self):
        pass

    @kernel
    def post_narrowband_checkpoint(self):
        self.post_narrowband_checkpoint_subfragments()
        print("Hello from post_narrowband_checkpoint, I am fragment A")


class DoInPostNarrowbandB(RedMOTCheckpoints):
    def build_fragment(self):
        pass

    @kernel
    def post_narrowband_checkpoint(self):
        self.post_narrowband_checkpoint_subfragments()
        print("Hello from post_narrowband_checkpoint, I am fragment B")


class DoInPostNarrowbandC(RedMOTCheckpoints):
    def build_fragment(self):
        self.setattr_fragment("sub", DoInPostNarrowbandB)

    @kernel
    def post_narrowband_checkpoint(self):
        self.post_narrowband_checkpoint_subfragments()
        print("Hello from post_narrowband_checkpoint, I am fragment C")


class _CallAllHooksBase(RedMOTCheckpoints, ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

    @kernel
    def run_once(self):
        self.DMA_initialization_checkpoint()
        self.pre_sequence_checkpoint()
        self.end_of_blue_3d_mot_loading_checkpoint()
        self.start_of_red_broadband_checkpoint()
        self.end_of_broadband_mot_checkpoint()
        self.post_narrowband_checkpoint()
        self.pre_expansion_checkpoint()
        self.after_first_imaging_pulse_checkpoint()
        self.post_sequence_cleanup_checkpoint()
        self.after_data_saved_checkpoint()


class TestCheckpointsSingleFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)


class TestCheckpointsDoubleFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subB", DoInPostNarrowbandB)


class TestCheckpointsNestedFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)

        self.subA: DoInPostNarrowbandA
        self.subC: DoInPostNarrowbandC

    @kernel
    def end_of_blue_3d_mot_loading_checkpoint(self):
        self.subA.end_of_blue_3d_mot_loading_checkpoint()
        self.subC.end_of_blue_3d_mot_loading_checkpoint()


class TestCheckpointsOverriddenFrag(_CallAllHooksBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("subA", DoInPostNarrowbandA)
        self.setattr_fragment("subC", DoInPostNarrowbandC)

    def post_narrowband_checkpoint(self):
        self.post_narrowband_checkpoint_subfragments()
        print("Hello from post_narrowband_checkpoint, I am TestCheckpointsOverridden")


TestCheckpointsSingle = make_fragment_scan_exp(TestCheckpointsSingleFrag)
TestCheckpointsDouble = make_fragment_scan_exp(TestCheckpointsDoubleFrag)
TestCheckpointsNested = make_fragment_scan_exp(TestCheckpointsNestedFrag)
TestCheckpointsOverridden = make_fragment_scan_exp(TestCheckpointsOverriddenFrag)
