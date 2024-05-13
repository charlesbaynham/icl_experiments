import logging

from artiq.experiment import kernel
from artiq.experiment import TFloat
from artiq.experiment import TList

from repository.lib import constants
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.ramping_phase import GeneralRampingPhase
from repository.lib.fragments.red_mot.red_mot_mixins.pumped_lattice import (
    DroppedPumpedLatticeMixin,
)


logger = logging.getLogger(__name__)


class _BiasFieldRamper(GeneralRampingPhase):
    # Configure general ramp to ramp the chamber 2 bias coils in amps
    general_setter_names = ["chamber_2_bias_x", "chamber_2_bias_y", "chamber_2_bias_z"]
    _opt = {"min": -5, "max": 5, "unit": "A"}
    general_setter_param_options = [_opt] * 3

    # Default settings for the ramp
    duration_default = constants.LATTICE_TRANSFER_TIME
    add_final_point = True

    general_setter_default_starts = [
        constants.B_FIELD_BIAS_NULL_X,
        constants.B_FIELD_BIAS_NULL_Y,
        constants.B_FIELD_BIAS_NULL_Z,
    ]

    general_setter_default_ends = [
        constants.B_FIELD_BIAS_LATTICE_X,
        constants.B_FIELD_BIAS_LATTICE_Y,
        constants.B_FIELD_BIAS_LATTICE_Z,
    ]

    def build_fragment(self, chamber_2_field_setter: SetMagneticFieldsQuick = None):
        if chamber_2_field_setter is None:
            raise TypeError("You must pass chamber_2_field_setter into build_fragment")
        self.field_setter = chamber_2_field_setter

        return super().build_fragment()

    @kernel
    def general_setter(self, vals: TList(TFloat)):
        self.field_setter.set_bias_fields(vals[0], vals[2], vals[2])


class DroppedLatticeWithTransportMixin(DroppedPumpedLatticeMixin):
    """
    Loads atoms into a lattice as per :class:`~DroppedPumpedLatticeMixin`, but
    loads the red MOT stages at the field null then transports the atoms to the
    lattice location afterwards by ramping the fields after the final red mot
    stage

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        # Add a ramping phase for the transfer between the red MOT and lattice.
        # Note that this must be before the NarrowbandRedMOT Fragment is added
        # so that its handle is already recorded by the time device_setup of the
        # NarrowbandRedMOT fires.
        self.setattr_fragment(
            "bias_field_ramper",
            _BiasFieldRamper,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.bias_field_ramper: _BiasFieldRamper

        super().build_fragment()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_lattice()

    @kernel
    def before_start_hook_lattice(self):
        self.bias_field_ramper.precalculate_dma_handle()

    @kernel
    def load_into_lattice(self):
        """
        Load into the lattice by shifting the atoms in the final red MOT stage
        into the lattice location then swapping to the lattice
        """
        self.transfer_mot_to_lattice_location()
        self.MOT_off_lattice_on()

    @kernel
    def transfer_mot_to_lattice_location(self):
        self.bias_field_ramper.do_phase()
