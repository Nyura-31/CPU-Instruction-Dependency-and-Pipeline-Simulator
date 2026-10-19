"""Build a register-hazard graph while preserving program semantics."""

from dfa_validator import Instruction


def build_dependency_graph(instructions: list[Instruction]) -> dict[int, list[int]]:
    """Create earlier-to-later edges for RAW, WAR, and WAW hazards.

    The additional WAR and WAW edges keep reordered independent work from
    changing the original program's register behavior.
    """
    graph = {instruction.index: [] for instruction in instructions}
    for earlier_position, earlier in enumerate(instructions):
        for later in instructions[earlier_position + 1:]:
            has_hazard = bool(
                earlier.registers_written & later.registers_read
                or earlier.registers_read & later.registers_written
                or earlier.registers_written & later.registers_written
            )
            if has_hazard:
                graph[earlier.index].append(later.index)
    return graph
