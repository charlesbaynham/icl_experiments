"""
Dynamic-ROI camera positioning validated from the dipole trap.

These three experiments commission the dynamic-ROI imaging stack
(:class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.DynamicROIImagingMixin`)
against atoms released from the dipole trap, using the same dipole-trap base
stack as the production Mach-Zehnder reference
(``repository/LMT/lmt_declarative.py``). They are the dipole-trap analogue of
``repository/LMT/red_mot_dynamic_roi.py`` (the red-MOT validation experiments),
built on the full dipole-trap loading/molasses/evaporation mixin stack rather
than the red-MOT DMA base.

The three experiments, in increasing complexity:

1. :class:`DeclarativeLMTDropValidationFrag` - pure free fall, no clock pulses.
   Validates the plumbing: the declared sequence carries only a SetPoint (needed
   to satisfy the DeclarativeLMTCoreBase non-empty sequence requirement) but no
   actual pulse events, so the trajectory predictor free-falls the ROIs. Scanning
   ``image_tof`` should track the falling cloud.
2. :class:`DeclarativeLMTLaunch2ValidationFrag` - velocity slice, then a 2-recoil
   launch ladder. Validates that the dynamic ROIs track a launched (moving) cloud.
3. :class:`DeclarativeLMTLaunch4ValidationFrag` - same as Launch2 but a 4-recoil
   ladder. The headline test of ROI tracking over a larger range of momenta.

MRO (all three)
---------------
The MRO mirrors :class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`,
with :class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.DynamicROIImagingMixin`
swapped in for
:class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.NormalisedFastKineticsLMTCorrectedMixin`.
This mirrors exactly the pattern used in ``red_mot_dynamic_roi.py``
(plain ``DynamicROIImagingMixin``, no extra clock-pulse readout between shots):

    DeclarativeLMTBase,
    DynamicROIImagingMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,

Imaging mixin choice
--------------------
All three use the plain ``DynamicROIImagingMixin`` rather than the
``NormalisedFastKineticsLMTCorrectedMixin`` variant used in the production
dipole reference. Rationale: ``NormalisedFastKineticsLMTCorrectedMixin`` fires
an extra clock down-beam pi pulse between fast-kinetics shots to de-shelve the
|e> population; these validation experiments have no population in |e> at imaging
time (the drop and low-N launch sequences are far below the full interferometer),
so the de-shelving pulse is superfluous. Keeping the plain mixin (a) avoids an
imaging-time clock drive on top of the declared sequence, (b) keeps the
experiments minimal - their purpose is ROI *tracking*, not a calibrated
excited-fraction readout. Both mixins win the same imaging hooks in the MRO, so
swapping to the corrected variant later is mechanical. The plain mixin still
produces a ground-port image (shot 1) and an excited-port image (shot 2) at the
two predicted positions.

EM gain
-------
EM gain is left as ``EMGainMixin``'s parameter, defaulting OFF. It is a safety
feature and is deliberately NOT hard-coded on here: enable it per run by passing
``em_gain_enabled=True`` in the submit arguments, after clearing the
``DISABLE_EM_GAIN`` interlock dataset by hand on the dashboard. Neither the
experiment code nor this module touches the interlock.

HOOK-COLLISION AUDIT (applies to all three classes)
----------------------------------------------------
Consumed hooks and their owning parent in the dipole base stack:

* ``post_dipole_trap_hook``              -> DeclarativeLMTBase (records
                                           t_dipole_beams_off; t=0 for the
                                           gravity Doppler and the ROI predictor)
* ``do_experiment_after_dipole_trap_hook`` -> DeclarativeLMTBase (prepares clock
                                             delivery AOM, then calls
                                             run_lmt_sequence)
* ``before_start_hook``                  -> DynamicROIImagingMixin (predicts the
                                           cloud positions + programs the ROIs
                                           off the time-critical timeline; chains
                                           before_start_hook_default)
* ``do_imaging_hook_andor``              -> DynamicROIImagingMixin
* ``get_andor_camera_config_hook``       -> DynamicROIImagingMixin
* ``DMA_initialization_hook``            -> Overridden explicitly here (see below);
                                           chains redmot_default, dipole_trap_default,
                                           loading_xodt_mot, xodt_molasses and
                                           evap_with_field_ramp, exactly as the
                                           production reference does.
* ``post_sequence_cleanup_hook``         -> Overridden explicitly here; chains
                                           _base, _andor and _declarative_lmt
                                           sub-hooks.

``EMGainMixin`` consumes no kernel hooks and never collides.

``DMA_initialization_hook`` collision: unlike the red-MOT base (which chains
only a single DMA init via ``DMAActionsAfterDropMixin``), the dipole base stack
has four loading/molasses/evap mixins that each contribute a sub-hook. None is
chain-called automatically; the hook must be overridden here and each sub-hook
called in order (as in the production reference). The five calls are:
  1. DMA_initialization_hook_redmot_default
  2. DMA_initialization_hook_dipole_trap_default
  3. DMA_initialization_hook_loading_xodt_mot
  4. DMA_initialization_hook_xodt_molasses
  5. DMA_initialization_hook_evap_with_field_ramp

``post_sequence_cleanup_hook``: contributed by three parents
(DipoleTrapWithExperimentBase: ``_base``; AndorImagingBase: ``_andor``;
DeclarativeLMTCoreBase: ``_declarative_lmt``). Overridden here and chained
explicitly, identical to the production reference.
"""

import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
    DynamicROIImagingMixin,
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
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


# %% Experiment 1: pure drop


class DeclarativeLMTDropValidationFrag(
    DeclarativeLMTBase,
    DynamicROIImagingMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Pure free-fall drop from the dipole trap with dynamic-ROI imaging.

    No clock pulses: only a full-intensity ``SetPoint`` event is declared (to
    satisfy the non-empty sequence requirement in
    :class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTCoreBase`),
    with no following pulse events. The trajectory predictor therefore handles
    an effectively empty intent stream as pure free fall, and the two ROIs track
    the ballistically falling cloud. Scanning ``image_tof`` (the time of flight
    from the dipole-trap drop to the first fast-kinetics image) should show the
    cloud following the predicted parabolic trajectory in the ROI-centred images.

    This is the lowest-complexity validation of the dynamic-ROI stack on the
    dipole trap: it checks the plumbing (DMA recording, ROI prediction, grabber
    programming) without exercising the pulse-sequence path.

    HOOK-COLLISION AUDIT
    --------------------
    See the module-level audit. Delta for this class: the declared sequence
    contains no pulse events, so ``run_lmt_sequence`` fires only the SetPoint
    event (which sets the delivery AOM - no OPLL ramp). The
    ``post_sequence_cleanup_hook`` (overridden below) chains all three sub-hooks
    (``_base``, ``_andor``, ``_declarative_lmt``) so the OPLL is safely
    restored regardless. The ``DMA_initialization_hook`` (overridden below)
    chains all five dipole-stack sub-hooks, as required.

    EM gain is left as the inherited parameter (default off); enable it per run
    via the ``em_gain_enabled`` submit argument.
    """

    # Atoms are released from the trap in the ground state with no kicks.
    lmt_initial_population = {("g", 0)}

    # Minimal sequence: only a SetPoint to satisfy the non-empty sequence
    # requirement. No pulse events follow, so the predictor sees an empty
    # intent stream and free-falls the ROIs.
    lmt_sequence = [
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
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


DeclarativeLMTDropValidation = make_fragment_scan_exp(DeclarativeLMTDropValidationFrag)


# %% Experiments 2 & 3: sliced LMT launch (N = 2, 4) via a factory


def _make_launch_frag(n: int):
    """
    Build a sliced-LMT-launch dynamic-ROI dipole-trap Frag for an ``n``-recoil
    launch.

    Returns a fresh class named ``DeclarativeLMTLaunch{n}ValidationFrag``. The
    declared sequence slices a velocity class, returns to full intensity, blasts
    the unselected atoms, walks the selected class ``n`` rungs up the momentum
    ladder, then clears any ground-state population left behind by imperfect
    pulses. The dynamic ROIs must track the launched (moving) cloud.

    Args:
        n: Number of ladder rungs (recoils) in the launch.

    Returns:
        A fresh ``ExpFragment`` class for an n-recoil dipole-trap launch with
        dynamic-ROI imaging.

    Composition and hook audit are identical to
    :class:`DeclarativeLMTDropValidationFrag`; see that class and the
    module-level audit.
    """

    class _LaunchFrag(
        DeclarativeLMTBase,
        DynamicROIImagingMixin,
        EMGainMixin,
        LoadSingleXODTMixin,
        XODTSingleMolassesPlusDipoleRampMixin,
        OpticalPumpingWithFieldSettingDipoleTrapMixin,
        FieldOnlyRampInEvapMixin,
        DipoleTrapWithExperimentBase,
    ):
        __doc__ = (
            f"Sliced LMT launch of {n} recoils from the dipole trap with "
            "dynamic-ROI imaging.\n\n"
            "Velocity slice selects a velocity class; a full-intensity clearout "
            "removes the unselected ground atoms; an n-recoil launch ladder "
            "declared in the LMT sequence language walks the selected class up "
            "the momentum ladder; a final clearout removes residual ground "
            "population. The dynamic ROIs track the launched cloud, validating "
            "ROI tracking over a non-zero momentum kick from the dipole trap. "
            "EM gain is left as the inherited parameter (default off; enable per "
            "run). Composition, imaging-mixin choice and HOOK-COLLISION AUDIT as "
            "for DeclarativeLMTDropValidationFrag (full dipole-trap stack); see "
            "that class and the module-level audit."
        )

        lmt_initial_population = {("g", 0)}

        lmt_sequence = [
            # Velocity slice: long pulse at reduced delivery set point.
            SetPoint(
                setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
                rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
                label="slice",
            ),
            pi(Beam.UP, m=0, label="slice"),
            # Back to full intensity for the launch.
            SetPoint(
                setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
                rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
                rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
            ),
            # Blast unselected ground-state atoms.
            Clearout(),
            # Launch ladder: n recoils, starting from m=1 (the sliced class).
            *ladder(start_m=1, n=n, first_beam=Beam.DOWN),
            # Remove ground-state population left behind by imperfect pulses.
            Clearout(),
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

    _LaunchFrag.__name__ = f"DeclarativeLMTLaunch{n}ValidationFrag"
    _LaunchFrag.__qualname__ = f"DeclarativeLMTLaunch{n}ValidationFrag"
    return _LaunchFrag


def _make_prep_frag(with_clearout: bool):
    """
    Build a slice-prep diagnostic Frag: velocity slice with NO launch ladder.

    Used to bisect launch atom-loss (the M0 launch legs imaged no in-band cloud).
    ``with_clearout=False`` images the sliced class plus the unselected ground
    atoms - a bright reference confirming the slice machinery preserves atoms;
    ``with_clearout=True`` images only the sliced velocity class that survives the
    clearout, confirming the slice selects a real sub-population. If both show
    atoms but a launch does not, the loss is in the ladder; if the clearout
    variant is null, the slice/clearout is the culprit. Composition,
    imaging-mixin choice and HOOK-COLLISION AUDIT identical to
    :class:`DeclarativeLMTDropValidationFrag`; see that class and the
    module-level audit.

    Args:
        with_clearout: Whether to blast the unselected ground atoms after the
            slice (leaving only the velocity-selected class).

    Returns:
        A fresh ``ExpFragment`` class for the slice-prep diagnostic.
    """

    class _PrepFrag(
        DeclarativeLMTBase,
        DynamicROIImagingMixin,
        EMGainMixin,
        LoadSingleXODTMixin,
        XODTSingleMolassesPlusDipoleRampMixin,
        OpticalPumpingWithFieldSettingDipoleTrapMixin,
        FieldOnlyRampInEvapMixin,
        DipoleTrapWithExperimentBase,
    ):
        __doc__ = (
            "Slice-prep diagnostic"
            + (" with clearout" if with_clearout else "")
            + " (no launch ladder) for bisecting launch atom-loss. Composition, "
            "imaging-mixin choice and HOOK-COLLISION AUDIT as for "
            "DeclarativeLMTDropValidationFrag; see that class and the "
            "module-level audit."
        )

        lmt_initial_population = {("g", 0)}

        lmt_sequence = [
            # Velocity slice: long pulse at reduced delivery set point.
            SetPoint(
                setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
                rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
                label="slice",
            ),
            pi(Beam.UP, m=0, label="slice"),
            # Back to full intensity (no launch follows).
            SetPoint(
                setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
                rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
                rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
            ),
        ] + ([Clearout()] if with_clearout else [])

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

    name = (
        "DeclarativeLMTSliceClearoutValidationFrag"
        if with_clearout
        else "DeclarativeLMTSliceOnlyValidationFrag"
    )
    _PrepFrag.__name__ = name
    _PrepFrag.__qualname__ = name
    return _PrepFrag


# Generate every Frag as a distinct module-level name, and wrap each with
# make_fragment_scan_exp (test_compile_all discovers classes by name, so both
# the Frag and its scan-exp must be importable module globals). Slice-prep
# diagnostics (no ladder) bisect launch atom-loss; launches n = 1..4 build the
# ladder up one rung at a time.
DeclarativeLMTSliceOnlyValidationFrag = _make_prep_frag(with_clearout=False)
DeclarativeLMTSliceClearoutValidationFrag = _make_prep_frag(with_clearout=True)
DeclarativeLMTLaunch1ValidationFrag = _make_launch_frag(1)
DeclarativeLMTLaunch2ValidationFrag = _make_launch_frag(2)
DeclarativeLMTLaunch3ValidationFrag = _make_launch_frag(3)
DeclarativeLMTLaunch4ValidationFrag = _make_launch_frag(4)

DeclarativeLMTSliceOnlyValidation = make_fragment_scan_exp(
    DeclarativeLMTSliceOnlyValidationFrag
)
DeclarativeLMTSliceClearoutValidation = make_fragment_scan_exp(
    DeclarativeLMTSliceClearoutValidationFrag
)
DeclarativeLMTLaunch1Validation = make_fragment_scan_exp(
    DeclarativeLMTLaunch1ValidationFrag
)
DeclarativeLMTLaunch2Validation = make_fragment_scan_exp(
    DeclarativeLMTLaunch2ValidationFrag
)
DeclarativeLMTLaunch3Validation = make_fragment_scan_exp(
    DeclarativeLMTLaunch3ValidationFrag
)
DeclarativeLMTLaunch4Validation = make_fragment_scan_exp(
    DeclarativeLMTLaunch4ValidationFrag
)
