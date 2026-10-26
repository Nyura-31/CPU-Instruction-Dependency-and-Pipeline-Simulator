"""Streamlit dashboard for the CPU instruction dependency pipeline simulator."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import streamlit as st

from dependency_graph import build_dependency_graph
from dfa_validator import ACCEPTING_STATES, TRANSITIONS, Instruction, validate_instruction, validate_program
from pipeline_simulator import performance, simulate_pipeline
from topological_sort import topological_sort


PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = PROJECT_DIR / "sample_programs" / "sample.asm"
PAGES = (
    "Overview",
    "Instruction Editor",
    "DFA Validation (FLAT)",
    "Dependency Analysis (DAA)",
    "Pipeline Simulator (COA)",
    "Testing & About",
)


def _read_sample() -> str:
    """Load the bundled example relative to this file, not the working folder."""
    return SAMPLE_FILE.read_text(encoding="utf-8")


def _load_sample_callback() -> None:
    try:
        st.session_state.program_text = _read_sample()
        st.session_state.analysis_snapshot = None
        st.session_state.flash_message = ("success", "Bundled sample loaded into the editor.")
    except OSError:
        st.session_state.flash_message = (
            "error",
            "The bundled sample file could not be read. Check sample_programs/sample.asm.",
        )


def _analyze_program(source_text: str) -> dict[str, Any]:
    """Run the existing validator, graph, sorter, and pipeline in sequence."""
    lines = source_text.splitlines()
    instructions, errors = validate_program(lines)
    result: dict[str, Any] = {
        "source_text": source_text,
        "instructions": instructions,
        "errors": errors,
        "input_count": sum(bool(line.strip()) for line in lines),
        "valid": not errors,
        "graph": {},
        "order": [],
        "rows": [],
        "cycles": None,
        "metrics": None,
        "analysis_error": None,
    }
    if errors:
        return result
    if not instructions:
        result["cycles"] = 0
        result["metrics"] = performance(0, 0)
        return result

    try:
        graph = build_dependency_graph(instructions)
        order = topological_sort(graph)
        rows, cycles, _schedule = simulate_pipeline(instructions, order)
        result.update(
            graph=graph,
            order=order,
            rows=rows,
            cycles=cycles,
            metrics=performance(len(instructions), cycles),
        )
    except (ValueError, KeyError) as error:
        result["analysis_error"] = str(error)
    return result


def _current_analysis() -> dict[str, Any] | None:
    snapshot = st.session_state.analysis_snapshot
    if snapshot is None:
        return None
    if snapshot["source_text"] != st.session_state.program_text:
        return None
    return snapshot


def _show_stale_notice() -> None:
    if st.session_state.analysis_snapshot is not None and _current_analysis() is None:
        st.warning("The editor contents changed after the last analysis. Run analysis again to refresh these results.")


def _render_instruction_row(index: int, text: str, accepted: bool, diagnostic: str = "") -> None:
    state_class = "accepted" if accepted else "rejected"
    status = "ACCEPT" if accepted else "REJECT"
    diagnostic_html = f'<small>{html.escape(diagnostic)}</small>' if diagnostic else ""
    st.markdown(
        f"""
        <div class="instruction-row">
          <span class="instruction-id">I{index}</span>
          <code>{html.escape(text)}</code>
          <span class="status-pill {state_class}">{status}</span>
          {diagnostic_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_errors(errors: list[tuple[int, str]]) -> None:
    for index, message in errors:
        st.error(f"I{index}: {message}")


def _render_metrics(analysis: dict[str, Any] | None) -> None:
    if analysis is None:
        values = ["—"] * 6
    else:
        values = [str(analysis["input_count"]), str(len(analysis["instructions"]))]
        if analysis["valid"] and analysis["analysis_error"] is None:
            edge_count = sum(len(targets) for targets in analysis["graph"].values())
            metrics = analysis["metrics"]
            values.extend(
                [
                    str(edge_count),
                    str(metrics["pipeline_cycles"]),
                    str(metrics["sequential_cycles"]),
                    f'{metrics["speedup"]:.3f}x',
                ]
            )
        else:
            values.extend(["—"] * 4)

    labels = (
        "Instructions",
        "Valid instructions",
        "Dependency edges",
        "Pipeline cycles",
        "Sequential baseline",
        "Speedup",
    )
    for row_start in (0, 3):
        columns = st.columns(3)
        for column, label, value in zip(
            columns, labels[row_start:row_start + 3], values[row_start:row_start + 3]
        ):
            with column:
                st.metric(label, value)


def _graphviz_source(analysis: dict[str, Any]) -> str:
    instructions = {item.index: item for item in analysis["instructions"]}
    lines = [
        "digraph Dependencies {",
        '  graph [rankdir=LR, bgcolor="transparent", nodesep=0.45, ranksep=0.65];',
        '  node [shape=box, style="rounded,filled", fillcolor="#EAF2FF", color="#89A9D5", fontname="sans-serif"];',
        '  edge [color="#5478AA", penwidth=1.6, arrowsize=0.75];',
    ]
    for instruction in analysis["instructions"]:
        label = f"I{instruction.index}\n{instruction.text}"
        lines.append(f"  I{instruction.index} [label={json.dumps(label)}];")
    for source, targets in analysis["graph"].items():
        for target in targets:
            lines.append(f"  I{source} -> I{target};")
    lines.append("}")
    return "\n".join(lines)


def _page_header(title: str, description: str) -> None:
    st.markdown(f"## {title}")
    st.markdown(f'<p class="page-description">{html.escape(description)}</p>', unsafe_allow_html=True)


def _render_overview() -> None:
    _page_header("Overview", "A compact lab for following instructions from syntax to execution.")
    analysis = _current_analysis()
    if analysis is None:
        st.info("No current analysis yet. Load the sample or enter instructions, then run analysis in the editor.")
        _render_metrics(None)
    else:
        _render_metrics(analysis)
        if not analysis["valid"]:
            st.warning("The current program contains rejected instructions. Dependency scheduling and pipeline simulation were skipped.")
        elif analysis["analysis_error"]:
            st.error(f'Analysis could not continue: {analysis["analysis_error"]}')

    st.markdown('<div class="section-card"><h3>Project workflow</h3><div class="workflow">'
                '<span>Instruction input</span><b>→</b><span>DFA validation</span><b>→</b>'
                '<span>Dependency graph</span><b>→</b><span>Topological scheduling</span><b>→</b>'
                '<span>Pipeline simulation</span></div></div>', unsafe_allow_html=True)
    st.markdown("### Three concepts, one execution path")
    cols = st.columns(3)
    cards = [
        ("FLAT", "DFA validation", "The explicit automaton accepts supported instruction forms and explains rejected syntax."),
        ("DAA", "Topological scheduling", "Kahn’s algorithm respects register hazards and prioritizes the longest remaining dependency path."),
        ("COA", "Five-stage pipeline", "The simulator shows fetch, decode, execute, memory, write-back, and dependency stalls."),
    ]
    for col, (tag, title, copy) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div class="concept-card"><span class="concept-tag">{tag}</span>'
                f'<h4>{title}</h4><p>{copy}</p></div>',
                unsafe_allow_html=True,
            )

    st.markdown("### Start with the bundled example")
    st.caption("The sample includes an independent instruction and a dependent ADD → MUL → STORE chain.")
    st.button("Load sample program", type="primary", on_click=_load_sample_callback, key="overview_load_sample")


def _render_editor() -> None:
    _page_header("Instruction Editor", "Enter the program in source order. The editor never silently rewrites your text.")
    st.markdown("Use one instruction per line. Blank lines are ignored by the existing validator. Registers are R0–R7; memory addresses are `[R0]`–`[R7]` or decimal `[0]`–`[9999]`.")
    st.caption("Examples: `ADD R1, R2, R3` · `LOAD R1, [R2]` · `STORE [100], R1`")
    controls = st.columns([1, 1, 4])
    with controls[0]:
        st.button("Load sample", on_click=_load_sample_callback, key="editor_load_sample")
    with controls[1]:
        st.button("Reset to sample", on_click=_load_sample_callback, key="editor_reset_sample")

    with st.form("instruction_editor_form", clear_on_submit=False):
        st.text_area(
            "Assembly-like instructions",
            key="program_text",
            height=230,
            placeholder="ADD R1, R2, R3\nMUL R4, R1, R5",
            help="Input order and spelling are preserved. Run analysis to validate and schedule the current text.",
        )
        submitted = st.form_submit_button("Run analysis", type="primary", use_container_width=True)

    if submitted:
        try:
            st.session_state.analysis_snapshot = _analyze_program(st.session_state.program_text)
            st.session_state.flash_message = ("success", "Analysis updated for the current editor contents.")
            st.rerun()
        except Exception:
            st.error("Analysis could not be completed. Check the input and try again.")

    source = st.session_state.program_text
    instructions, errors = validate_program(source.splitlines())
    st.markdown("### Original instruction sequence")
    if not source.strip():
        st.info("The program is empty. Load the sample or enter an instruction above.")
    else:
        instruction_by_id = {item.index: item for item in instructions}
        error_by_id = dict(errors)
        index = 0
        for line in source.splitlines():
            if not line.strip():
                continue
            index += 1
            if index in instruction_by_id:
                _render_instruction_row(index, line, True)
            else:
                _render_instruction_row(index, line, False, error_by_id.get(index, "Rejected by the DFA."))
    if errors:
        st.markdown("### Validation feedback")
        _render_errors(errors)


def _render_dfa() -> None:
    _page_header("DFA Validation · FLAT", "The UI calls the project’s explicit DFA validator; it does not substitute a regular expression.")
    source = st.session_state.program_text
    instructions, errors = validate_program(source.splitlines())
    st.markdown("### Current program")
    if not source.strip():
        st.info("No instructions to validate. Load the sample or enter instructions in the editor.")
    else:
        valid_by_id = {item.index: item for item in instructions}
        error_by_id = dict(errors)
        instruction_id = 0
        for line in source.splitlines():
            if not line.strip():
                continue
            instruction_id += 1
            if instruction_id in valid_by_id:
                _render_instruction_row(instruction_id, line, True)
            else:
                _render_instruction_row(
                    instruction_id, line, False, error_by_id.get(instruction_id, "Rejected by the DFA.")
                )

    st.markdown("### Invalid-input demonstration")
    malformed = "ADD R1, R2"
    _parsed, diagnostic = validate_instruction(malformed)
    _render_instruction_row(1, malformed, False, diagnostic)
    st.caption("This demonstration uses validate_instruction() from dfa_validator.py. A rejected program is never scheduled.")

    with st.expander("Supported grammar and DFA details", expanded=False):
        st.code(
            "ALU ::= (ADD | SUB | MUL) REGISTER , REGISTER , REGISTER\n"
            "LOAD ::= LOAD REGISTER , MEMORY\n"
            "STORE ::= STORE MEMORY , REGISTER\n"
            "REGISTER ::= R0 | R1 | ... | R7\n"
            "MEMORY ::= [REGISTER] | [DECIMAL_ADDRESS 0..9999]",
            language="text",
        )
        st.markdown(
            "The start state is `START`. Each token is classified and passed through the transition table. "
            "An instruction is accepted only if its final state is one of the accepting states."
        )
        st.write(f"**Start state:** `START`  ·  **Accepting states:** {', '.join(sorted(ACCEPTING_STATES))}")
        transition_rows = [
            {"Current state": state, "Input symbol": symbol, "Next state": next_state}
            for state, transitions in TRANSITIONS.items()
            for symbol, next_state in transitions.items()
        ]
        st.dataframe(transition_rows, hide_index=True, use_container_width=True)


def _analysis_needed() -> dict[str, Any] | None:
    analysis = _current_analysis()
    if analysis is None:
        _show_stale_notice()
        st.info("Run analysis from Instruction Editor to see results for the current text.")
        return None
    if not analysis["valid"]:
        st.error("Scheduling stopped because DFA validation rejected one or more instructions.")
        _render_errors(analysis["errors"])
        return None
    if analysis["analysis_error"]:
        st.error(f'Analysis could not continue: {analysis["analysis_error"]}')
        return None
    if not analysis["instructions"]:
        st.info("The current program has no instructions. Add instructions in the editor to build a graph or pipeline.")
        return None
    return analysis


def _render_dependencies() -> None:
    _page_header("Dependency Analysis · DAA", "Follow real register-hazard edges and inspect the order returned by Kahn’s algorithm.")
    analysis = _analysis_needed()
    if analysis is None:
        return

    st.markdown("### Original instruction order")
    st.write("  →  ".join(f'I{item.index}: {item.text}' for item in analysis["instructions"]))
    graph = analysis["graph"]
    edge_count = sum(len(targets) for targets in graph.values())
    st.markdown("### Dependency graph")
    if edge_count:
        try:
            st.graphviz_chart(_graphviz_source(analysis), use_container_width=True)
        except Exception:
            st.info("The graph image is unavailable in this environment; use the adjacency list below.")
    else:
        st.info("No register dependency edges were found; all instructions are independent in this graph.")

    edge_rows = [
        {"Instruction": f"I{source}", "Depends on later instruction": f"I{target}"}
        for source, targets in graph.items()
        for target in targets
    ]
    if edge_rows:
        st.dataframe(edge_rows, hide_index=True, use_container_width=True)
    adjacency = [
        {"Instruction": f"I{node}", "Outgoing dependency edges": ", ".join(f"I{x}" for x in targets) or "None"}
        for node, targets in graph.items()
    ]
    with st.expander("Adjacency list", expanded=True):
        st.dataframe(adjacency, hide_index=True, use_container_width=True)

    st.markdown("### Topological execution order")
    order = analysis["order"]
    positions = {instruction_id: place for place, instruction_id in enumerate(order)}
    reverse_edges = {
        node: [source for source, targets in graph.items() if node in targets]
        for node in graph
    }
    order_rows = []
    instructions_by_id = {item.index: item for item in analysis["instructions"]}
    for place, node in enumerate(order, start=1):
        predecessors = reverse_edges[node]
        order_rows.append(
            {
                "Order": place,
                "Instruction": f"I{node}",
                "Code": instructions_by_id[node].text,
                "Required predecessors": ", ".join(f"I{x}" for x in predecessors) or "None",
                "Ready at selection": all(positions[parent] < positions[node] for parent in predecessors),
            }
        )
    st.dataframe(order_rows, hide_index=True, use_container_width=True)
    st.success("Valid order: every dependency edge points from an earlier scheduled instruction to a later one.")
    st.caption(
        "Longest remaining path is only a tie-break heuristic among ready instructions. "
        "It does not guarantee an optimal or fastest schedule."
    )
    st.caption("The current dependency API returns adjacency lists, not hazard labels or per-node path priorities; this view does not infer those values.")


def _pipeline_table_html(analysis: dict[str, Any], selected_cycle: int) -> str:
    instructions = analysis["instructions"]
    headers = "".join(
        f'<th class="{"selected-cycle" if cycle == selected_cycle else ""}">C{cycle}</th>'
        for cycle in range(1, analysis["cycles"] + 1)
    )
    body_rows = []
    for instruction, stages in zip(instructions, analysis["rows"]):
        cells = []
        for cycle, stage in enumerate(stages, start=1):
            safe_stage = html.escape(stage)
            stage_class = "empty" if stage == "-" else "stage " + stage.lower().replace("*", "-stall")
            selected = " selected-cycle" if cycle == selected_cycle else ""
            cells.append(f'<td class="{stage_class}{selected}">{safe_stage}</td>')
        body_rows.append(
            f'<tr><th class="instruction-label">I{instruction.index}<br>'
            f'<code>{html.escape(instruction.text)}</code></th>{"".join(cells)}</tr>'
        )
    return (
        '<div class="pipeline-scroll"><table class="pipeline-table"><thead><tr>'
        '<th class="instruction-label">Instruction · source ID</th>' + headers
        + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table></div>"
    )


def _render_pipeline() -> None:
    _page_header("Pipeline Simulator · COA", "Inspect the cycle-by-cycle timing returned by the existing five-stage simulator.")
    analysis = _analysis_needed()
    if analysis is None:
        return
    metrics = analysis["metrics"]
    st.caption("Pipeline execution follows the computed topological order: " + " → ".join(f'I{x}' for x in analysis["order"]))

    cols = st.columns(4)
    for column, label, value in zip(
        cols,
        ("Pipeline cycles", "Sequential baseline", "Throughput", "Speedup"),
        (
            str(metrics["pipeline_cycles"]),
            str(metrics["sequential_cycles"]),
            f'{metrics["throughput"]:.3f} instr/cycle',
            f'{metrics["speedup"]:.3f}x',
        ),
    ):
        with column:
            st.metric(label, value)

    if analysis["cycles"]:
        selected_cycle = st.select_slider(
            "Highlight a clock cycle",
            options=list(range(1, analysis["cycles"] + 1)),
            value=1,
            help="The selected column is highlighted in the timing table.",
        )
        st.markdown(_pipeline_table_html(analysis, selected_cycle), unsafe_allow_html=True)
        st.markdown(
            '<div class="stage-legend">'
            '<span><b>IF</b> Fetch</span><span><b>ID</b> Decode</span><span><b>EX</b> Execute</span>'
            '<span><b>MEM</b> Memory</span><span><b>WB</b> Write back</span>'
            '<span><b>ID*</b> Decode stall</span><span><b>IF*</b> Held fetch</span><span><b>–</b> Empty</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No pipeline cycles are needed for an empty program.")

    with st.expander("Pipeline and performance assumptions", expanded=False):
        st.markdown(
            "- Five stages: IF, ID, EX, MEM, and WB; each stage takes one cycle.\n"
            "- No forwarding paths are modeled.\n"
            "- WB writes before ID reads in the same cycle, so same-cycle WB/ID is allowed.\n"
            "- A dependent instruction waits in ID until its producer reaches WB.\n"
            "- The next instruction is held in IF while decode is stalled.\n"
            "- The sequential baseline is five non-overlapped stages per instruction.\n"
            "- Speedup is baseline cycles divided by pipeline cycles; it is specific to this model."
        )


def _render_about() -> None:
    _page_header("Testing & About", "Project architecture, assumptions, and local verification instructions.")
    st.markdown("### Academic concepts")
    st.markdown(
        "- **FLAT:** `dfa_validator.py` defines the token classes, DFA transition table, start state, and accepting states.\n"
        "- **DAA:** `dependency_graph.py` builds RAW/WAR/WAW edges; `topological_sort.py` runs Kahn’s algorithm with a graph-derived longest-path priority.\n"
        "- **COA:** `pipeline_simulator.py` models IF, ID, EX, MEM, and WB with dependency stalls and held fetch cycles.\n"
        "- **Interface:** `app.py` presents those existing calculations; `main.py` remains the terminal application."
    )
    st.markdown("### Supported instructions")
    st.code("ADD / SUB / MUL  Rdest, Rsrc1, Rsrc2\nLOAD               Rdest, [Rbase] or [address]\nSTORE              [Rbase] or [address], Rsrc", language="text")
    st.markdown("### Tests")
    st.code("python -m unittest discover -s tests -v", language="powershell")
    st.caption("Run this command from the project directory. The deployed website does not execute the local unittest suite.")
    st.markdown("### Limitations")
    st.markdown(
        "This is a teaching model with five supported opcodes and eight registers. It has no branch/control hazards, "
        "forwarding, structural hazard model, or memory ordering analysis. The longest-path tie-break is a heuristic, "
        "not an optimal scheduling algorithm."
    )
    st.markdown("### Source repository")
    st.markdown("[GitHub repository](https://github.com/Nyura-31/CPU-Instruction-Dependency-and-Pipeline-Simulator)")


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root { --navy: #14243a; --blue: #3569a8; --ink: #17263a; --muted: #607086; }
        [data-testid="stAppViewContainer"] { background: #f5f8fc; }
        [data-testid="stHeader"] { background: rgba(245,248,252,.88); }
        [data-testid="stSidebar"] { background: #14243a; }
        [data-testid="stSidebar"] * { color: #e8eef7; }
        [data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius: 9px; padding: .32rem .4rem; }
        [data-testid="stSidebar"] [aria-checked="true"] { background: #263e5c; }
        .block-container { padding-top: 1.8rem; padding-bottom: 2.5rem; max-width: 1500px; }
        h1, h2, h3, h4 { color: var(--ink); letter-spacing: -.02em; }
        .page-description { color: var(--muted); margin-top: -.65rem; margin-bottom: 1.25rem; }
        .brand-card { padding: 1.05rem 1.1rem; border-radius: 16px; background: linear-gradient(120deg,#fff,#eef5ff); border: 1px solid #dce7f5; margin-bottom: 1.25rem; }
        .brand-title { font-size: 1.5rem; font-weight: 750; color: #17263a; margin: 0; }
        .brand-subtitle { font-size: .88rem; color: #64758b; margin: .15rem 0 0; }
        .concept-tags { display:flex; gap:.45rem; margin-top:.75rem; }
        .concept-tags span, .concept-tag { display:inline-block; border-radius:999px; padding:.2rem .6rem; background:#e7f0ff; color:#285a96; font-size:.72rem; font-weight:700; letter-spacing:.04em; }
        .section-card, .concept-card { background:#fff; border:1px solid #e1e8f0; border-radius:15px; padding:1rem 1.1rem; box-shadow:0 3px 12px rgba(28,49,77,.035); }
        .section-card h3 { margin:0 0 .8rem; font-size:1.05rem; }
        .concept-card { min-height:145px; }
        .concept-card h4 { margin:.6rem 0 .35rem; font-size:1rem; }
        .concept-card p { color:#607086; font-size:.88rem; line-height:1.5; }
        .workflow { display:flex; flex-wrap:wrap; gap:.55rem; align-items:center; color:#35506f; font-size:.84rem; }
        .workflow span { background:#f1f6fd; border:1px solid #e0eafa; border-radius:999px; padding:.4rem .65rem; }
        .workflow b { color:#7d93ad; }
        [data-testid="stMetric"] { background:white; border:1px solid #e0e8f1; border-radius:14px; padding:.9rem 1rem; box-shadow:0 3px 12px rgba(28,49,77,.035); }
        .instruction-row { display:grid; grid-template-columns:3.4rem minmax(12rem,2fr) auto minmax(12rem,1.3fr); gap:.75rem; align-items:center; background:white; border:1px solid #e3eaf2; border-radius:11px; padding:.65rem .8rem; margin:.4rem 0; }
        .instruction-row code { color:#263b55; white-space:pre-wrap; overflow-wrap:anywhere; }
        .instruction-id { color:#71839a; font-size:.76rem; font-weight:700; }
        .instruction-row small { color:#a33838; }
        .status-pill { border-radius:999px; padding:.2rem .6rem; font-size:.7rem; font-weight:750; letter-spacing:.03em; }
        .status-pill.accepted { background:#e4f5ed; color:#1c7650; }
        .status-pill.rejected { background:#fde9e8; color:#a33232; }
        .pipeline-scroll { overflow-x:auto; background:#fff; border:1px solid #dce5ef; border-radius:13px; padding:.5rem; }
        .pipeline-table { border-collapse:separate; border-spacing:3px; min-width:max-content; width:100%; font-family:system-ui,sans-serif; }
        .pipeline-table th,.pipeline-table td { text-align:center; padding:.48rem .55rem; border-radius:7px; font-size:.8rem; }
        .pipeline-table thead th { background:#eaf0f7; color:#50637a; font-weight:700; }
        .pipeline-table .instruction-label { text-align:left; min-width:13rem; background:#f3f6fa; color:#263b55; }
        .pipeline-table .instruction-label code { color:#52657b; white-space:normal; }
        .pipeline-table .empty { background:#f8fafc; color:#bdc6d2; }
        .pipeline-table .stage { font-weight:750; color:#244564; background:#e9f2ff; }
        .pipeline-table .stage.id-stall { color:#895a10; background:#fff1ce; }
        .pipeline-table .stage.if-stall { color:#5d648d; background:#eeedff; }
        .pipeline-table .selected-cycle { outline:2px solid #3977c4; outline-offset:-2px; }
        .stage-legend { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.75rem; }
        .stage-legend span { padding:.3rem .55rem; border-radius:8px; background:white; border:1px solid #e0e8f1; color:#5b6c81; font-size:.78rem; }
        .stage-legend b { color:#2d5684; margin-right:.25rem; }
        @media(max-width:760px) { .instruction-row { grid-template-columns:2.5rem 1fr auto; } .instruction-row small { grid-column:2/4; } .workflow { align-items:flex-start; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="CPU Lab | Instruction Pipeline Simulator", page_icon="⚙️", layout="wide")
    for key, value in (
        ("program_text", ""),
        ("analysis_snapshot", None),
        ("active_page", "Overview"),
        ("flash_message", None),
    ):
        if key not in st.session_state:
            st.session_state[key] = value

    _apply_styles()
    st.markdown(
        '<div class="brand-card"><p class="brand-title">CPU Lab</p>'
        '<p class="brand-subtitle">Instruction Dependency &amp; Pipeline Simulator</p>'
        '<div class="concept-tags"><span>FLAT · DFA</span><span>DAA · TOPOLOGICAL SORT</span><span>COA · PIPELINING</span></div></div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### CPU Lab")
        st.caption("Academic micro-project")
        page = st.radio("Navigate", PAGES, key="active_page", label_visibility="collapsed")
        st.markdown("---")
        st.caption("FLAT  ·  DAA  ·  COA")

    flash = st.session_state.flash_message
    if flash:
        kind, message = flash
        getattr(st, kind)(message)
        st.session_state.flash_message = None

    if page == "Overview":
        _render_overview()
    elif page == "Instruction Editor":
        _render_editor()
    elif page == "DFA Validation (FLAT)":
        _render_dfa()
    elif page == "Dependency Analysis (DAA)":
        _render_dependencies()
    elif page == "Pipeline Simulator (COA)":
        _render_pipeline()
    else:
        _render_about()


if __name__ == "__main__":
    main()
