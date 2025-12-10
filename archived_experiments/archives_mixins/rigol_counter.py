from artiq.language import kernel

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from archived_experiments.archives_fragments.rigol_counter import RigolCounterFrag


class RigolCounterMixin(RedMOTWithExperiment):
    def build_fragment(self):
        self.setattr_fragment("rigol", RigolCounterFrag)
        self.rigol: RigolCounterFrag
        super().build_fragment()

    @kernel
    def host_functions_after_experiment_hook(self):
        self.host_functions_after_experiment_hook_default()
        self.host_functions_after_experiment_hook_rigol()

    @kernel
    def host_functions_after_experiment_hook_rigol(self):
        self.rigol.check_counter_rpc()
