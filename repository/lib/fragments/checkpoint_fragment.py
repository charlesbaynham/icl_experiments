import textwrap
from artiq.language import HasEnvironment, kernel, kernel_from_string, portable, rpc
import logging
from ndscan.experiment import Fragment
from artiq.experiment import kernel

logger = logging.getLogger(__name__)


class CheckpointFragment(Fragment):
    """
    An NDScan fragment with the addition of Checkpoints

    A Checkpoint is a method that can be implemented by subfragments (or their
    subfragments) and that will be called at some point by the user. When this
    happens, all the subfragments' implementations of the checkpoint will be
    run.

    For now, this directly defines the checkpoints we'll use in the AION code.
    Later, if this proves useful, we can make this more general.
    """

    checkpoint_method_names = ["test_checkpoint"]  # FIXME

    # Default implementations of checkpoints. These could be dynamically
    # generated easily, but we write them out so that type checkers can see them
    @portable
    def test_checkpoint(self):
        self.test_checkpoint_subfragments()

    # Stubs for "*_subfragments" methods for checkpoints. These are overwritten
    # in build_fragment so the following code never gets run: it's just here for
    # type annotations. Do not override these in children classes! It won't
    # work, they'll just be rewritten anyway. If you want to override something,
    # don't call these methods and just implement their functionality in your
    # checkpoint directly.
    @portable
    def test_checkpoint_subfragments(self):
        pass

    @portable
    def _noop(self):
        pass

    @classmethod
    def _checkpoint_is_trivial(cls, frag, checkpoint_name: str):
        """
        Check if the passed fragment or its children use this checkpoint

        There are two ways that this checkpoint could be not used:

        a) The (sub)fragment is a CheckpointFragment but which has not
           implemented this checkpoint. The method will therefore be a _noop.
        b) The sub(fragment) is a plain Fragment and has no concept of this
           Checkpoint. The method will not exist.

        Anything other than these two scenarios == a non-trivial checkpoint
        implementation.

        This is written as a classmethod instead of a normal bound method so
        that it can be called passing Fragments as well as CheckpointFragments.
        """
        assert not frag._building
        we_have_trivial_checkpoint = (
            not hasattr(frag, checkpoint_name)
            or getattr(frag, checkpoint_name).__func__ is cls._noop
        )

        children_have_trivial_checkpoints = all(
            [cls._checkpoint_is_trivial(f, checkpoint_name) for f in frag._subfragments]
        )
        return we_have_trivial_checkpoint and children_have_trivial_checkpoints

    def build(self, *args, **kwargs):
        super().build(*args, **kwargs)

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
                if CheckpointFragment._checkpoint_is_trivial(
                    s, checkpoint_name=checkpoint_name
                ):
                    continue
                code += f"self.{s._fragment_path[-1]}.{checkpoint_name}()\n"

            implementation_kernel = (
                kernel_from_string(["self"], code[:-1], portable)
                if code
                else self._noop
            )
            implementation_kernel_name = f"{checkpoint_name}_subfragments"

            # Overwrite the "*_subfragment" stub defined above with this
            # implementation, binding it to the instance (see
            # https://docs.python.org/3/howto/descriptor.html#functions-and-methods
            # for an interesting look at how python treats class methods vs.
            # functions)
            setattr(
                self,
                implementation_kernel_name,
                implementation_kernel.__get__(self, self.__class__),
            )
