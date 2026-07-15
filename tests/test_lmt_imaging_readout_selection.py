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
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag,
)
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderFrag,
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
