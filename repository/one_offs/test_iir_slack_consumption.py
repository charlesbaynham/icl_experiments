from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from ndscan.experiment import make_fragment_scan_exp, ExpFragment
from artiq.coredevice.core import Core
from artiq.language import delay_mu, now_mu, kernel, delay
from numpy import int64


class TestIIRSlackConsumptionFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag, manual_init=False)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_device("core")
        self.core: Core

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(500e-3)

        # Copy / paste from blue_3d_mot.do_blue_transfer_mot
        t_one_rtio_cycle_mu = int64(self.core.ref_multiplier)

        t_start_mu = now_mu()

        # Set the PGIA and loop params to the requested values
        for i in range(
            len(self.blue_3d_mot.blue_transfer_MOT.suservo_setters_and_param_handles)
        ):
            suservo_channel = (
                self.blue_3d_mot.blue_transfer_MOT.suservo_setters_and_param_handles[i][
                    0
                ]
            )
            suservo_channel.set_pgia_gain_mu(
                self.blue_3d_mot.blue_transfer_MOT.suservo_pgias[i]
            )
            delay_mu(t_one_rtio_cycle_mu)

            suservo_channel.set_iir_params(
                ki=self.blue_3d_mot.blue_transfer_MOT.suservo_kIs[i]
            )
            delay_mu(t_one_rtio_cycle_mu)

        t_end_mu = now_mu()

        print("t_end - t_start = ", self.core.mu_to_seconds(t_end_mu - t_start_mu))


TestIIRSlackConsumption = make_fragment_scan_exp(TestIIRSlackConsumptionFrag)
