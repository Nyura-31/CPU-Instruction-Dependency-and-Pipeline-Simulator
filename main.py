"""Terminal interface for the CPU instruction dependency pipeline simulator."""

from pathlib import Path

from dependency_graph import build_dependency_graph
from dfa_validator import Instruction, validate_program
from pipeline_simulator import STAGES, performance, simulate_pipeline
from topological_sort import topological_sort

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "sample_programs" / "sample.asm"


def show_validation(lines: list[str], instructions: list[Instruction], errors: list[tuple[int, str]]) -> None:
    print("\n1. DFA syntax validation")
    valid_by_line = {item.index: item for item in instructions}
    line_number = 0
    error_by_line = dict(errors)
    for source in lines:
        if not source.strip():
            continue
        line_number += 1
        if line_number in valid_by_line:
            print(f"  {line_number:>2}. ACCEPT  {source.strip()}")
        else:
            print(f"  {line_number:>2}. REJECT  {source.strip()} — {error_by_line[line_number]}")


def run_analysis(lines: list[str]) -> None:
    instructions, errors = validate_program(lines)
    show_validation(lines, instructions, errors)
    if errors:
        print("\nScheduling stopped: fix the rejected instruction(s) and try again.")
        return
    if not instructions:
        print("\nNo instructions to schedule. Pipeline cycles: 0.")
        print("Sequential baseline cycles: 0; throughput: 0.000 instructions/cycle; speedup: 0.000x.")
        return

    print("\n2. Original instruction sequence")
    for instruction in instructions:
        print(f"  I{instruction.index}: {instruction.text}")

    graph = build_dependency_graph(instructions)
    print("\n3. Register dependency graph (instruction ID -> dependent IDs)")
    for node, neighbors in graph.items():
        print(f"  I{node} -> {', '.join(f'I{target}' for target in neighbors) if neighbors else '(none)'}")
    print(f"  Dependency edges: {sum(map(len, graph.values()))}")

    print("\n4. Topological order (Kahn's algorithm; longest remaining path first)")
    try:
        order = topological_sort(graph)
    except ValueError as error:
        print(f"  Error: {error}")
        return
    by_id = {item.index: item for item in instructions}
    for position, instruction_id in enumerate(order, start=1):
        print(f"  {position}. I{instruction_id}: {by_id[instruction_id].text}")
    position_by_id = {instruction_id: position for position, instruction_id in enumerate(order)}
    all_edges_respected = all(
        position_by_id[source] < position_by_id[target]
        for source, targets in graph.items()
        for target in targets
    )
    if not all_edges_respected:
        print("  Error: a dependency edge is not respected; pipeline simulation stopped.")
        return
    print("  Valid order: every dependency edge points forward in this order.")

    print("\n5. Five-stage pipeline timing table (- = empty, * = held during a stall)")
    rows, cycles, _ = simulate_pipeline(instructions, order)
    headers = [f"C{cycle}" for cycle in range(1, cycles + 1)]
    label_width = max(11, max(len(f"I{x}: {by_id[x].text}") for x in order))
    print(f"  {'Instruction':<{label_width}} " + " ".join(f"{heading:>4}" for heading in headers))
    for instruction_id, row in zip([item.index for item in instructions], rows):
        label = f"I{instruction_id}: {by_id[instruction_id].text}"
        print(f"  {label:<{label_width}} " + " ".join(f"{stage:>4}" for stage in row))

    result = performance(len(instructions), cycles)
    print("\n6. Performance summary")
    print(f"  Valid instructions:          {result['instruction_count']}")
    print(f"  Pipeline cycles:             {result['pipeline_cycles']}")
    print(f"  Sequential baseline cycles:  {result['sequential_cycles']}")
    print(f"  Throughput:                  {result['throughput']:.3f} instructions/cycle")
    print(f"  Speedup:                     {result['speedup']:.3f}x")
    print("  Baseline assumes each instruction takes IF, ID, EX, MEM, WB alone (5 cycles).")
    print("  Pipeline uses one cycle per stage; WB writes before ID reads in the same cycle.")


def read_interactive_program() -> list[str]:
    print("Enter one instruction per line. Submit a blank line to finish.")
    lines: list[str] = []
    while True:
        try:
            line = input(f"{len(lines) + 1:>2}> ")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return lines


def main() -> None:
    while True:
        print("\n" + "=" * 65)
        print("CPU INSTRUCTION DEPENDENCY AND PIPELINE SIMULATOR")
        print("=" * 65)
        print("1. Enter instructions interactively")
        print("2. Run the sample program")
        print("3. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            run_analysis(read_interactive_program())
        elif choice == "2":
            lines = SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
            print(f"Sample loaded from {SAMPLE_PATH.name}:")
            for line in lines:
                print(f"  {line}")
            run_analysis(lines)
        elif choice == "3":
            print("Goodbye.")
            return
        else:
            print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
