from artiq.coredevice.core import Core
from artiq.experiment import kernel
from numpy import int64

from repository.lib.experiment_templates import RedMOTWithExperiment
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints


# Define a fragment which uses two Checkpoints:
# `end_of_blue_3d_mot_loading_checkpoint` and `after_data_saved_checkpoint`. The "_"
# at the start of the name communicates that this is a private class and is not
# intended to be used outside this module.
class _TimePrintingFragment(RedMOTCheckpoints):
    # Notice that we inherit from RedMOTCheckpoints, not Fragment. You must do
    # this if you want to use the Checkpoints from RedMOTCheckpoints.
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.timestamp_mu = int64(0)

    @kernel
    def end_of_blue_3d_mot_loading_checkpoint(self):
        # Note that we don't print here: that would consume lots of
        # slack and probably break other mixins.
        self.timestamp_mu = self.core.get_rtio_counter_mu()

    @kernel
    def after_data_saved_checkpoint(self):
        print("The time at the end of the blue MOT was:")
        print(self.timestamp_mu)


class TimePrintingMixin(RedMOTWithExperiment):
    """
    This Mixin prints the time at the end_of_blue_3d_mot checkpoint

    This isn't very useful, but is here as an example mixin to show how to use
    Checkpoints.
    """

    def build_fragment(self):
        # Call the parent build_fragment. Don't forget this, otherwise your
        # mixin will break all the other mixins!
        super().build_fragment()

        # Add the _TimePrintingFragment as a subfragment. Note that we can also
        # add normal Fragments here, but they won't get to use Checkpoints.
        self.setattr_fragment("time_printing_fragment", _TimePrintingFragment)

        # Optional, but recommended: type annotate the new fragment so that
        # autocompletion works in your IDE
        self.time_printing_fragment: _TimePrintingFragment
