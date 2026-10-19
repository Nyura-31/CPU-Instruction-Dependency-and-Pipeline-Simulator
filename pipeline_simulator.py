"""Cycle-by-cycle five-stage pipeline with decode-stage dependency stalls."""

from dfa_validator import Instruction

STAGES = ("IF", "ID", "EX", "MEM", "WB")


def simulate_pipeline(
    instructions: list[Instruction], order: list[int]
) -> tuple[list[list[str]], int, dict[int, dict[str, int]]]:
    """Simulate the given order; return rows, total cycles, and stage cycles.

    Every instruction takes one cycle per stage. A consumer may decode in the
    same cycle its producer writes back (write-first register file). Otherwise
    it waits in ID until all source register values are available.
    """
    by_id = {instruction.index: instruction for instruction in instructions}
    schedule: dict[int, dict[str, int]] = {}
    producer_by_register: dict[str, int] = {}
    # IF starts in cycle 1. A single IF stage may hold an instruction while ID
    # is stalled, so the following instruction cannot be fetched until it
    # leaves IF. ID also accepts at most one instruction per cycle.
    previous_if_end = 0
    previous_id_end = 1
    for instruction_id in order:
        instruction = by_id[instruction_id]
        if_cycle = previous_if_end + 1
        id_start = max(if_cycle + 1, previous_id_end + 1)
        id_cycle = id_start
        for register in instruction.registers_read:
            producer_id = producer_by_register.get(register)
            if producer_id is not None:
                id_cycle = max(id_cycle, schedule[producer_id]["WB"])

        # ID is occupied from its first cycle through the cycle it reads its
        # inputs. WB and ID may share a cycle under the write-first assumption.
        if_end = max(if_cycle, id_start - 1)
        schedule[instruction_id] = {
            "IF": if_cycle,
            "IF_END": if_end,
            "ID_START": id_start,
            "ID": id_cycle,
            "EX": id_cycle + 1,
            "MEM": id_cycle + 2,
            "WB": id_cycle + 3,
        }
        previous_if_end = if_end
        previous_id_end = id_cycle
        for register in instruction.registers_written:
            producer_by_register[register] = instruction_id

    total_cycles = max((stages["WB"] for stages in schedule.values()), default=0)
    rows = [["-" for _ in range(total_cycles)] for _ in instructions]
    row_for_id = {instruction.index: row for instruction, row in zip(instructions, rows)}
    for instruction_id, stages in schedule.items():
        row = row_for_id[instruction_id]
        row[stages["IF"] - 1] = "IF"
        for cycle in range(stages["IF"] + 1, stages["IF_END"] + 1):
            row[cycle - 1] = "IF*"
        for cycle in range(stages["ID_START"], stages["ID"]):
            row[cycle - 1] = "ID*"
        row[stages["ID"] - 1] = "ID"
        for stage in ("EX", "MEM", "WB"):
            row[stages[stage] - 1] = stage
    return rows, total_cycles, schedule


def sequential_baseline_cycles(instruction_count: int) -> int:
    """Sequential baseline: each instruction uses all five stages alone."""
    return instruction_count * len(STAGES)


def performance(instruction_count: int, pipeline_cycles: int) -> dict[str, float | int]:
    """Return comparable sequential/pipeline cycle counts and derived metrics."""
    baseline = sequential_baseline_cycles(instruction_count)
    throughput = instruction_count / pipeline_cycles if pipeline_cycles else 0.0
    speedup = baseline / pipeline_cycles if pipeline_cycles else 0.0
    return {
        "instruction_count": instruction_count,
        "pipeline_cycles": pipeline_cycles,
        "sequential_cycles": baseline,
        "throughput": throughput,
        "speedup": speedup,
    }
