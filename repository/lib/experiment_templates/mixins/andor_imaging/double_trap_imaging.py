import logging

import numpy as np
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import portable
from artiq.language import rpc
from artiq.master.scheduler import Scheduler
from artiq.master.worker_impl import CCB
from artiq_influx_generic import InfluxController
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.andor_camera import AndorCameraConfig

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedXXODTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedXXODTSpectroscopyFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsDoubleTrapClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsDoubleTrapRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImageMixin,
)

logger = logging.getLogger(__name__)


class _DoubleTrapAndorImageConfigBase(AndorCameraConfig):
    """
    Base config for imaging two traps (forward + backward).

    Provides 8 ROI IntParams (fwd_roi_* and bwd_roi_*) and a get_rois() that
    returns them in [fwd, bwd] order. Subclasses must set num_andor_images,
    num_images_per_series and num_grabber_readouts.
    """

    num_grabber_rois = 2

    def build_fragment(
        self,
        fwd_x0,
        fwd_y0,
        fwd_x1,
        fwd_y1,
        bwd_x0,
        bwd_y0,
        bwd_x1,
        bwd_y1,
    ):
        super().build_fragment()

        self.setattr_param(
            "fwd_roi_x0",
            IntParam,
            "Forward trap grabber ROI x0",
            default=fwd_x0,
            min=0,
            max=512,
        )
        self.fwd_roi_x0: IntParamHandle
        self.setattr_param(
            "fwd_roi_y0",
            IntParam,
            "Forward trap grabber ROI y0",
            default=fwd_y0,
            min=0,
            max=1024,
        )
        self.fwd_roi_y0: IntParamHandle
        self.setattr_param(
            "fwd_roi_x1",
            IntParam,
            "Forward trap grabber ROI x1",
            default=fwd_x1,
            min=0,
            max=512,
        )
        self.fwd_roi_x1: IntParamHandle
        self.setattr_param(
            "fwd_roi_y1",
            IntParam,
            "Forward trap grabber ROI y1",
            default=fwd_y1,
            min=0,
            max=1024,
        )
        self.fwd_roi_y1: IntParamHandle

        self.setattr_param(
            "bwd_roi_x0",
            IntParam,
            "Backward trap grabber ROI x0",
            default=bwd_x0,
            min=0,
            max=512,
        )
        self.bwd_roi_x0: IntParamHandle
        self.setattr_param(
            "bwd_roi_y0",
            IntParam,
            "Backward trap grabber ROI y0",
            default=bwd_y0,
            min=0,
            max=1024,
        )
        self.bwd_roi_y0: IntParamHandle
        self.setattr_param(
            "bwd_roi_x1",
            IntParam,
            "Backward trap grabber ROI x1",
            default=bwd_x1,
            min=0,
            max=512,
        )
        self.bwd_roi_x1: IntParamHandle
        self.setattr_param(
            "bwd_roi_y1",
            IntParam,
            "Backward trap grabber ROI y1",
            default=bwd_y1,
            min=0,
            max=1024,
        )
        self.bwd_roi_y1: IntParamHandle

        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        self.roi_buffer[0][0] = self.fwd_roi_x0.get()
        self.roi_buffer[0][1] = self.fwd_roi_y0.get()
        self.roi_buffer[0][2] = self.fwd_roi_x1.get()
        self.roi_buffer[0][3] = self.fwd_roi_y1.get()
        self.roi_buffer[1][0] = self.bwd_roi_x0.get()
        self.roi_buffer[1][1] = self.bwd_roi_y0.get()
        self.roi_buffer[1][2] = self.bwd_roi_x1.get()
        self.roi_buffer[1][3] = self.bwd_roi_y1.get()
        return self.roi_buffer


class DoubleTrapBasicAndorImageConfig(_DoubleTrapAndorImageConfigBase):
    """Config for DoubleTrapImagingBasicMixin: 2 ROIs, 1 readout, 1 image per series."""

    num_andor_images = 1
    num_images_per_series = 1
    num_grabber_readouts = 1


class DoubleTrapBGCorrectedAndorImageConfig(_DoubleTrapAndorImageConfigBase):
    """Config for DoubleTrapImagingBGSubtractedMixin: 2 ROIs, 2 readouts, 2 images per series."""

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_readouts = 2


_DOUBLE_TRAP_DEFAULT_ROIS = dict(
    fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
    fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
    fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
    fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
    bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
    bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
    bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
    bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
)


class DoubleTrapImagingBasicMixin(SingleAndorImageMixin):
    """
    Image two traps with a single fluorescence pulse

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            DoubleTrapBasicAndorImageConfig,
            **_DOUBLE_TRAP_DEFAULT_ROIS,
        )
        return f  # type: ignore


class DoubleTrapImagingBGSubtractedMixin(BGCorrectedAndorImageMixin):
    """
    Image two traps with two fluorescence pulses and background-subtract

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            DoubleTrapBGCorrectedAndorImageConfig,
            **_DOUBLE_TRAP_DEFAULT_ROIS,
        )
        return f  # type: ignore

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
        self.ccb: CCB

        rid = self.scheduler.rid

        dataset_path_x = f"ndscan.rid_{rid}.points.channel_excitation_fraction_forward"
        dataset_path_y = f"ndscan.rid_{rid}.points.channel_excitation_fraction_backward"

        cmd = f'${{artiq_applet}}plot_xy {dataset_path_y} --x {dataset_path_x} --title "RID {rid}"'
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


class DoubleTrapImagingClockPulseNormalisedBase(
    NormalisedFastKineticsDoubleTrapClockPulseMixin
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
        rid = self.scheduler.rid
        dataset_path_x = f"ndscan.rid_{rid}.points.channel_excitation_fraction_forward"
        dataset_path_y = f"ndscan.rid_{rid}.points.channel_excitation_fraction_backward"

        cmd = f'${{artiq_applet}}plot_xy {dataset_path_y} --x {dataset_path_x} --title "RID {rid}"'
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


class DoubleTrapImagingRepumpedNormalisedMixin(
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


class DoubleTrapImagingClockPulseNormalisedMixin(
    NormalisedXXODTFastKineticsMixin, DoubleTrapImagingClockPulseNormalisedBase
):
    """
    Image two traps with three pulses of light, imaging the ground, excited and
    background, with 707 repumping after the first pulse.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """


class DoubleTrapImagingSpectroscopyRepumpedNormalisedMixin(
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


DoubleTrapImagingSpectroscopyRepumpedNormalised = (
    DoubleTrapImagingSpectroscopyRepumpedNormalisedMixin
)
