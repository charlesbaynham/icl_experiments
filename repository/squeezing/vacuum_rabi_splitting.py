from repository.lib.utils import _Stub


class SingleVRSSweepFrag(_Stub):
    """
    Single sided RF sweep on the 689 VRS AM

    This sequence traps the atoms from a narrowband red mot and does a vacuum Rabi
    splitting measurement. This includes preparing a scope to readout from the PMT
    and triggering it while sweeping the amplitude modulator on the 689 probe beam.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks)

        * :meth:`~do_experiment_after_red_mot_hook`
        * :meth:`~host_functions_after_experiment_hook`
    """
