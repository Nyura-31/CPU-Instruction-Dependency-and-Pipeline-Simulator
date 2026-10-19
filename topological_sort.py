"""Deterministic Kahn topological sorting."""

import heapq


def _kahn_order(
    graph: dict[int, list[int]], priorities: dict[int, int]
) -> list[int]:
    """Run Kahn's algorithm, using priority then instruction ID for ready nodes."""
    indegree = {node: 0 for node in graph}
    for neighbors in graph.values():
        for neighbor in neighbors:
            indegree[neighbor] += 1

    # Negative priorities make heapq remove the highest priority first.
    ready = [(-priorities[node], node) for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for neighbor in sorted(graph[node]):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                heapq.heappush(ready, (-priorities[neighbor], neighbor))

    if len(order) != len(graph):
        raise ValueError("dependency graph contains a cycle; no topological ordering exists")
    return order


def topological_sort(graph: dict[int, list[int]]) -> list[int]:
    """Kahn sort prioritizing ready nodes on the longest remaining path.

    A path's length is its number of dependency edges. Equal path priorities
    are resolved by the lower instruction ID for reproducible output.
    """
    # Any topological order lets us calculate longest paths from the end back
    # toward the start. This first Kahn pass also detects cycles.
    initial_order = _kahn_order(graph, {node: 0 for node in graph})
    remaining_path = {node: 0 for node in graph}
    for node in reversed(initial_order):
        if graph[node]:
            remaining_path[node] = max(
                1 + remaining_path[neighbor] for neighbor in graph[node]
            )

    # Run Kahn again, now preferring ready instructions with more work below them.
    return _kahn_order(graph, remaining_path)
