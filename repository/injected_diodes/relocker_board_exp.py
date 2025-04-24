from ndscan.experiment import make_fragment_scan_exp

from .relocker_board import RelockerAutoFrag
from .relocker_board import RelockerChannelFrag
from .relocker_board import RelockerFrag
from .relocker_board import ScanIJDRelockerFrag

RunRelockerChannel = make_fragment_scan_exp(RelockerChannelFrag)
RunAllRelockers = make_fragment_scan_exp(RelockerFrag)
RelockerAuto = make_fragment_scan_exp(RelockerAutoFrag)
ScanIJDRelocker = make_fragment_scan_exp(ScanIJDRelockerFrag)
