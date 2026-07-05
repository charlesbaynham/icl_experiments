"""Compile-time readout selection for declarative-LMT imaging.

The readout method (clock-pulse shelving vs 679/707 repump) is chosen purely by
which dynamic-ROI aggregator a sequence names in its bases: no runtime argument
picks the physics path. These host-level tests pin that resolution so the two
aggregators cannot silently converge, and so a calibration cannot regress back
to clock-pulse readout (which would be circular - it needs clock parameters the
calibration is itself measuring).
"""

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    DynamicROIImagingMixin,
    NormalisedFastKineticsLMTCorrectedMixin,
    NormalisedFastKineticsLMTCorrectedRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
    NormalisedFastKineticsRepumpedMixin,
)


def test_repumped_aggregator_reads_out_via_repump():
    assert (
        NormalisedFastKineticsLMTCorrectedRepumpedMixin.do_first_pulse
        is NormalisedFastKineticsRepumpedMixin.do_first_pulse
    )


def test_clock_aggregator_reads_out_via_clock_pulse():
    assert (
        NormalisedFastKineticsLMTCorrectedMixin.do_first_pulse
        is NormalisedFastKineticsClockPulseMixin.do_first_pulse
    )


def test_both_aggregators_keep_dynamic_roi_hooks():
    for aggregator in (
        NormalisedFastKineticsLMTCorrectedMixin,
        NormalisedFastKineticsLMTCorrectedRepumpedMixin,
    ):
        for hook in (
            "do_imaging_hook_andor",
            "get_andor_camera_config_hook",
            "before_start_hook",
        ):
            assert (
                getattr(aggregator, hook) is getattr(DynamicROIImagingMixin, hook)
            ), f"{aggregator.__name__}.{hook} should come from DynamicROIImagingMixin"


def test_calibration_sequences_use_repumped_readout():
    from repository.LMT.lmt_tune_slice import (
        NarrowDownAfterSliceFrag,
        NarrowUpAfterSliceFrag,
    )

    for frag in (NarrowDownAfterSliceFrag, NarrowUpAfterSliceFrag):
        assert (
            frag.do_first_pulse is NormalisedFastKineticsRepumpedMixin.do_first_pulse
        ), f"{frag.__name__} (a calibration) must read out via repump, not a clock pulse"


def test_interferometer_sequences_keep_clock_readout():
    from repository.LMT.lmt_declarative import DeclarativeLMTSymmetricMachZehnderFrag

    assert (
        DeclarativeLMTSymmetricMachZehnderFrag.do_first_pulse
        is NormalisedFastKineticsClockPulseMixin.do_first_pulse
    )
