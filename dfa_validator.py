"""A small explicit DFA for the simulator's assembly-like instruction language."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instruction:
    """A parsed instruction, retaining its source text and operand fields."""

    index: int
    text: str
    opcode: str
    destination: str | None = None
    source1: str | None = None
    source2: str | None = None

    @property
    def registers_read(self) -> set[str]:
        if self.opcode in {"ADD", "SUB", "MUL"}:
            return {self.source1 or "", self.source2 or ""}
        if self.opcode == "STORE":
            registers = {self.source1 or ""}
            if (self.source2 or "").startswith("R"):
                registers.add(self.source2 or "")
            return registers
        if self.opcode == "LOAD" and (self.source1 or "").startswith("R"):
            return {self.source1 or ""}
        return set()

    @property
    def registers_written(self) -> set[str]:
        if self.opcode in {"ADD", "SUB", "MUL", "LOAD"}:
            return {self.destination or ""}
        return set()


# The DFA's input alphabet consists of token classes produced by classify_token.
# Memory references are one token, for example [R2] or [120].
TRANSITIONS: dict[str, dict[str, str]] = {
    "START": {"ADD": "ALU_DEST", "SUB": "ALU_DEST", "MUL": "ALU_DEST",
              "LOAD": "LOAD_DEST", "STORE": "STORE_ADDRESS"},
    "ALU_DEST": {"REGISTER": "ALU_COMMA_1"},
    "ALU_COMMA_1": {"COMMA": "ALU_SOURCE_1"},
    "ALU_SOURCE_1": {"REGISTER": "ALU_COMMA_2"},
    "ALU_COMMA_2": {"COMMA": "ALU_SOURCE_2"},
    "ALU_SOURCE_2": {"REGISTER": "ACCEPT_ALU"},
    "LOAD_DEST": {"REGISTER": "LOAD_COMMA"},
    "LOAD_COMMA": {"COMMA": "LOAD_ADDRESS"},
    "LOAD_ADDRESS": {"MEMORY": "ACCEPT_LOAD"},
    "STORE_ADDRESS": {"MEMORY": "STORE_COMMA"},
    "STORE_COMMA": {"COMMA": "STORE_SOURCE"},
    "STORE_SOURCE": {"REGISTER": "ACCEPT_STORE"},
}
ACCEPTING_STATES = {"ACCEPT_ALU", "ACCEPT_LOAD", "ACCEPT_STORE"}
OPCODE_STATES = {"START": "opcode"}


def tokenize(line: str) -> list[str]:
    """Split whitespace and commas while retaining commas as DFA symbols."""
    tokens: list[str] = []
    current = ""
    for character in line.strip():
        if character.isspace():
            if current:
                tokens.append(current)
                current = ""
        elif character == ",":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(",")
        else:
            current += character
    if current:
        tokens.append(current)
    return tokens


def classify_token(token: str) -> str:
    """Return the input symbol class using explicit character checks, not regex."""
    upper = token.upper()
    if upper in {"ADD", "SUB", "MUL", "LOAD", "STORE"}:
        return upper
    if token == ",":
        return "COMMA"
    if len(upper) >= 2 and upper[0] == "R" and all(ch.isdigit() for ch in upper[1:]):
        number = int(upper[1:])
        if 0 <= number <= 7:
            return "REGISTER"
        return "INVALID_REGISTER"
    if len(token) >= 3 and token[0] == "[" and token[-1] == "]":
        inside = token[1:-1].upper()
        if len(inside) >= 2 and inside[0] == "R" and all(ch.isdigit() for ch in inside[1:]):
            if int(inside[1:]) <= 7:
                return "MEMORY"
            return "INVALID_MEMORY"
        if inside and all(ch.isdigit() for ch in inside) and int(inside) <= 9999:
            return "MEMORY"
        return "INVALID_MEMORY"
    return "INVALID"


def validate_instruction(line: str, index: int = 1) -> tuple[Instruction | None, str]:
    """Run the token classes through the DFA and return a useful diagnostic."""
    tokens = tokenize(line)
    if not tokens:
        return None, "instruction is empty"

    state = "START"
    classes: list[str] = []
    for token in tokens:
        symbol = classify_token(token)
        classes.append(symbol)
        next_state = TRANSITIONS.get(state, {}).get(symbol)
        if next_state is None:
            if state == "START" and symbol == "INVALID":
                return None, f"unknown opcode or invalid opcode '{token}'"
            if symbol in {"INVALID_REGISTER", "INVALID_MEMORY", "INVALID"}:
                return None, f"malformed operand '{token}'"
            return None, f"unexpected '{token}' while DFA was in state {state}"
        state = next_state

    if state not in ACCEPTING_STATES:
        return None, f"incomplete instruction; DFA stopped in non-accepting state {state}"

    # The path through the DFA identifies the opcode and all grammar slots.
    opcode = tokens[0].upper()
    operands = [token.upper() for token in tokens[1:] if token != ","]
    if opcode in {"ADD", "SUB", "MUL"}:
        instruction = Instruction(index, line.strip(), opcode, operands[0], operands[1], operands[2])
    elif opcode == "LOAD":
        address = operands[1][1:-1]
        instruction = Instruction(index, line.strip(), opcode, operands[0], address, None)
    else:  # STORE [address], Rsrc
        address = operands[0][1:-1]
        instruction = Instruction(index, line.strip(), opcode, None, operands[1], address)
    return instruction, "accepted"


def validate_program(lines: list[str]) -> tuple[list[Instruction], list[tuple[int, str]]]:
    """Validate each nonblank line, returning accepted instructions and errors."""
    instructions: list[Instruction] = []
    errors: list[tuple[int, str]] = []
    source_index = 0
    for line in lines:
        if not line.strip():
            continue
        source_index += 1
        parsed, message = validate_instruction(line, source_index)
        if parsed is None:
            errors.append((source_index, message))
        else:
            instructions.append(parsed)
    return instructions, errors
