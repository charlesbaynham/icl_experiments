import logging

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsDoubleTrapBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFKConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFKDoubleTrapConfig,
)

logger = logging.getLogger(__name__)


class NormalisedRedMOTFastKineticsMixin(NormalisedFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    # Lengthen the readout timeout from the default 2s to support evaporation
    # TODO: Associate this with the Evap mixin somehow rather than hard-coding it here
    image_read_timeout = 15.0


class NormalisedDipoleTrapFKConfig(NormalisedFKConfig):
    """NormalisedFKConfig with dipole-trap-specific FK height/offset defaults."""

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP


class NormalisedDipoleTrapFastKineticsMixin(NormalisedFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedDipoleTrapFKConfig,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y1,
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )
        self.andor_camera_config: NormalisedDipoleTrapFKConfig
        return f


class NormalisedXXODTFKConfigBase(NormalisedFKDoubleTrapConfig):
    """Base config for XXODT (double-trap) fast-kinetics variants."""

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP


class NormalisedXXODTFKConfig(NormalisedXXODTFKConfigBase):
    """Config for non-spectroscopy XXODT fast-kinetics with gravity-corrected ROIs."""


class NormalisedXXODTSpectroscopyFKConfig(NormalisedXXODTFKConfigBase):
    """Config for spectroscopy XXODT fast-kinetics with gravity-corrected ROIs."""


class NormalisedXXODTFastKineticsBase(NormalisedFastKineticsDoubleTrapBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedXXODTFKConfigBase,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )
        self.andor_camera_config: NormalisedXXODTFKConfigBase
        return f

    def get_monitor_rois(self):
        rois = self.andor_camera_config.get_rois()
        fwd_roi = list(rois[0])
        bwd_roi = list(rois[2])
        return [fwd_roi, bwd_roi]


def _gravity_pixels_dropped_interferometry():
    """Compute pixels-dropped-between-pulses for the interferometry (XXODT) variant."""
    time_dropped_before_first_pulse = (
        constants.SHELVING_PULSE_CLEAROUT_DURATION
        + constants.CLOCK_SHELVING_PULSE_TIME
        + 2 * constants.CLOCK_PI_TIME
        + 2 * constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES
    )
    velocity_at_first_pulse = (
        constants.scipy_constants.g * time_dropped_before_first_pulse
    )
    distance_fallen_between_pulses = (
        velocity_at_first_pulse * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES
        + 0.5
        * constants.scipy_constants.g
        * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES**2
    )
    return round(
        distance_fallen_between_pulses / constants.ANDOR_CAMERA_FACTS["pixel_size"]
    )


def _gravity_pixels_dropped_spectroscopy():
    """Compute pixels-dropped-between-pulses for the spectroscopy (XXODT) variant."""
    time_dropped_before_first_pulse = (
        constants.SHELVING_PULSE_CLEAROUT_DURATION
        + constants.CLOCK_SHELVING_PULSE_TIME
        + constants.CLOCK_PI_TIME
        + constants.DELAY_AFTER_CLOCK_SPECTROSCOPY
    )
    velocity_at_first_pulse = (
        constants.scipy_constants.g * time_dropped_before_first_pulse
    )
    distance_fallen_between_pulses = (
        velocity_at_first_pulse * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES
        + 0.5
        * constants.scipy_constants.g
        * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES**2
    )
    return round(
        distance_fallen_between_pulses / constants.ANDOR_CAMERA_FACTS["pixel_size"]
    )


class NormalisedXXODTFastKineticsMixin(NormalisedXXODTFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        # Compensate for the drop under gravity in the excited cloud relative to
        # the ground cloud.
        #
        # TODO: This logic uses values from constants but these are defaults and
        # might be overridden by the user. If they do this, this calculation
        # will be wrong. It does this because this fragment is configured in
        # build_fragment where parameter values are not yet set. This ought to
        # be updated.
        pixels_dropped_between_pulses = _gravity_pixels_dropped_interferometry()

        logger.debug(
            "Compensating gravity drop with an offset of %s pixels",
            pixels_dropped_between_pulses,
        )

        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedXXODTFKConfig,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
            excited_shift=pixels_dropped_between_pulses,
        )
        self.andor_camera_config: NormalisedXXODTFKConfig
        return f

    def host_setup(self):
        super().host_setup()

        # Add checks to catch varied parameters which would cause the gravity
        # calculations in `_gravity_pixels_dropped_interferometry` (called from
        # `get_andor_camera_config_hook`) to fail. This is horrible code because
        # it a) relies on classes that this one does not inherit from and b) it
        # should just calculate this properly, not throw error when it's wrong.
        # I'm so sorry, time is just too short to do this properly right now.
        handles_and_default_vals = [
            (
                "shelving_pulse_clearout_duration",
                constants.SHELVING_PULSE_CLEAROUT_DURATION,
            ),
            ("shelving_pulse_time", constants.CLOCK_SHELVING_PULSE_TIME),
            ("spectroscopy_pulse_time", constants.CLOCK_PI_TIME),
            (
                "delay_between_interferometry_pulses",
                constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
            ),
        ]

        for handle_name, default_val in handles_and_default_vals:
            if not hasattr(self, handle_name):
                logger.warning(
                    "NormaliseXXODT readout is applying gravity corrections assuming that you're doing "
                    "slicing but you're not, so the gravity corrections will be wrong. "
                    "Specifically the %s parameter is not present.",
                    handle_name,
                )
            else:
                val = getattr(self, handle_name).get()

                diff = val - default_val
                if abs(diff) / default_val > 1e-6:
                    logger.warning(
                        "NormaliseXXODT readout is applying gravity corrections based on the "
                        "default parameter value of %s = %s, but you have set it to %s so the "
                        "excited state ROI will be in the wrong place.",
                        handle_name,
                        default_val,
                        val,
                    )


class NormalisedXXODTSpectroscopyFastKineticsMixin(NormalisedXXODTFastKineticsBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        # Compensate for the drop under gravity in the excited cloud relative to
        # the ground cloud.
        #
        # TODO: This logic uses values from constants but these are defaults and
        # might be overridden by the user. If they do this, this calculation
        # will be wrong. It does this because this fragment is configured in
        # build_fragment where parameter values are not yet set. This ought to
        # be updated.
        pixels_dropped_between_pulses = _gravity_pixels_dropped_spectroscopy()

        logger.debug(
            "Compensating gravity drop with an offset of %s pixels",
            pixels_dropped_between_pulses,
        )

        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedXXODTSpectroscopyFKConfig,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
            excited_shift=pixels_dropped_between_pulses,
        )
        self.andor_camera_config: NormalisedXXODTSpectroscopyFKConfig
        return f

    def host_setup(self):
        super().host_setup()

        # Add checks to catch varied parameters which would cause the gravity
        # calculations in `_gravity_pixels_dropped_spectroscopy` (called from
        # `get_andor_camera_config_hook`) to fail. This is horrible code because
        # it a) relies on classes that this one does not inherit from and b) it
        # should just calculate this properly, not throw error when it's wrong.
        # I'm so sorry, time is just too short to do this properly right now.
        handles_and_default_vals = [
            (
                "shelving_pulse_clearout_duration",
                constants.SHELVING_PULSE_CLEAROUT_DURATION,
            ),
            ("shelving_pulse_time", constants.CLOCK_SHELVING_PULSE_TIME),
            ("spectroscopy_pulse_time", constants.CLOCK_PI_TIME),
            ("delay_after_spectroscopy", constants.DELAY_AFTER_CLOCK_SPECTROSCOPY),
        ]

        for handle_name, default_val in handles_and_default_vals:
            if not hasattr(self, handle_name):
                logger.warning(
                    "NormaliseXXODT readout is applying gravity corrections assuming that you're doing "
                    "slicing but you're not, so the gravity corrections will be wrong. "
                    "Specifically the %s parameter is not present.",
                    handle_name,
                )
            else:
                val = getattr(self, handle_name).get()

                diff = val - default_val
                if abs(diff) / default_val > 1e-6:
                    logger.warning(
                        "NormaliseXXODT readout is applying gravity corrections based on the "
                        "default parameter value of %s = %s, but you have set it to %s so the "
                        "excited state ROI will be in the wrong place.",
                        handle_name,
                        default_val,
                        val,
                    )
