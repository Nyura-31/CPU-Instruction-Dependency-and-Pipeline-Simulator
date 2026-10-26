# CPU Lab Instruction Dependency and Pipeline Simulator

A beginner-friendly terminal project that combines three CSE concepts:

- **FLAT:** an explicitly implemented Deterministic Finite Automaton (DFA) validates each instruction.
- **DAA:** a register dependency graph is ordered using Kahn's topological sorting algorithm.
- **COA:** a five-stage CPU pipeline is simulated cycle by cycle, including dependency stalls.

The command-line application and core algorithms use only the Python standard library. The optional web dashboard uses Streamlit, listed in `requirements.txt`.

## How the three subjects connect

FLAT's DFA first checks that each assembly-like instruction follows the language grammar. DAA then turns the accepted instructions into a dependency graph and uses topological sorting to choose a valid order. COA uses that computed order to simulate the five pipeline stages, including stalls when an input register is not ready. The longest-path rule only guides choices between instructions that are already ready; it does not bypass the dependency checks.

## Run it

From this project directory, use Python 3.10 or later:

```text
python main.py
```

Choose `1` to type instructions one per line, ending with a blank line. Choose `2` to run `sample_programs/sample.asm`; choose `3` to exit. The report prints validation results, the adjacency list, the sorted order, a pipeline timing table, and performance metrics. If any instruction is invalid, it reports the DFA errors and stops before scheduling.

## Run the Streamlit dashboard

Create and activate a virtual environment, then install the dashboard dependency:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The dashboard starts on the Overview page. Use the sidebar to open the Instruction Editor, load the sample, and run analysis. The six pages use the existing validator, dependency graph, Kahn sorter, and pipeline simulator. To use the terminal app instead, continue to run `python main.py`.

## Instruction language and DFA

Registers are `R0` through `R7`; decimal memory addresses are `0` through `9999`. Opcode and register letter case is accepted without distinction. Commas separate operands; whitespace may surround tokens.

```text
ALU    ::= (ADD | SUB | MUL) REGISTER , REGISTER , REGISTER
LOAD   ::= LOAD REGISTER , MEMORY
STORE  ::= STORE MEMORY , REGISTER
REGISTER ::= R0 | R1 | ... | R7
MEMORY ::= [REGISTER] | [DECIMAL_ADDRESS]
```

Examples: `ADD R1, R2, R3`, `LOAD R1, [R2]`, and `STORE [100], R1`.

`dfa_validator.py` tokenizes each line into symbols such as `ADD`, `REGISTER`, `COMMA`, and `MEMORY`. `TRANSITIONS` defines the DFA transition table, `START` is the start state, and `ACCEPT_ALU`, `ACCEPT_LOAD`, and `ACCEPT_STORE` are accepting states. The validator applies the transition function to every symbol and rejects the line if a transition is missing or the final state is not accepting. The syntax check does not use regular expressions. Diagnostics identify unknown opcodes, malformed operands, unexpected symbols, or incomplete instructions.

## Dependency analysis and topological ordering

`dependency_graph.py` records registers read and written by each instruction. It adds a directed edge from an earlier instruction to a later one for:

- **RAW:** read after write (the later instruction needs the earlier result).
- **WAR:** write after read (the later write must not move before the earlier read).
- **WAW:** write after write (the writes must retain their order).

Adding all three hazard types preserves the program's register behavior while allowing independent instructions to move. The graph is displayed as an adjacency list. `topological_sort.py` uses Kahn's algorithm: it repeatedly chooses a ready instruction (one whose dependencies have already been handled) and removes its outgoing edges. It calculates each instruction's **longest remaining dependency path** from the graph, measured in edges. Among ready instructions, it selects the one with the longest path; equal path lengths use the lower instruction ID. This priority only chooses among ready nodes: it never removes or changes a dependency edge. A first Kahn pass gives a valid order for calculating path lengths from the end of the graph; a second Kahn pass applies the priorities. A cycle is reported if Kahn's algorithm cannot output every node. Building the graph takes **O(n²)** time for `n` instructions; the two priority-sort passes take **O((V + E) log V)** overall, where `V` is the number of instructions and `E` is the number of dependency edges.

Topological sorting answers **which orders are valid** under the dependencies. The longest-path rule is a **scheduling heuristic** for choosing among currently ready instructions. It can help keep a long dependency chain moving, but it does not guarantee an optimal schedule or the fastest pipeline result.

## Pipeline model and performance assumptions

`pipeline_simulator.py` models **IF → ID → EX → MEM → WB**, with each stage taking one cycle. It schedules instructions in the topological order. For a register dependency, the consumer occupies ID while waiting until the producer's WB cycle. The register file is assumed to write before decode reads in the same cycle, so ID may coincide with the producer's WB. No forwarding paths are modeled. When ID stalls, the following instruction is held in IF until ID becomes available. In the table, `ID*` marks cycles ID is waiting on a dependency and `IF*` marks a fetched instruction held behind a busy ID stage; `-` means that instruction is not in a stage that cycle.

The sequential baseline is explicitly a non-overlapped model: every instruction runs all five stages alone, so it costs `5 × instruction count` cycles. Pipeline cycles include fill, drain, and dependency stalls. Throughput is `instruction count / pipeline cycles`, in instructions per cycle. Speedup is `sequential baseline cycles / pipeline cycles`. These metrics describe this model; they do not guarantee that pipelining is faster for every program. For zero instructions, both cycle counts and both ratios are zero.

## Sample program

`sample_programs/sample.asm` puts an independent `SUB` before a dependent chain in the input:

```text
SUB R6, R7, R0
ADD R1, R2, R3
MUL R4, R1, R5
STORE [100], R4
```

The dependency edges are `I2 → I3` (`MUL` reads `R1` produced by `ADD`) and `I3 → I4` (`STORE` reads `R4` produced by `MUL`). Independent `I1` has no edges. The original order is `I1, I2, I3, I4`. The longest-path priorities for I1 through I4 are 0, 2, 1, and 0 edges, so Kahn's algorithm chooses `I2` and `I3` before independent `I1`. The resulting order, `I2, I3, I1, I4`, is valid because both dependency edges still point forward. `main.py` passes this computed order directly to the pipeline simulator; the output is not rearranged for display.

Verified terminal results for this sample:

```text
Dependency edges: 2
Original order: I1, I2, I3, I4
Topological order: I2, I3, I1, I4
Pipeline cycles: 11
Sequential baseline cycles: 20
Throughput: 0.364 instructions/cycle
Speedup: 1.818x
```

The timing table is printed by the program and shows each instruction's IF, ID, EX, MEM, and WB cycle. `I3` waits for `I2` to write back before reading `R1`, and `I4` waits for `I3` to write back before reading `R4`. The cycle results use the documented assumption that WB writes before ID reads in the same cycle. The heuristic does not promise fewer cycles than another valid order.

## Project files

- `app.py` — Streamlit dashboard entry point and presentation layer.
- `requirements.txt` — Streamlit dependency for the dashboard.
- `main.py` — menu, terminal output, and end-to-end workflow.
- `dfa_validator.py` — instruction model, tokenizer, DFA transitions, and syntax validation.
- `dependency_graph.py` — register hazards and adjacency-list construction.
- `topological_sort.py` — deterministic Kahn topological sort and cycle detection.
- `pipeline_simulator.py` — stage timing, stalls, and performance calculations.
- `sample_programs/sample.asm` — ready-to-run demonstration.
- `tests/test_simulator.py` — standard-library automated tests.

## Run tests

```text
python -m unittest discover -s tests -v
```

The verified suite contains 13 tests for valid and invalid syntax, missing operands and unknown opcodes, register hazards, deterministic ordering, cycle detection, stage progression, dependency stalls, the full sample timing table, performance metrics, and empty input. Expected summary:

```text
Ran 13 tests
OK
```

The web app does not run these tests in the browser. Run the command above locally from the repository directory.

## Deploy to Streamlit Community Cloud

The configured GitHub remote is [Nyura-31/CPU-Instruction-Dependency-and-Pipeline-Simulator](https://github.com/Nyura-31/CPU-Instruction-Dependency-and-Pipeline-Simulator). To deploy:

1. Push the project, including `app.py`, `requirements.txt`, and `sample_programs/sample.asm`, to the GitHub branch you want to deploy.
2. In Streamlit Community Cloud, create a new app and connect that repository.
3. Select the repository, branch, and `app.py` as the main file.
4. Deploy. Community Cloud installs Streamlit from `requirements.txt`; the sample is loaded relative to `app.py`, so it does not depend on the server's working directory.

Deployed CPU Lab Application Link: 
https://cpu-lab-instruction-dependency-and-pipeline-simulator.streamlit.app/

## Limitations

This is a teaching model, not a complete ISA or hardware simulator. It supports only five opcodes and eight registers, has no branch/control hazards, models memory references only as simple addresses or base registers, assumes fixed one-cycle stages, and does not model forwarding or structural hazards. The graph's ordering is dependency-safe for this register-only language; memory ordering between `LOAD` and `STORE` is not analyzed.
