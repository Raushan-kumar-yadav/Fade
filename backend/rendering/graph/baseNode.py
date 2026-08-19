from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import skia


class RenderResult:
    """
    Output of one node's execute() — an offscreen Skia image.
    None means the node produced no visible output (e.g. muted track).
    """
    def __init__(self, image: Optional[skia.Image] = None, opacity: float = 1.0) -> None:
        self.image   = image
        self.opacity = opacity

    @property
    def valid(self) -> bool:
        return self.image is not None


class BaseNode(ABC):
    """
    One node in the Render DAG.
    Python port of the C++ render graph node concept from GraphBuilder/RenderGraph.

    Topology:
      - inputs  : list of upstream nodes this node depends on
      - outputs : list of downstream nodes that depend on this node
                  (populated by RenderGraph.compile() — do not set manually)

    Kahn's algorithm uses in_degree (len(inputs)) to find roots.
    """

    def __init__(self, nodeId: str) -> None:
        self.nodeId:   str            = nodeId
        self.inputs:   list[BaseNode] = []   # upstream dependencies
        self.outputs:  list[BaseNode] = []   # downstream dependents (filled by RenderGraph)
        self._result:  RenderResult | None = None

    def addInput(self, node: "BaseNode") -> None:
        if node not in self.inputs:
            self.inputs.append(node)
            node.outputs.append(self)

    @property
    def inDegree(self) -> int:
        return len(self.inputs)

    @abstractmethod
    def execute(self, ctx: "RenderContext") -> RenderResult:
        """
        Run this node. All input nodes are guaranteed to have been
        executed already (topological order).
        """
        ...

    def getResult(self) -> RenderResult | None:
        return self._result

    def run(self, ctx: "RenderContext") -> RenderResult:
        self._result = self.execute(ctx)
        return self._result

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.nodeId!r})"
