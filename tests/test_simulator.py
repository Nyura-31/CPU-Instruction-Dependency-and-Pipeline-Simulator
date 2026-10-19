import unittest

from dependency_graph import build_dependency_graph
from dfa_validator import validate_instruction, validate_program
from pipeline_simulator import performance, simulate_pipeline
from topological_sort import topological_sort


class DfaTests(unittest.TestCase):
    def test_valid_instruction_forms(self):
        for line in ("ADD R1, R2, R3", "SUB R0,R7,R1", "MUL R4, R5, R6",
                     "LOAD R1, [R2]", "LOAD R1, [123]", "STORE [R2], R1", "STORE [123], R1"):
            with self.subTest(line=line):
                parsed, message = validate_instruction(line)
                self.assertIsNotNone(parsed)
                self.assertEqual(message, "accepted")

    def test_invalid_and_missing_operands(self):
        for line in ("ADD R1, R2", "ADD R8, R2, R3", "LOAD R1", "STORE [R1],",
                     "JMP R1", "ADD R1 R2, R3", "MUL R1, R2, XYZ", "LOAD R1, [R99]"):
            with self.subTest(line=line):
                parsed, message = validate_instruction(line)
                self.assertIsNone(parsed)
                self.assertNotEqual(message, "accepted")

    def test_program_validation_handles_empty_lines_and_keeps_rejections(self):
        instructions, errors = validate_program(["", "ADD R1, R2, R3", "BAD R1"])
        self.assertEqual(len(instructions), 1)
        self.assertEqual(len(errors), 1)


class DependencyTests(unittest.TestCase):
    def parse(self, lines):
        instructions, errors = validate_program(lines)
        self.assertEqual(errors, [])
        return instructions

    def test_register_dependencies_include_raw_war_and_waw(self):
        instructions = self.parse([
            "ADD R1, R2, R3",     # writes R1
            "MUL R4, R1, R5",     # RAW from I1
            "SUB R1, R6, R7",     # WAR and WAW with earlier operations
            "STORE [R4], R1",     # reads stored value and address base
        ])
        graph = build_dependency_graph(instructions)
        self.assertIn(2, graph[1])
        self.assertIn(3, graph[1])
        self.assertIn(4, graph[2])
        self.assertIn(4, graph[3])

    def test_topological_order_and_deterministic_tie_break(self):
        graph = {1: [3], 2: [], 3: []}
        self.assertEqual(topological_sort(graph), [1, 2, 3])

    def test_longest_remaining_path_is_prioritized_and_equal_paths_use_id(self):
        graph = {1: [], 2: [3], 3: [4], 4: []}
        expected = [2, 3, 1, 4]
        for _ in range(3):
            self.assertEqual(topological_sort(graph), expected)
        tied_graph = {1: [], 2: [], 3: []}
        self.assertEqual(topological_sort(tied_graph), [1, 2, 3])

    def test_reordered_sample_is_a_valid_topological_order(self):
        instructions, errors = validate_program([
            "SUB R6, R7, R0",
            "ADD R1, R2, R3",
            "MUL R4, R1, R5",
            "STORE [100], R4",
        ])
        self.assertEqual(errors, [])
        graph = build_dependency_graph(instructions)
        self.assertEqual(graph, {1: [], 2: [3], 3: [4], 4: []})

        order = topological_sort(graph)
        self.assertEqual(order, [2, 3, 1, 4])
        self.assertNotEqual(order, [instruction.index for instruction in instructions])
        position = {instruction_id: place for place, instruction_id in enumerate(order)}
        for source, targets in graph.items():
            for target in targets:
                self.assertLess(position[source], position[target])

    def test_cycle_detection(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            topological_sort({1: [2], 2: [1]})

    def test_empty_graph(self):
        self.assertEqual(topological_sort({}), [])


class PipelineTests(unittest.TestCase):
    def test_single_instruction_progresses_through_five_stages(self):
        instructions, errors = validate_program(["ADD R1, R2, R3"])
        self.assertEqual(errors, [])
        rows, cycles, _ = simulate_pipeline(instructions, [1])
        self.assertEqual(cycles, 5)
        self.assertEqual(rows[0], ["IF", "ID", "EX", "MEM", "WB"])

    def test_dependent_consumer_waits_for_writeback(self):
        instructions, _ = validate_program(["ADD R1, R2, R3", "MUL R4, R1, R5"])
        rows, cycles, schedule = simulate_pipeline(instructions, [1, 2])
        self.assertEqual(schedule[1]["WB"], schedule[2]["ID"])
        self.assertEqual(schedule[2]["ID_START"], 3)
        self.assertEqual(rows[1], ["-", "IF", "ID*", "ID*", "ID", "EX", "MEM", "WB"])
        self.assertEqual(cycles, 8)

    def test_sample_pipeline_table_and_metrics_use_topological_order(self):
        instructions, errors = validate_program([
            "SUB R6, R7, R0",
            "ADD R1, R2, R3",
            "MUL R4, R1, R5",
            "STORE [100], R4",
        ])
        self.assertEqual(errors, [])
        graph = build_dependency_graph(instructions)
        order = topological_sort(graph)
        self.assertEqual(order, [2, 3, 1, 4])
        rows, cycles, schedule = simulate_pipeline(instructions, order)
        self.assertEqual(cycles, 11)
        self.assertEqual(rows, [
            ["-", "-", "IF", "IF*", "IF*", "ID", "EX", "MEM", "WB", "-", "-"],
            ["IF", "ID", "EX", "MEM", "WB", "-", "-", "-", "-", "-", "-"],
            ["-", "IF", "ID*", "ID*", "ID", "EX", "MEM", "WB", "-", "-", "-"],
            ["-", "-", "-", "-", "-", "IF", "ID*", "ID", "EX", "MEM", "WB"],
        ])
        self.assertEqual(schedule[2]["WB"], 5)
        self.assertEqual(schedule[3]["ID"], 5)
        self.assertEqual(schedule[3]["ID_START"], 3)
        self.assertEqual(schedule[3]["WB"], 8)
        self.assertEqual(schedule[4]["ID"], 8)
        self.assertEqual(schedule[4]["WB"], 11)

        result = performance(4, cycles)
        self.assertEqual(result["sequential_cycles"], 20)
        self.assertAlmostEqual(result["throughput"], 4 / 11)
        self.assertAlmostEqual(result["speedup"], 20 / 11)

    def test_performance_and_zero_instruction_edge_case(self):
        self.assertEqual(performance(4, 8), {
            "instruction_count": 4, "pipeline_cycles": 8, "sequential_cycles": 20,
            "throughput": 0.5, "speedup": 2.5,
        })
        self.assertEqual(performance(0, 0)["speedup"], 0.0)
        self.assertEqual(performance(0, 0)["throughput"], 0.0)


if __name__ == "__main__":
    unittest.main()
