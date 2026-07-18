"""Pin the compile-time repump-vs-clock LMT readout selection.

Repumped vs clock-pulse readout is chosen by which aggregator an experiment
Frag names in its bases. These tests guard that:
 - the default aggregator keeps the 679/707 repump ``do_first_pulse``,
 - the clock aggregator uses the full-power broad clock selection pulse,
 - the two Global symmetric MZ experiments pick up the intended one, with no
   accidental diamond (each Frag pulls in exactly one readout mixin).
"""

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    NormalisedFastKineticsLMTCorrectedClockMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    NormalisedFastKineticsLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    SingleImageDynamicROIImagingMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    SingleImageLMTClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    SingleImageLMTCorrectedClockMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    SingleImageLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    RepumpingWith679Mixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedBase,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderFrag,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderSingleImageClockReadoutFrag,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderSingleImageFrag,
)


def _first_pulse_owner(cls):
    for base in cls.__mro__:
        if "do_first_pulse" in base.__dict__:
            return base
    raise AssertionError(f"{cls.__name__} has no do_first_pulse in its MRO")


def test_repump_aggregator_uses_repump_first_pulse():
    assert (
        _first_pulse_owner(NormalisedFastKineticsLMTCorrectedMixin)
        is NormalisedFastKineticsRepumpedMixin
    )


def test_clock_aggregator_uses_clock_first_pulse():
    assert (
        _first_pulse_owner(NormalisedFastKineticsLMTCorrectedClockMixin)
        is NormalisedFastKineticsClockPulseMixin
    )


def test_global_mz_default_is_repump():
    owner = _first_pulse_owner(DeclarativeLMTGlobalSymmetricMachZehnderFrag)
    assert owner is NormalisedFastKineticsRepumpedMixin
    assert (
        NormalisedFastKineticsClockPulseMixin
        not in DeclarativeLMTGlobalSymmetricMachZehnderFrag.__mro__
    )


def test_global_mz_clock_variant_is_clock():
    owner = _first_pulse_owner(DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag)
    assert owner is NormalisedFastKineticsClockPulseMixin
    assert (
        NormalisedFastKineticsRepumpedMixin
        not in DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag.__mro__
    )


def test_clock_first_pulse_drives_full_delivery_power():
    import inspect

    src = inspect.getsource(NormalisedFastKineticsClockPulseMixin.do_first_pulse)
    assert "set_clock_delivery_aom" in src
    assert "CLOCK_DELIVERY_SETPOINT_V" in src
    assert "DOWN_CLOCK_BEAM_PI_TIME" in src


# %% Single-image (spatial background) readout


def test_single_image_repump_aggregator_uses_repump_first_pulse():
    assert (
        _first_pulse_owner(SingleImageLMTCorrectedMixin) is RepumpingWith679Mixin
    )


def test_single_image_clock_aggregator_uses_clock_first_pulse():
    assert (
        _first_pulse_owner(SingleImageLMTCorrectedClockMixin)
        is SingleImageLMTClockPulseMixin
    )


def test_single_image_readout_never_pulls_in_the_two_series_flow():
    """The whole point of the merge is one fast-kinetics series.

    Inheriting NormalisedFastKineticsBase would bring back the second
    acquisition, its clear-out delay and the images[2]/[3] processing that
    spatial background exists to remove -- and would do so silently, since the
    hooks would still resolve.
    """
    for aggregator in (SingleImageLMTCorrectedMixin, SingleImageLMTCorrectedClockMixin):
        assert NormalisedFastKineticsBase not in aggregator.__mro__
        assert SingleImageNormalisedBase in aggregator.__mro__


def test_single_image_clock_pulse_compensates_the_free_fall_doppler():
    """The LMT readout fires after the atoms have been falling for the sequence.

    Losing the OPLL fall compensation is silent: the pulse still fires, just off
    resonance by t_fall * GRAVITY_DOPPLER_PER_SEC_CLOCK (~14 kHz/ms, so ~70 kHz
    after 5 ms). Pin that it is both present and actually invoked.
    """
    import inspect

    src = inspect.getsource(SingleImageLMTClockPulseMixin.do_first_pulse)
    assert "set_clock_delivery_aom" in src
    assert "CLOCK_DELIVERY_SETPOINT_V" in src
    assert "DOWN_CLOCK_BEAM_PI_TIME" in src
    assert "_set_readout_opll_for_fall" in src

    fall_src = inspect.getsource(SingleImageLMTClockPulseMixin._set_readout_opll_for_fall)
    assert "GRAVITY_DOPPLER_PER_SEC_CLOCK" in fall_src
    assert "get_t_release_mu" in fall_src

    # ...and that the aggregator actually resolves to this implementation rather
    # than the single-image family's uncompensated pi pulse.
    assert (
        SingleImageLMTCorrectedClockMixin.do_first_pulse
        is SingleImageLMTClockPulseMixin.do_first_pulse
    )


def test_single_image_global_mz_frags_pick_the_intended_readout():
    repump_owner = _first_pulse_owner(
        DeclarativeLMTGlobalSymmetricMachZehnderSingleImageFrag
    )
    assert repump_owner is RepumpingWith679Mixin

    clock_owner = _first_pulse_owner(
        DeclarativeLMTGlobalSymmetricMachZehnderSingleImageClockReadoutFrag
    )
    assert clock_owner is SingleImageLMTClockPulseMixin

    # No accidental diamond with the two-series readout.
    for frag in (
        DeclarativeLMTGlobalSymmetricMachZehnderSingleImageFrag,
        DeclarativeLMTGlobalSymmetricMachZehnderSingleImageClockReadoutFrag,
    ):
        assert NormalisedFastKineticsBase not in frag.__mro__


def test_original_two_series_frags_are_untouched_by_the_new_readout():
    """The validated readout must stay reachable and unchanged for rollback."""
    for frag in (
        DeclarativeLMTGlobalSymmetricMachZehnderFrag,
        DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag,
    ):
        assert SingleImageDynamicROIImagingMixin not in frag.__mro__
        assert NormalisedFastKineticsBase in frag.__mro__
