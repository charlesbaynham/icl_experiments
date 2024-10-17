from ndscan.experiment import * 
from ndscan.experiment.parameters import FloatParamHandle 

 

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag 
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement 

 

class ScanPlugBeamParamsFrag(ExpFragment): 

def build_fragment(self) -> None: 

self.setattr_device("core") 

self.core: Core 

 
 

self.setattr_fragment("blue_mot", Blue3DMOTFrag) 

self.blue_mot: Blue3DMOTFrag 

 

self.setattr_fragment( 

"dual_cameras", DualCameraMeasurement, hardware_trigger=True 

) 

self.dual_cameras: DualCameraMeasurement 

 

 

self.setattr_param( 

"plug_aom_attenuation", 

FloatParam, 

description="Attenuation on Urukul's variable attenuator", 

default=30, 

unit="dB", 

min=0, 

max=31.5, 

) 

 

self.setattr_param( 

"plug_aom_frequency", 

FloatParam, 

description="Frequency of plug beam AOM", 

default=165, 

unit="MHz", 

min=145, 

max=185, 

) 

 

self.plug_aom_attenuation: FloatParamHandle 

self.plug_aom_frequency: FloatParamHandle 

 

 

#need to replace the names of the following with relevant things for the AOM 

@kernel 

def run_once(self) -> None: 

new_plug_attenuation = self.plug_aom_attenuation.get() 

new_plug_frequency = self.plug_aom_frequency.get() 

 
self.set_plug_aom( 

new_plug_attenuation=new_plug_attenuation, 

new_plug_frequency=new_plug_frequency, 

) 

 
self.blue_mot.load_mot(clearout=self.clearout) #need to add something like delay(1.0)? 

 

self.dual_cameras.trigger() 

 
 

self.core.wait_until_mu(now_mu()) 

self.dual_cameras.save_data() 

 

 

ScanPlugBeamParams= make_fragment_scan_exp(ScanPlugBeamParamsFrag) 

 
 