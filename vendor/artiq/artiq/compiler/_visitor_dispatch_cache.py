"""Speed up pythonparser AST visitor dispatch.

pythonparser's ``Visitor._visit_one``/``Transformer._visit_one`` resolve the
``visit_<NodeType>`` method with a string concatenation plus ``hasattr`` +
``getattr`` on every single node visit. The ARTIQ compiler performs millions
of node visits per kernel compile (the inferencer alone re-walks every
embedded function), so this dynamic lookup is a measurable fraction of
compile time.

This module replaces ``_visit_one`` on both base classes with a version that
caches the resolved method per (visitor class, node class) pair. Visitor
classes in ARTIQ define all ``visit_*`` handlers on the class (never on
instances), so a class-keyed cache is safe.
"""

from pythonparser import algorithm as _algorithm

_dispatch_cache = {}


def _cached_visit_one(self, node):
    key = (self.__class__, node.__class__)
    try:
        method = _dispatch_cache[key]
    except KeyError:
        method = getattr(self.__class__, "visit_" + node.__class__.__name__, None)
        _dispatch_cache[key] = method
    if method is not None:
        return method(self, node)
    return self.generic_visit(node)


def install():
    _algorithm.Visitor._visit_one = _cached_visit_one
    _algorithm.Transformer._visit_one = _cached_visit_one
