"""
Velocity-sliced clock spectroscopy driven by the declarative LMT stack.

DELIVERABLE 2 of the declarative-LMT ladder: a velocity-selective (slice)
pulse selects a narrow velocity class, then a clock spectroscopy pulse whose
detuning is scanned maps out the resonance. With the slice the line is
narrowed to the slice width (target ~2 kHz for a square 380 us pulse); without
it the line is Doppler-broadened. Proving the slice narrows the linewidth, and
that the de-shelve readout reads it out cleanly, is the headline result; the
slice setpoint->Rabi calibration done here is reused by deliverables 3-6.

Two experiments are declared, sharing the dipole-trap declarative stack of the
reference Mach-Zehnder experiment
(:mod:`repository.LMT.lmt_declarative`) - only the sequence differs:

* :class:`DeclarativeVSliceSpecFrag` - the headline experiment: slice ->
  full-intensity SetPoint -> clearout (blast unselected ground atoms) ->
  resonant spectroscopy pulse on the selected class. Scanning the spectroscopy
  pulse's auto-spawned detuning offset maps the (slice-narrowed) line.
* :class:`DeclarativeNoSliceSpecFrag` - the no-slice control for the linewidth
  A/B: the same spectroscopy pulse fired on the *whole* (unsliced, Doppler-
  broadened) ground cloud, so its line is the broad reference against which the
  sliced line is compared.

Population bookkeeping
----------------------
The slice is an up-beam pi addressing the released ground class
``(g, 0)``, transferring it to ``(e, 1)``; the ``Clearout`` then blasts the
unselected ground atoms (the selected class is excited, so survives). The
spectroscopy pulse is an up-beam pi addressing ``(e, 1)``, which on resonance
returns the selected class to ``(g, 0)``. The readout (de-shelve clock pi
between the two fast-kinetics shots, from
:class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.NormalisedFastKineticsLMTCorrectedMixin`)
reports the excitation fraction, so a resonant spectroscopy pulse produces a
DIP in excitation fraction. The no-slice control instead drives the whole
ground cloud ``(g, 0) -> (e, 1)``, giving a PEAK.

Gravity Doppler is handled by the engine: every pulse (slice and spectroscopy
alike) fires at the model-predicted resonance with the OPLL chirped at the
gravity rate for the pulse duration, so the long slice pulse stays on
resonance with the falling atoms. See
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`.
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
    NormalisedFastKineticsLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTBase,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import pi

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


class DeclarativeVSliceSpecFrag(
    DeclarativeLMTBase,
    # Dynamic-ROI imaging + de-shelve clock-pulse readout, exactly as the
    # reference Mach-Zehnder experiment. NB: do not also mix in one of the
    # static-config imaging mixins - it would win get_andor_camera_config_hook
    # in the MRO and install a config without calculate_atom_positions.
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Velocity-sliced clock spectroscopy from a declared pulse sequence.

    Scanning the spectroscopy pulse's auto-spawned detuning offset
    (``p04_pi_u_m1_spec_offset``) maps out the velocity-slice-narrowed line.
    """

    # Atoms are released from the dipole trap in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Velocity selection: a normal pulse, just longer and with a lower
        # delivery set point. The SetPoint writes the slicing set point and
        # waits clock_delivery_preempt_time for the servo to recapture; the
        # declared rabi_up sets the default slice pulse time.
        #
        # TODO: experimentally scan this set point (the spawned
        # p00_setpoint_slice parameter) to find the value giving the intended
        # slicing Rabi frequency, then update the default and the declared
        # rabi_up. The delivery-setpoint -> Rabi relation is uncalibrated, so
        # it must be calibrated on atoms; deliverables 3-6 reuse the value
        # found here.
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        # Back to full intensity for the resonant spectroscopy pulse; the
        # declared Rabi frequencies set the default pulse durations
        # (pi time = 1 / (2 * Rabi)).
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Blast away the unselected ground-state atoms
        Clearout(),
        # Resonant spectroscopy pulse on the selected class |e, 1>; its
        # detuning-offset parameter (default 0, relative to the model-predicted
        # resonance) is the spectroscopy scan axis. On resonance it returns the
        # selected class to the ground state, producing a dip in the read-out
        # excitation fraction.
        pi(Beam.UP, m=1, label="spec"),
    ]

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_declarative_lmt()


DeclarativeVSliceSpec = make_fragment_scan_exp(DeclarativeVSliceSpecFrag)


class DeclarativeNoSliceSpecFrag(DeclarativeVSliceSpecFrag):
    """
    No-slice control for the velocity-slice linewidth A/B comparison.

    Identical stack and readout to :class:`DeclarativeVSliceSpecFrag`, but the
    spectroscopy pulse is fired at full intensity on the *whole* released
    ground cloud (no velocity selection and no clearout), so its line is the
    Doppler-broadened reference. Scanning the spectroscopy pulse's detuning
    offset (``p01_pi_u_m0_spec_offset``) maps the broad line; comparing its
    width with the sliced experiment's narrow line is the headline A/B result.
    On resonance the spectroscopy pulse excites the cloud, producing a peak in
    the read-out excitation fraction.
    """

    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Full intensity straight away - no velocity selection.
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Spectroscopy pulse on the whole released ground cloud |g, 0>; its
        # detuning-offset parameter (default 0) is the scan axis. The line is
        # Doppler-broadened (no velocity selection), the reference against
        # which the sliced line's width is compared.
        pi(Beam.UP, m=0, label="spec"),
    ]


DeclarativeNoSliceSpec = make_fragment_scan_exp(DeclarativeNoSliceSpecFrag)
