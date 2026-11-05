"""Network and spatial topology graph primitives."""

from itertools import pairwise
from math import isfinite
from typing import Self

from pydantic import Field, model_validator

from simulation_core.types import FrozenModel


class NetworkEdge(FrozenModel):
    """An edge between two nodes in a spatial or interaction graph."""

    source: str
    target: str
    weight: float = Field(default=1.0, gt=0)
    capacity: float | None = Field(default=None, ge=0)
    bidirectional: bool = True

    @model_validator(mode="after")
    def validate_finite(self) -> Self:
        if not isfinite(self.weight):
            raise ValueError("Edge weight must be finite")
        if self.capacity is not None and not isfinite(self.capacity):
            raise ValueError("Edge capacity must be finite")
        return self


class NetworkTopology(FrozenModel):
    """Immutable graph representing trade networks, spatial grids, or social ties."""

    nodes: tuple[str, ...] = Field(default_factory=tuple)
    edges: tuple[NetworkEdge, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_nodes_and_edges(self) -> Self:
        node_set = set(self.nodes)
        for edge in self.edges:
            if edge.source not in node_set or edge.target not in node_set:
                raise ValueError(
                    f"Edge ({edge.source}, {edge.target}) references unknown nodes"
                )
        return self

    def neighbors(self, node: str) -> tuple[str, ...]:
        if node not in self.nodes:
            raise ValueError(f"Unknown node: {node}")
        found = set()
        for edge in self.edges:
            if edge.source == node:
                found.add(edge.target)
            elif edge.bidirectional and edge.target == node:
                found.add(edge.source)
        return tuple(sorted(found))

    def degree(self, node: str) -> int:
        return len(self.neighbors(node))

    def has_edge(self, source: str, target: str) -> bool:
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                return True
            if edge.bidirectional and edge.source == target and edge.target == source:
                return True
        return False

    def are_connected(self, source: str, target: str) -> bool:
        return self.shortest_path(source, target) is not None

    def shortest_path(self, source: str, target: str) -> tuple[str, ...] | None:
        """Find the minimum-weight path from source to target using Dijkstra's algorithm."""
        if source not in self.nodes or target not in self.nodes:
            raise ValueError("Both source and target must belong to the topology")
        if source == target:
            return (source,)

        import heapq

        # Priority queue of (cumulative_weight, current_node, path)
        pq: list[tuple[float, str, tuple[str, ...]]] = [(0.0, source, (source,))]
        best_cost: dict[str, float] = {source: 0.0}

        while pq:
            cost, current, path = heapq.heappop(pq)
            if current == target:
                return path
            if cost > best_cost.get(current, float("inf")):
                continue

            for edge in self.edges:
                neighbor = None
                weight = edge.weight
                if edge.source == current:
                    neighbor = edge.target
                elif edge.bidirectional and edge.target == current:
                    neighbor = edge.source

                if neighbor is not None:
                    new_cost = cost + weight
                    if new_cost < best_cost.get(neighbor, float("inf")):
                        best_cost[neighbor] = new_cost
                        heapq.heappush(pq, (new_cost, neighbor, (*path, neighbor)))

        return None

    def shortest_path_distance(self, source: str, target: str) -> float | None:
        path = self.shortest_path(source, target)
        if path is None:
            return None
        if len(path) == 1:
            return 0.0

        total = 0.0
        for u, v in pairwise(path):
            for edge in self.edges:
                if (edge.source == u and edge.target == v) or (
                    edge.bidirectional and edge.source == v and edge.target == u
                ):
                    total += edge.weight
                    break
        return total

    def subgraph(self, nodes: tuple[str, ...]) -> "NetworkTopology":
        node_set = set(nodes)
        if not node_set.issubset(set(self.nodes)):
            raise ValueError("Subgraph nodes must be a subset of topology nodes")
        sub_edges = tuple(
            e for e in self.edges if e.source in node_set and e.target in node_set
        )
        return NetworkTopology(nodes=nodes, edges=sub_edges)
