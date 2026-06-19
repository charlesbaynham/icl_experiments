"""
Probe: does the ARTIQ kernel compiler accept a Python ``IntEnum`` member where
we currently use bare ``int`` constants?

``repository.lib.pulse_intent`` defines the intent-record vocabulary as a flat
list of module-level ``int`` constants (``KIND_PULSE = 0`` ...) plus hand-written
``__post_init__`` validation. Those codes are consumed by ``@portable`` methods
on ``PulseDMARecording`` (``register_pulse`` and friends), so they cross into
kernel code. The obvious tidy-up is to replace the loose ints with an
``IntEnum`` and let the type system do the checking - but only if the ARTIQ
kernel compiler can actually digest an ``IntEnum`` member.

This test compiles a tiny kernel that uses an ``IntEnum`` member as a value, in
a comparison against a runtime kernel int, and in integer arithmetic - exactly
how the intent codes are used.

Result (confirmed on the vendored ARTIQ fork): it COMPILES. ``IntEnum`` members
subclass ``int``, and the kernel compiler inlines them as ordinary int
constants. So the flat module-level ``int`` constants in ``pulse_intent`` can be
replaced with an ``IntEnum`` and the hand-written ``__post_init__`` validation
deleted. This test stays as a regression guard: if a future ARTIQ bump breaks
``IntEnum`` in kernels it will fail here, pointing straight at the cause.
"""

from enum import IntEnum

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment


class _IntentKind(IntEnum):
    PULSE = 0
    CLEAROUT = 1
    CALLBACK = 2


class IntEnumInKernelFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

    @kernel
    def run_once(self):
        # Use IntEnum members the way the intent vocabulary would on the kernel:
        #   - bound in kernel scope as a value,
        #   - compared against a genuine *runtime* kernel int (the dispatch the
        #     recorder/decoder does, not two host-folded constants), and
        #   - used in integer arithmetic.
        kind = _IntentKind.PULSE
        n = 0
        for i in range(3):  # i is a real runtime kernel int
            if i == _IntentKind.CLEAROUT:
                n += _IntentKind.CALLBACK
        if kind == _IntentKind.PULSE:
            n += 1
        return n


def test_intenum_member_compiles_in_kernel(fragment_precompiler):
    """Compile a kernel that uses an IntEnum member as an int.

    Passes on the vendored ARTIQ fork: IntEnum members compile as int
    constants in kernels (see module docstring). If this ever starts failing,
    an ARTIQ bump has dropped IntEnum support and the flat-int encoding in
    ``pulse_intent`` must stay.
    """
    fragment_precompiler(IntEnumInKernelFrag)
