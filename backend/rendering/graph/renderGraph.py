from __future__ import annotations
from collections import deque
from backend.rendering.graph.baseNode import BaseNode
from backend.rendering.renderContext import RenderContext


class RenderGraph:
  

    def __init__(self) -> None:
        self._nodes:   list[BaseNode] = []
        self._sorted:  list[BaseNode] = []
        self._compiled = False

    def addNode(self, node: BaseNode) -> None:
        if node not in self._nodes:
            self._nodes.append(node)

    def compile(self) -> None:
         
        # Build in-degree table
        inDegree: dict[str, int] = {n.nodeId: 0 for n in self._nodes}
        nodeMap:  dict[str, BaseNode] = {n.nodeId: n for n in self._nodes}

        for node in self._nodes:
            for downstream in node.outputs:
                if downstream.nodeId in inDegree:
                    inDegree[downstream.nodeId] += 1

        # Enqueue all roots  
        queue: deque[BaseNode] = deque()
        for node in self._nodes:
            if inDegree[node.nodeId] == 0:
                queue.append(node)

        self._sorted = []

        while queue:
            node = queue.popleft()
            self._sorted.append(node)

            for downstream in node.outputs:
                if downstream.nodeId not in inDegree:
                    continue
                inDegree[downstream.nodeId] -= 1
                if inDegree[downstream.nodeId] == 0:
                    queue.append(nodeMap[downstream.nodeId])

        # Cycle detection
        if len(self._sorted) != len(self._nodes):
            remaining = [n.nodeId for n in self._nodes if n not in self._sorted]
            raise RuntimeError(
                f"[RenderGraph] Cycle detected — {len(remaining)} nodes unreachable: {remaining}"
            )

        self._compiled = True

    def execute(self, ctx: RenderContext) -> None:
        """
        Run nodes hierarchically starting from the root OutputNode.
        This avoids intermediate offscreen surface allocations, improving
        performance and fixing OOM memory leaks.
        """
        output_nodes = [n for n in self._nodes if n.nodeId == "output"]
        if not output_nodes:
            return
            
        output_nodes[0].execute(ctx)

    def nodeCount(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return f"RenderGraph({len(self._nodes)} nodes, compiled={self._compiled})"
