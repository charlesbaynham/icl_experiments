"""Specialise a shared Fragment class per enclosing type, for ARTIQ.

See :func:`specialise_per_enclosing_type` for the what and why.
"""

from typing import Type

#: Cache of specialised subclasses, keyed by (base class, enclosing type).
_specialised_subclasses = {}


def specialise_per_enclosing_type(base_cls: type, enclosing_type: type) -> Type:
    """Return a distinct subclass of ``base_cls``, one per ``enclosing_type``.

    Use this for a Fragment that carries a member whose *type* depends on its
    enclosing fragment - typically a back-reference to the encloser
    (``outer_self``) or a config object it is parameterised by. ARTIQ infers one
    type per ``(class, attribute)`` across a whole compiled kernel, so a single
    shared class cannot hold that member as two different types at once. That
    bites when a fused kernel (e.g. a qbutler DAG-fix that runs several
    calibrations' measurements) touches two *different* enclosing fragments: the
    shared member's type differs between them and ARTIQ fails to unify it.

    Giving each enclosing type its own subclass keeps the member's type
    consistent within one class (so its instances unify), while different
    enclosing types get distinct classes ARTIQ never tries to unify. Call it
    where you build the subfragment, passing ``type(self)`` as the encloser::

        self.setattr_fragment(
            "dma_recording_fragment",
            specialise_per_enclosing_type(PulseDMARecording, type(self)),
            outer_self=self,
        )

    Subclasses are cached, so repeated calls with the same ``(base_cls,
    enclosing_type)`` return the same class.
    """
    key = (base_cls, enclosing_type)
    cls = _specialised_subclasses.get(key)
    if cls is None:
        cls = type(
            f"{base_cls.__name__}_for_{enclosing_type.__name__}", (base_cls,), {}
        )
        _specialised_subclasses[key] = cls
    return cls
