import logging
import textwrap

from artiq.language import kernel_from_string
from artiq.language import portable
from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class CheckpointFragment(Fragment):
    """
    An NDScan fragment with the addition of Checkpoints

    A Checkpoint is a method that can be implemented by subfragments (or their
    subfragments) and that will be called at some point by the user. When this
    happens, all the subfragments' implementations of the checkpoint will be
    run.

    To use this you should subclass from this class and:

    * Choose some checkpoint names and list them in `checkpoint_method_names`.
    * Write default implementations for each of these. Probably just calling
      `self.<your-hook-name>_subfragments()`.
    * Optionally, write a stub method for
      `self.<your-hook-name>_subfragments()`. This does nothing, but means that
      users will get autocompletion in their IDE.

    See :class:`~RedMOTCheckpoints` for an example.
    """

    checkpoint_method_names = None

    @classmethod
    def _checkpoint_is_trivial(cls, frag, checkpoint_name: str):
        """
        Check if the passed fragment or its children use this checkpoint

        There are two ways that this checkpoint could be not used:

        a) The (sub)fragment is a CheckpointFragment but which has not
           implemented this checkpoint. The method will therefore exist but do
           nothing.
        b) The sub(fragment) is a plain Fragment and has no concept of this
           Checkpoint. The method will not exist.

        Anything other than these two scenarios == a non-trivial checkpoint
        implementation.

        This is written as a classmethod instead of a normal bound method so
        that it can be called passing Fragments as well as CheckpointFragments.
        """
        assert not frag._building
        we_have_trivial_checkpoint = not hasattr(frag, checkpoint_name) or getattr(
            frag, checkpoint_name
        ).__func__ is getattr(cls, checkpoint_name)

        children_have_trivial_checkpoints = all(
            [cls._checkpoint_is_trivial(f, checkpoint_name) for f in frag._subfragments]
        )
        return we_have_trivial_checkpoint and children_have_trivial_checkpoints

    def build(self, *args, **kwargs):
        # Make sure that kernel_invariants is defined. This isn't really related
        # to checkpoints, but I'm constantly annoyed that I have to do this
        # everywhere and Sebastian won't let me merge it into upstream ARTIQ, so
        # I'll just add it here.
        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        super().build(*args, **kwargs)

        if self.checkpoint_method_names is None:
            raise TypeError(
                f"You must define `checkpoint_method_names`. See the following docstring for this class:\n\n{CheckpointFragment.__doc__}"
            )

        for checkpoint_name in self.checkpoint_method_names:
            # Check that we have a default implementation defined. This is done
            # manually so that type checkers can read it: see above.
            assert hasattr(
                self, checkpoint_name
            ), f"You must provide a default implementation of {checkpoint_name}"

            # Check that there's a `*_subfragments`` method defined. This isn't
            # essential, but means that type checkers and IDE type hints will
            # work.
            if not hasattr(self, f"{checkpoint_name}_subfragments"):
                logger.warning(
                    textwrap.dedent(
                        """
                        No %s_subfragments method statically defined

                        This is not an error since this method will be defined
                        dynamically, but means that type annotation and IDE type
                        hints will not work. Consider adding one to help people use
                        your checkpoint.
                        """
                    ).strip(),
                    checkpoint_name,
                )

            # Build an implementation kernel that calls all this fragments'
            # subfragments' checkpoints
            code = ""
            for s in self._subfragments:
                if s in self._detached_subfragments:
                    continue
                if self.__class__._checkpoint_is_trivial(
                    s, checkpoint_name=checkpoint_name
                ):
                    continue
                code += f"self.{s._fragment_path[-1]}.{checkpoint_name}()\n"

            code += "pass\n"

            implementation_kernel = kernel_from_string(["self"], code[:-1], portable)
            implementation_kernel_name = f"{checkpoint_name}_subfragments"

            # Overwrite the "*_subfragment" stub defined above with this
            # implementation, binding it to the instance (see
            # https://docs.python.org/3/howto/descriptor.html#functions-and-methods
            # for an interesting look at how python treats class methods vs.
            # functions)
            setattr(
                self,
                implementation_kernel_name,
                implementation_kernel.__get__(self),
            )


class RedMOTCheckpoints(CheckpointFragment):
    """
    Checkpoints for the :class:`~RedMOTWithExperiment` experiment template
    """

    checkpoint_method_names = [
        "DMA_initialization_checkpoint",
        "pre_sequence_checkpoint",
        "end_of_blue_3d_mot_loading_checkpoint",
        "start_of_red_broadband_checkpoint",
        "end_of_broadband_mot_checkpoint",
        "post_narrowband_checkpoint",
        "pre_expansion_checkpoint",
        "after_first_imaging_pulse_checkpoint",
        "post_sequence_cleanup_checkpoint",
        "after_data_saved_checkpoint",
    ]

    # Default implementations of checkpoints. These could be dynamically
    # generated easily, but we write them out manually so that type checkers can
    # see them and we can write some documentation.
    @portable
    def DMA_initialization_checkpoint(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.DMA_initialization_checkpoint_subfragments()

    @portable
    def pre_sequence_checkpoint(self):
        """
        Checkpoint for core actions that can affect the timeline at the start
        of the sequence

        In contrast to :meth:`~before_start_hook`, break_realtimes will affect
        the sequence timeline from this point onwards.
        """
        self.pre_sequence_checkpoint_subfragments()

    @portable
    def end_of_blue_3d_mot_loading_checkpoint(self):
        """
        Executed when the loading blue MOT ends, as the ramping blue MOT phase begins.

        This will clash with the blue ramping phase: only add events here if you include a negative delay
        """
        self.end_of_blue_3d_mot_loading_checkpoint_subfragments()

    @portable
    def start_of_red_broadband_checkpoint(self):
        """
        Executed as the broadband MOT stage starts.

        This hook is just before the broadband MOT starts. It should take
        negligible duration (i.e. just a few coarse RTIO cycles) otherwise
        assumptions about the broadband MOT duration will be wrong
        """
        self.start_of_red_broadband_checkpoint_subfragments()

    @portable
    def end_of_broadband_mot_checkpoint(self):
        """
        Executed immediately after the broadband MOT stage ends, before the
        broadband ramping is disabled. No timeline correction is performed, so
        changes here will delay the narrowband red MOT.
        """
        self.end_of_broadband_mot_checkpoint_subfragments()

    @portable
    def post_narrowband_checkpoint(self):
        """
        Executed immediately after the red beams go off on the narrowband MOT.

        No timeline correction is performed, so changes here will delay the
        experiment / dipole trapping that occurs after the red MOT.

        Note that the beams are turned off by the default implementation of
        :meth:`~post_narrowband_hook` which occurs immediately before this
        checkpoint. If you want the beams to stay on, you can override this
        hook.
        """
        self.post_narrowband_checkpoint_subfragments()

    @portable
    def pre_expansion_checkpoint(self):
        """
        Hook for core actions after the narrowband red mot is completed, after
        the light is turned off and cloud expansion begins

        Any changes to the cursor made by this hook will be ignored
        """
        self.pre_expansion_checkpoint_subfragments()

    @portable
    def after_first_imaging_pulse_checkpoint(self):
        """
        Checkpoint for core actions after the first fluorescence imaging pulse

        Unlike the other checkpoints, this is not called by RedMOTExperiment
        directly but by the Andor imaging mixins instead. Also, it's only called
        by sequences that have more than one image, so code in this checkpoint
        will not run if there is only one image taken.

        Any changes to the cursor made by this hook will be ignored
        """
        self.after_first_imaging_pulse_checkpoint_subfragments()

    @portable
    def post_sequence_cleanup_checkpoint(self):
        """
        Called immediately after the imaging is completed while there is still
        some slack.

        This is the last chance to do timing-critical things. Slow,
        non-timing-critical things like readout should be in
        :meth:`~after_data_saved_checkpoint` instead.
        """
        self.post_sequence_cleanup_checkpoint_subfragments()

    @portable
    def after_data_saved_checkpoint(self):
        """
        Called after the sequence is completed and the core has waiting for time
        to catch up with the cursor

        This is used mostly for saving data that was taken during the
        time-critical and can now be read out without affecting timings.

        Contrast with :meth:`~post_sequence_cleanup_checkpoint` which is called
        immediately after the imaging is completed while there is still some
        slack.
        """
        self.after_data_saved_checkpoint_subfragments()

    # Stubs for "*_subfragments" methods for checkpoints. These are overwritten
    # in build_fragment so the following code never gets run: it's just here for
    # type annotations. Do not override these in children classes! It won't
    # work, they'll just be rewritten anyway. If you want to override something,
    # don't call these methods and just implement their functionality in your
    # checkpoint directly.

    @portable
    def DMA_initialization_checkpoint_subfragments(self):
        pass

    @portable
    def pre_sequence_checkpoint_subfragments(self):
        pass

    @portable
    def end_of_blue_3d_mot_loading_checkpoint_subfragments(self):
        pass

    @portable
    def start_of_red_broadband_checkpoint_subfragments(self):
        pass

    @portable
    def end_of_broadband_mot_checkpoint_subfragments(self):
        pass

    @portable
    def post_narrowband_checkpoint_subfragments(self):
        pass

    @portable
    def pre_expansion_checkpoint_subfragments(self):
        pass

    @portable
    def after_first_imaging_pulse_checkpoint_subfragments(self):
        pass

    @portable
    def post_sequence_cleanup_checkpoint_subfragments(self):
        pass

    @portable
    def after_data_saved_checkpoint_subfragments(self):
        pass
