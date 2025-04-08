import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationSingleRampMixin
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)


class EvaporationFrag(EvaporationSingleRampMixin,
                      BGCorrectedAndorImage,
                      FLIRBlueMOTMeasurementMixin
                      ):
    
    """ 
    Do evaporation from XODT
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

Evaporation = make_fragment_scan_exp(EvaporationFrag)
