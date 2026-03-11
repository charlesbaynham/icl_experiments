import logging

from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.fragment import TransitoryError
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)

logger = logging.getLogger(__name__)


class _AtomNumberCheckFrag(Fragment):
    """Fragment that checks the atom number from the Andor camera.

    Raises a :class:`~ndscan.experiment.fragment.TransitoryError` if the
    background-corrected atom number (``andor_sum_bg_corrected``) is below a
    settable threshold, causing ndscan to retry the current point.

    This fragment is intended to be used via
    :class:`~AtomNumberCheckMixin`.

    Example usage::

        self.setattr_fragment("atom_number_check", AtomNumberCheckFrag)
        self.atom_number_check: AtomNumberCheckFrag
    """

    def build_fragment(self) -> None:
        self.setattr_param(
            "min_atom_number",
            IntParam,
            description="Minimum acceptable background-corrected atom number",
            default=0,
            min=0,
        )
        self.min_atom_number: IntParamHandle

        self.setattr_param(
            "enable_check",
            BoolParam,
            description="Enable the atom number check",
            default=False,
        )
        self.enable_check: BoolParamHandle

    @rpc
    def check_atom_number(self, atom_number: int) -> None:
        """Check that *atom_number* is above the configured threshold.

        Args:
            atom_number: The background-corrected atom number to check.

        Raises:
            TransitoryError: If *atom_number* is below ``min_atom_number``.
        """
        if not self.enable_check.get():
            return
        threshold: int = self.min_atom_number.get()
        if atom_number < threshold:
            logger.warning(
                "Atom number %g is below threshold %d, retrying point",
                atom_number,
                threshold,
            )
            raise TransitoryError(
                f"Atom number {atom_number:.4g} is below threshold {threshold}"
            )


class AtomNumberCheckMixin(BGCorrectedAndorImage):
    """Mixin that raises a :class:`~ndscan.experiment.fragment.TransitoryError`
    when the atom number is too low.

    After every imaging sequence the background-corrected atom number
    (``andor_sum_bg_corrected``) is checked against a settable threshold.  If
    it is below the threshold a ``TransitoryError`` is raised, which causes
    ndscan to automatically retry the current scan point.

    This mixin must appear before :class:`~.BGCorrectedAndorImage` in the MRO::

        class MyExperimentFrag(
            AtomNumberCheckMixin,
            BGCorrectedAndorImage,
            RedMOTWithExperiment,
        ):
            ...

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~process_grabber_data_hook`
    * :meth:`~host_functions_after_experiment_hook`
    """

    def build_fragment(self) -> None:
        super().build_fragment()

        self.setattr_fragment("atom_number_check", _AtomNumberCheckFrag)
        self.atom_number_check: _AtomNumberCheckFrag

        # Stores the most recent bg-corrected atom number so it can be
        # accessed in host_functions_after_experiment_hook.
        self._last_atom_number: int = 0

    @kernel
    def process_grabber_data_hook(self, sums, means):
        self.process_grabber_data_hook_bgcorrection(sums, means)
        self.process_grabber_data_hook_atomcheck(sums, means)

    @kernel
    def process_grabber_data_hook_atomcheck(self, sums, means):
        # Store the bg-corrected atom number on the kernel so we can check it
        # later in host_functions_after_experiment_hook
        self._last_atom_number = sums[0] - sums[1]

    @kernel
    def host_functions_after_experiment_hook(self):
        self.host_functions_after_experiment_hook_default()
        self.host_functions_after_experiment_hook_atom_number_check()

    @kernel
    def host_functions_after_experiment_hook_atom_number_check(self):
        self.atom_number_check.check_atom_number(self._last_atom_number)
