"""
Dynamic-ROI camera positioning validated from the RED MOT (dipole trap offline).

These three experiments commission the dynamic-ROI imaging stack
(:class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.DynamicROIImagingMixin`)
against atoms released directly from the red MOT, for the period when the
1064 nm dipole trap is unavailable. They are the red-MOT analogue of
``repository/LMT/lmt_declarative.py`` (the dipole reference), built on the
red-MOT DMA base
(:class:`~repository.lib.experiment_templates.red_mot_dma_experiment.RedMOTWithDMAExperimentBase`)
instead of the dipole-trap base.

The three experiments, in increasing complexity:

1. :class:`RedMOTDropDynamicROIFrag` - pure free fall, no clock pulses. Validates
   the plumbing: the DMA recording is non-empty (the base records a 1 us marker)
   but the intent stream is empty, so the trajectory predictor free-falls the
   ROIs. Scanning ``delay_after_experiment`` should track the falling cloud.
2. :class:`RedMOTSlicedSpecDynamicROIFrag` - velocity-sliced clock spectroscopy
   declared in the LMT sequence language.
3. :class:`RedMOTLaunchDynamicROI_N{2,4,8}Frag` - sliced LMT launch of N recoils;
   the headline test that ROIs track a launched (moving) cloud.

EM gain
-------
EM gain is left as ``EMGainMixin``'s parameter, defaulting OFF. It is a safety
feature and is deliberately NOT hard-coded on here: enable it per run by passing
``em_gain_enabled=True`` (level 30 is fine) in the submit arguments, and clear
the ``DISABLE_EM_GAIN`` interlock dataset by hand on the dashboard. Neither the
experiment code nor this module touches the interlock.

Imaging mixin choice
--------------------
All three use the *plain* ``DynamicROIImagingMixin`` (dynamic ROIs, no extra
clock-pulse readout), not the ``NormalisedFastKineticsLMTCorrectedMixin``
variant the dipole reference uses. Rationale: in the dipole reference the
``NormalisedFastKineticsClockPulseMixin`` half fires a clock down-beam pi pulse
between the two fast-kinetics shots to de-shelve the |e> population so the
second (excited-port) image sees it. For these declarative experiments *all*
clock driving lives in the declared ``lmt_sequence`` (the slice, the resonant
spectroscopy pulse, the launch ladder); the ROI prediction that this stack
validates is driven entirely by the recorded intent stream and is independent
of the imaging readout. Keeping the plain mixin therefore (a) avoids a second,
imaging-time clock drive on top of the declared sequence, and (b) keeps the
validation experiments minimal - their goal is ROI *tracking*, not a calibrated
excited-fraction readout. The de-shelving clock readout can be layered back in
(swap to ``NormalisedFastKineticsLMTCorrectedMixin``) once the geometry is
commissioned and a true excited-port image is wanted. Both
``DynamicROIImagingMixin`` and ``NormalisedFastKineticsClockPulseMixin`` win the
same imaging hooks in the MRO, so the swap is mechanical; the plain mixin still
produces a ground image (shot 1) and an excited-port image (shot 2) at the two
predicted positions - shot 2 simply images whatever |g>-resonant population is
at the excited port rather than a freshly de-shelved one.

HOOK-COLLISION AUDIT (applies to all three)
-------------------------------------------
Consumed hooks and their owning parent:

* ``DMA_record_hook``                    -> RedMOTWithDMAExperimentBase (base)
* ``DMA_initialization_hook``            -> RedMOTWithDMAExperimentBase (base)
* ``do_experiment_after_red_mot_hook``   -> RedMOTWithDMAExperimentBase (base)
* ``pre_expansion_hook``                 -> RedMOTWithDMAExperimentBase (base)
* ``do_experiment_after_drop_hook``      -> DeclarativeLMTRedMOTBase (exp 2/3 only;
                                            default no-op for exp 1)
* ``do_imaging_hook_andor``              -> DynamicROIImagingMixin
* ``get_andor_camera_config_hook``       -> DynamicROIImagingMixin
* ``post_sequence_cleanup_hook``         -> contributed by *several* parents
  (RedMOTWithExperimentBase: ``_base``; AndorImagingBase: ``_base`` + ``_andor``;
  DeclarativeLMTCoreBase: ``_declarative_lmt``) - so we override and chain the
  ``_base`` / ``_andor`` / ``_declarative_lmt`` sub-hooks explicitly.

``EMGainMixin`` consumes *no* kernel hooks, so it never collides.

``DMA_initialization_hook`` collision: the base's default
``RedMOTWithDMAExperimentBase.DMA_initialization_hook`` already chains the
red-MOT default plus the DMA recording fragment's after-drop handle fetch, and
no other parent in these stacks overrides it. So unlike the dipole reference
(which had loading/molasses/evap mixins each contributing a DMA-init sub-hook),
nothing here needs an explicit override - the base default is sufficient and is
left untouched.
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
    DynamicROIImagingMixin,
)
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTRedMOTBase,
)
from repository.lib.experiment_templates.red_mot_dma_experiment import (
    RedMOTWithDMAExperimentBase,
)
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


# %% Experiment 1: pure drop


class RedMOTDropDynamicROIFrag(
    # Imaging mixin first, then EMGain, then the experiment base last - mirroring
    # the ordering of the dipole reference (DeclarativeLMTMachZehnderFrag).
    DynamicROIImagingMixin,
    EMGainMixin,
    RedMOTWithDMAExperimentBase,
):
    """
    Pure free-fall drop from the red MOT with dynamic-ROI imaging.

    No declarative engine and no clock pulses: every post-drop hook is left at
    its ``RedMOTWithDMAExperimentBase`` default, so ``actions_after_drop``
    records only the unconditional 1 us marker (the DMA recording is therefore
    non-empty, which ``core_dma`` requires) and the intent stream stays empty.
    The trajectory predictor handles an empty intent stream as pure free fall,
    so the two ROIs simply track the ballistically falling cloud. The drop time
    is the inherited ``delay_after_experiment`` parameter, which the validation
    scans.

    HOOK-COLLISION AUDIT
    --------------------
    Consumed hooks: ``DMA_record_hook`` / ``DMA_initialization_hook`` /
    ``do_experiment_after_red_mot_hook`` / ``pre_expansion_hook`` (all owned by
    ``RedMOTWithDMAExperimentBase``); ``do_imaging_hook_andor`` /
    ``get_andor_camera_config_hook`` (owned by ``DynamicROIImagingMixin``).
    ``EMGainMixin`` owns no hooks. The only multiply-claimed hook is
    ``post_sequence_cleanup_hook``, overridden below to chain the red-MOT/Andor
    base cleanups (there is no declarative engine here, so no ``_declarative_lmt``
    sub-hook). ``DMA_initialization_hook`` is left at the base default (the
    red-MOT default plus the DMA fragment's after-drop handle fetch); no other
    parent contributes a DMA-init sub-hook.

    EM gain is left as the inherited parameter (default off); enable it per run
    via the ``em_gain_enabled`` submit argument.
    """

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()


RedMOTDropDynamicROI = make_fragment_scan_exp(RedMOTDropDynamicROIFrag)


# %% Experiment 2: velocity-sliced clock spectroscopy


class RedMOTSlicedSpecDynamicROIFrag(
    # Declarative red-MOT engine (which brings RedMOTWithDMAExperimentBase via
    # its own bases), then the dynamic-ROI imaging mixin, then EMGain. The
    # experiment base is reached through DeclarativeLMTRedMOTBase, so it is not
    # listed again - the dipole reference lists the base explicitly only because
    # its imaging/loading mixins do not otherwise pull it in.
    DeclarativeLMTRedMOTBase,
    DynamicROIImagingMixin,
    EMGainMixin,
):
    """
    Velocity-sliced clock spectroscopy from the red MOT, declared in the LMT
    sequence language and imaged with dynamic ROIs.

    The declared sequence: a long low-setpoint slice pulse selects a velocity
    class; the delivery set point is then returned to full intensity and the
    unselected ground atoms are blasted away (``Clearout``); finally a resonant
    spectroscopy pulse addresses the selected class (``m=1``). The
    spectroscopy pulse's auto-spawned detuning-offset ndscan parameter is what
    the validation scans.

    HOOK-COLLISION AUDIT
    --------------------
    Consumed hooks: ``DMA_record_hook`` / ``DMA_initialization_hook`` /
    ``do_experiment_after_red_mot_hook`` / ``pre_expansion_hook`` (owned by
    ``RedMOTWithDMAExperimentBase``); ``do_experiment_after_drop_hook`` (owned by
    ``DeclarativeLMTRedMOTBase`` - runs the declared sequence); and
    ``do_imaging_hook_andor`` / ``get_andor_camera_config_hook`` (owned by
    ``DynamicROIImagingMixin``). ``EMGainMixin`` owns no hooks.
    ``post_sequence_cleanup_hook`` is multiply-claimed (red-MOT base, Andor base,
    declarative engine) and is overridden below to chain all three sub-hooks.
    ``DMA_initialization_hook`` is left at the base default.
    """

    # Atoms are released from the red MOT in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Velocity slice: a normal pulse, just longer and at a lower delivery
        # set point. The SetPoint writes the slicing set point and waits for the
        # servo to recapture; the declared rabi_up sets the default pulse time.
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        # Back to full intensity for the resonant spectroscopy pulse
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Blast away the unselected ground-state atoms
        Clearout(),
        # Resonant spectroscopy pulse on the selected class; its detuning-offset
        # parameter (default 0) is the validation scan axis.
        pi(Beam.UP, m=1, label="spec"),
    ]

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_declarative_lmt()


RedMOTSlicedSpecDynamicROI = make_fragment_scan_exp(RedMOTSlicedSpecDynamicROIFrag)


# %% Experiment 3: sliced LMT launch (N = 2, 4, 8) via a factory


def _make_launch_frag(n):
    """
    Build a sliced-LMT-launch dynamic-ROI red-MOT Frag for an ``n``-recoil
    launch.

    Returns a fresh class named ``RedMOTLaunchDynamicROI_N{n}Frag``. The
    declared sequence slices a velocity class, returns to full intensity, blasts
    the unselected atoms, walks the selected class ``n`` rungs up the momentum
    ladder, then clears any ground-state population left behind by imperfect
    pulses. The dynamic ROIs must track the launched (moving) cloud - the
    headline validation of this stack.

    Composition and hook audit are identical to
    :class:`RedMOTSlicedSpecDynamicROIFrag`; see that class.
    """

    class _LaunchFrag(
        DeclarativeLMTRedMOTBase,
        DynamicROIImagingMixin,
        EMGainMixin,
    ):
        __doc__ = (
            f"Sliced LMT launch of {n} recoils from the red MOT with dynamic-ROI "
            "imaging.\n\n"
            "Velocity slice, then an n-recoil launch ladder declared in the LMT "
            "sequence language; the dynamic ROIs track the launched cloud. EM "
            "gain is left as the inherited parameter (default off; enable per "
            "run). Composition, imaging-mixin choice and HOOK-COLLISION AUDIT as "
            "for RedMOTSlicedSpecDynamicROIFrag: the base owns DMA_record_hook / "
            "DMA_initialization_hook / do_experiment_after_red_mot_hook / "
            "pre_expansion_hook; DeclarativeLMTRedMOTBase owns "
            "do_experiment_after_drop_hook; DynamicROIImagingMixin owns "
            "do_imaging_hook_andor / get_andor_camera_config_hook; EMGainMixin "
            "owns none; post_sequence_cleanup_hook is overridden to chain "
            "_base / _andor / _declarative_lmt."
        )

        lmt_initial_population = {("g", 0)}

        lmt_sequence = [
            SetPoint(
                setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
                rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
                label="slice",
            ),
            pi(Beam.UP, m=0, label="slice"),
            SetPoint(
                setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
                rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
                rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
            ),
            Clearout(),
            *ladder(start_m=1, n=n, first_beam=Beam.DOWN),
            Clearout(),
        ]

        @kernel
        def post_sequence_cleanup_hook(self):
            self.post_sequence_cleanup_hook_base()
            self.post_sequence_cleanup_hook_andor()
            self.post_sequence_cleanup_hook_declarative_lmt()

    _LaunchFrag.__name__ = f"RedMOTLaunchDynamicROI_N{n}Frag"
    _LaunchFrag.__qualname__ = f"RedMOTLaunchDynamicROI_N{n}Frag"
    return _LaunchFrag


# Generate the three launch Frags as distinct module-level names, and wrap each
# with make_fragment_scan_exp (test_compile_all discovers classes by name, so
# both the Frag and its scan-exp must be importable module globals).
RedMOTLaunchDynamicROI_N2Frag = _make_launch_frag(2)
RedMOTLaunchDynamicROI_N4Frag = _make_launch_frag(4)
RedMOTLaunchDynamicROI_N8Frag = _make_launch_frag(8)

RedMOTLaunchDynamicROI_N2 = make_fragment_scan_exp(RedMOTLaunchDynamicROI_N2Frag)
RedMOTLaunchDynamicROI_N4 = make_fragment_scan_exp(RedMOTLaunchDynamicROI_N4Frag)
RedMOTLaunchDynamicROI_N8 = make_fragment_scan_exp(RedMOTLaunchDynamicROI_N8Frag)
