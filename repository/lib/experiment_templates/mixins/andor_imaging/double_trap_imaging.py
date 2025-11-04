import logging

from artiq.language import host_only
from artiq.language import kernel
from artiq.language import rpc
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from ndscan.experiment import FloatChannel

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedXXODTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedXXODTSpectroscopyFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsDoubleTrapRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)

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
        self.setattr_result("andor_sum_imbalance", FloatChannel)
        self.setattr_result("andor_sum_total", FloatChannel)
        self.andor_sum_fwd_corrected: FloatChannel
        self.andor_sum_bkd_corrected: FloatChannel
        self.andor_sum_imbalance: FloatChannel
        self.andor_sum_total: FloatChannel

    @kernel
    def process_grabber_data_hook(self, sums, means):
        atom_number_fwd = sums[0] - sums[2]
        atom_number_bwd = sums[1] - sums[3]

        total = atom_number_fwd + atom_number_bwd
        if total == 0:
            imbalance = 0.0
        else:
            imbalance = (atom_number_fwd - atom_number_bwd) / total

        self.andor_sum_fwd_corrected.push(atom_number_fwd)
        self.andor_sum_bkd_corrected.push(atom_number_bwd)
        self.andor_sum_imbalance.push(imbalance)
        self.andor_sum_total.push(total)


class DoubleTrapImagingRepumpedNormalisedBase(
    NormalisedFastKineticsDoubleTrapRepumpedMixin
):
    """
    Image two traps with three pulses of light, imaging the ground, excited and
    background, with 707 repumping after the first pulse.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction_forward", FloatChannel)
        self.setattr_result("atom_number_forward", FloatChannel)

        self.setattr_result("excitation_fraction_backward", FloatChannel)
        self.setattr_result("atom_number_backward", FloatChannel)

        self.setattr_result("atom_number_imbalance", FloatChannel)
        self.setattr_result("atom_number_total", FloatChannel)

        self.excitation_fraction_forward: FloatChannel
        self.atom_number_forward: FloatChannel
        self.excitation_fraction_backward: FloatChannel
        self.atom_number_backward: FloatChannel
        self.atom_number_imbalance: FloatChannel
        self.atom_number_total: FloatChannel

    def host_setup(self):
        super().host_setup()

        self.launch_ellipse_applet()

    @host_only
    def launch_ellipse_applet(self):
        # Reconstruct the ndscan dataset path
        # This is a bit fragile, and ought to be based on NDScan functions

        self.setattr_device("ccb")
        dataset_path_x = f"ndscan.rid_{self.scheduler.rid}.points.channel_excitation_fraction_forward"
        dataset_path_y = f"ndscan.rid_{self.scheduler.rid}.points.channel_excitation_fraction_backward"

        cmd = f"${{artiq_applet}}plot_xy {dataset_path_y} --x {dataset_path_x}"
        self.ccb.issue("create_applet", "Excitation Lissajous plot", cmd)

    @kernel
    def process_grabber_data_hook(self, sums, means):
        sum_ground_fwd = sums[0]
        sum_excited_fwd = sums[1]
        sum_background_fwd_ground = sums[4]
        sum_background_fwd_excited = sums[5]
        sum_background_fwd = sum_background_fwd_ground + sum_background_fwd_excited
        sum_ground_bwd = sums[2]
        sum_excited_bwd = sums[3]
        sum_background_bwd_ground = sums[6]
        sum_background_bwd_excited = sums[7]
        sum_background_bwd = sum_background_bwd_ground + sum_background_bwd_excited
        atom_number_fwd = sum_ground_fwd + sum_excited_fwd - sum_background_fwd
        atom_number_bwd = sum_ground_bwd + sum_excited_bwd - sum_background_bwd

        if atom_number_fwd == 0:
            excitation_fraction_forward = 0.0
        else:
            excitation_fraction_forward = (
                sum_excited_fwd - sum_background_fwd_excited
            ) / atom_number_fwd

        if atom_number_bwd == 0:
            excitation_fraction_backward = 0.0
        else:
            excitation_fraction_backward = (
                sum_excited_bwd - sum_background_bwd_excited
            ) / atom_number_bwd

        total = atom_number_fwd + atom_number_bwd
        if total == 0:
            imbalance = 0.0
        else:
            imbalance = (atom_number_fwd - atom_number_bwd) / total

        self._double_trap_imaging_log_data(
            excitation_fraction_forward=excitation_fraction_forward,
            excitation_fraction_backward=excitation_fraction_backward,
            atom_number_fwd=atom_number_fwd,
            atom_number_bwd=atom_number_bwd,
            imbalance=imbalance,
            total=total,
        )

    @rpc(flags={"async"})
    def _double_trap_imaging_log_data(
        self,
        excitation_fraction_forward: float,
        excitation_fraction_backward: float,
        atom_number_fwd: float,
        atom_number_bwd: float,
        imbalance: float,
        total: float,
    ) -> None:
        # Log to NDScan
        self.excitation_fraction_forward.push(excitation_fraction_forward)
        self.excitation_fraction_backward.push(excitation_fraction_backward)
        self.atom_number_forward.push(atom_number_fwd)
        self.atom_number_backward.push(atom_number_bwd)
        self.atom_number_imbalance.push(imbalance)
        self.atom_number_total.push(total)

        # Log to InfluxDB
        self.influx_logger.write(
            tags={
                "type": "xxodt_atom_stats",
                "rid": self.scheduler.rid,
            },
            fields={
                "excitation_fraction_forward": excitation_fraction_forward,
                "excitation_fraction_backward": excitation_fraction_backward,
                "atom_number_forward": atom_number_fwd,
                "atom_number_backward": atom_number_bwd,
                "atom_number_imbalance": imbalance,
                "atom_number_total": total,
            },
        )


class DoubleTrapImagingRepumpedNormalised(
    NormalisedXXODTFastKineticsMixin, DoubleTrapImagingRepumpedNormalisedBase
):
    """
    Image two traps with three pulses of light, imaging the ground, excited and
    background, with 707 repumping after the first pulse.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """


class DoubleTrapImagingSpectroscopyRepumpedNormalised(
    NormalisedXXODTSpectroscopyFastKineticsMixin,
    DoubleTrapImagingRepumpedNormalisedBase,
):
    """
    Image two traps with three pulses of light, imaging the ground, excited and
    background, with 707 repumping after the first pulse.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """
