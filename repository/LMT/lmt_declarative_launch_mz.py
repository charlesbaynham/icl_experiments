"""
Deliverable 3: launch + Mach-Zehnder interferometer, declarative.

Velocity slice -> launch the cloud up the momentum ladder -> a pi/2 - pi - pi/2
Mach-Zehnder on the top momentum class -> fast-kinetics excited-state readout.
The whole thing is declared as a single :mod:`repository.lib.lmt_sequence`
list, from which the engine
(:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)
spawns one scannable detuning-offset and duration parameter per pulse.

This is a focused copy of the reference
:class:`repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag` for the
declarative-LMT D3 commissioning run. The sequence is identical to the
reference (same MRO, same launch ladder and MZ); the only additions here are
this module's documentation of how to drive it and which knob produces fringes.

Seeing fringes
--------------

The interferometer closes on the output pair ``|e, M_TOP> <-> |g, M_TOP + 1>``
(``final_population == {("e", 13), ("g", 14)}`` for ``N_LAUNCH = 12``). The
excitation fraction read out by the imaging mixin oscillates with the relative
phase of the recombiner. The cleanest commissioning fringe knob is the
detuning offset of the final pi/2 (the recombiner, ``bs2``): the engine spawns
it as the ndscan parameter ``p21_pi2_d_m13_bs2_offset`` (kHz, default 0).
Scanning it rotates the recombiner phase and the excitation fraction traces out
a sinusoid - the Mach-Zehnder fringe. The free dark time ``T``
(``p18_wait_dark1_duration`` / ``p20_wait_dark2_duration``, kept equal so the
interferometer stays symmetric about the mirror) is an alternative phase axis.

Notes / gotchas (carried from the framework)
--------------------------------------------

- SetPoint events cost time, so they are kept OUTSIDE the interferometer; the
  interferometer is symmetric about the mirror pulse (equal 1 ms darks) so it
  closes.
- The launch ladder and the whole MZ run on the down beam (the weaker beam,
  ~70 % per-pulse fidelity), which limits how many atoms survive - expect
  moderate contrast.
- Released from the dipole trap (``DeclarativeLMTBase``): t=0 for the gravity
  Doppler and the ballistic ROI predictor is the trap drop. The dipole release
  path is the one the launch should be commissioned on (the red-MOT path is
  where the prior launch underflowed).
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
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
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Number of launch pulses; the velocity-selective pulse provides the first
# kick (|g, 0> -> |e, 1>), so the launch ladder runs from m = 1 and ends at
# m = 1 + N_LAUNCH, which is the momentum class the Mach-Zehnder operates on.
N_LAUNCH = 12
M_TOP = 1 + N_LAUNCH

# Mach-Zehnder free dark time (each of the two darks, kept equal so the
# interferometer is symmetric about the mirror pulse and closes).
MZ_DARK_TIME = 1e-3


class DeclarativeLMTLaunchMachZehnderFrag(
    DeclarativeLMTBase,
    # Repositions the camera ROIs along the ballistic trajectory predicted from
    # the recorded pulse sequence (t=0 at the dipole-trap drop) and de-shelves
    # the excited port for the excitation-fraction readout. Do not also mix in
    # a static-config imaging mixin - it would win get_andor_camera_config_hook
    # and drop the trajectory-corrected ROIs.
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Velocity slice, launch and a Mach-Zehnder interferometer, all declared.
    """

    # Atoms are released from the trap in the ground state with no kicks.
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Velocity selection: a normal up-beam pulse, just longer and at a
        # lower delivery set point. Its SetPoint writes the reduced set point
        # and waits clock_delivery_preempt_time for the servo to recapture.
        # The set point -> Rabi relation is uncalibrated: scan p00_setpoint_slice
        # on atoms to hit the intended ~2 kHz slice width before trusting it.
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        # Full intensity for the launch and interferometer. The declared Rabi
        # frequencies set the default pulse durations (pi time = 1 / (2 Rabi)).
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Blast away the unselected ground-state atoms.
        Clearout(),
        # Launch: alternating-beam pi-pulse ladder walking the selected class
        # up the momentum ladder from |e, 1> to m = M_TOP.
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN),
        # Remove ground-state population left behind by imperfect launch pulses.
        Clearout(),
        # Mach-Zehnder on the pair |e, M_TOP> <-> |g, M_TOP + 1>. Kept
        # symmetric about the mirror (equal darks, no SetPoint inside) so it
        # closes. Scan p21_pi2_d_m13_bs2_offset (the bs2 detuning offset) to
        # see fringes.
        pi2(Beam.DOWN, m=M_TOP, label="bs1"),
        Wait(t=MZ_DARK_TIME, label="dark1"),
        pi(Beam.DOWN, m=M_TOP, label="mirror"),
        Wait(t=MZ_DARK_TIME, label="dark2"),
        pi2(Beam.DOWN, m=M_TOP, label="bs2"),
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


DeclarativeLMTLaunchMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTLaunchMachZehnderFrag
)
