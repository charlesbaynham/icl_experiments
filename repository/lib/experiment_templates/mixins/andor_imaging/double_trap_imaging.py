import logging

from artiq.experiment import kernel
from ndscan.experiment import FloatChannel

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

from .single_andor_image import SingleAndorImage
from .imaging_base import AndorImagingBase
from .bg_corrected_andor_image import BGCorrectedAndorImage
from .triple_imaging_fast_kinetics import TripleImageFastKineticsMixin
from .triple_imaging_fast_kinetics import calculate_grabber_rois

logger = logging.getLogger(__name__)


class _DoubleTrapROIOverrides(AndorImagingBase):
    def build_fragment(self):
        super().build_fragment()

        # Set default ROIs
        self.setattr_param_rebind(
            "roi_0_x0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
        )
        self.setattr_param_rebind(
            "roi_0_x1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
        )
        self.setattr_param_rebind(
            "roi_0_y0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
        )
        self.setattr_param_rebind(
            "roi_0_y1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        )

        self.setattr_param_rebind(
            "roi_1_x0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
        )
        self.setattr_param_rebind(
            "roi_1_x1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
        )
        self.setattr_param_rebind(
            "roi_1_y0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
        )
        self.setattr_param_rebind(
            "roi_1_y1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )


class DoubleTrapImagingBasic(_DoubleTrapROIOverrides, SingleAndorImage):
    """
    Image two traps with a single fluorescence pulse

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    num_andor_images = 1
    num_grabber_readouts = 1
    num_grabber_rois = 2


class DoubleTrapImagingBGSubtracted(_DoubleTrapROIOverrides, BGCorrectedAndorImage):
    """
    Image two traps with two fluorescence pulses and background-subtract

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    num_andor_images = 2
    num_grabber_readouts = 2
    num_grabber_rois = 2

    def bg_imaging_make_result_channel(self):
        self.setattr_result("andor_sum_fwd_corrected", FloatChannel)
        self.setattr_result("andor_sum_bkd_corrected", FloatChannel)
        self.andor_sum_fwd_corrected: FloatChannel
        self.andor_sum_bkd_corrected: FloatChannel

    @kernel
    def process_andor_data_hook(self, sums, means):
        self.andor_sum_fwd_corrected.push(sums[0] - sums[2])
        self.andor_sum_bkd_corrected.push(sums[1] - sums[3])


class DoubleTrapImagingNormalised(TripleImageFastKineticsMixin):
    """
    Image two traps with three pulses of light, imaging the ground, excited and
    background.

    Reumping is not handled here, but you can override e.g.
    :meth:`~do_first_pulse` to add it if required. See e.g.
    :class:`~ClockRabiSpectroscopyRedMotMixin`.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    num_andor_images = 3
    num_grabber_readouts = 1
    num_grabber_rois = 6

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction_forward", FloatChannel)
        self.setattr_result("atom_number_forward", FloatChannel)

        self.setattr_result("excitation_fraction_backward", FloatChannel)
        self.setattr_result("atom_number_backward", FloatChannel)

        self.excitation_fraction_forward: FloatChannel
        self.atom_number_forward: FloatChannel
        self.excitation_fraction_backward: FloatChannel
        self.atom_number_backward: FloatChannel

    def hook_setup_andor(self):
        """
        Setup the Andor camera to use 6x ROIs

        We're using fast kinetics mode. The first three ROIs are for the forward
        trap, the last three are for the backwards trap.
        """

        roi_defaults = calculate_grabber_rois(
            fast_kinetics_height=constants.ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP,
            fast_kinetics_offset=constants.ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP,
            num_images=3,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        ) + calculate_grabber_rois(
            fast_kinetics_height=constants.ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP,
            fast_kinetics_offset=constants.ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP,
            num_images=3,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )

        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=roi_defaults,
            add_pre_trigger_delay=True,
            fast_kinetics_num_shots=3,
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    @kernel
    def process_andor_data_hook(self, sums, means):
        atom_number_fwd = sums[0] + sums[1] - 2 * sums[2]
        atom_number_bwd = sums[3] + sums[4] - 2 * sums[5]

        if atom_number_fwd == 0:
            self.excitation_fraction_forward.push(0.0)
        else:
            self.excitation_fraction_forward.push((sums[1] - sums[2]) / atom_number_fwd)

        if atom_number_bwd == 0:
            self.excitation_fraction_backward.push(0.0)
        else:
            self.excitation_fraction_backward.push(
                (sums[4] - sums[5]) / atom_number_bwd
            )

        self.atom_number_forward.push(atom_number_fwd)
        self.atom_number_backward.push(atom_number_bwd)
