"""
:class:`ConstantHoister` is a code motion transform:
it moves any invariant loads to the earliest point where
they may be executed.
"""

from .. import types, ir

class ConstantHoister:
    def process(self, functions):
        for func in functions:
            self.process_function(func)

    def process_function(self, func):
        # Iterate to a fixed point in program order (each moved load may make
        # its users hoistable in turn). A deterministic visit order is
        # required so that independent loads land in the entry block in the
        # same order on every compile; popping a worklist built as a set of
        # instructions would order the entry block by object address and make
        # the emitted IR differ between processes, defeating the
        # content-addressed kernel cache.
        entry = func.entry()
        moved = set()
        changed = True
        while changed:
            changed = False
            for insn in list(func.instructions()):
                if (isinstance(insn, ir.GetAttr) and insn not in moved and
                        types.is_instance(insn.object().type) and
                        insn.attr in insn.object().type.constant_attributes):
                    has_variant_operands = False
                    index_in_entry = 0
                    for operand in insn.operands:
                        if isinstance(operand, ir.Argument):
                            pass
                        elif isinstance(operand, ir.Instruction) and operand.basic_block == entry:
                            index_in_entry = entry.index(operand) + 1
                        else:
                            has_variant_operands = True
                            break

                    if has_variant_operands:
                        continue

                    insn.remove_from_parent()
                    entry.instructions.insert(index_in_entry, insn)
                    moved.add(insn)
                    changed = True
