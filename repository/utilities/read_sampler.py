from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.read_adc import ReadSamplerADC

ReadSampler = make_fragment_scan_exp(ReadSamplerADC)
