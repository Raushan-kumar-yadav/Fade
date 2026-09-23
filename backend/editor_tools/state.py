from typing import Any

class SelectionGeometry:
    def __init__(self, shape_type: str, data: dict[str, Any]):
        self.shape_type = shape_type  # 'rect', 'lasso', 'polygon', 'ellipse'
        self.data = data  # specific coordinate data depending on shape_type

    def to_dict(self):
        return {
            "shape_type": self.shape_type,
            "data": self.data
        }

class SelectionState:
    def __init__(self):
        self.active_selection: SelectionGeometry | None = None

    def set_selection(self, geom: SelectionGeometry | None):
        self.active_selection = geom

    def get_selection(self) -> dict | None:
        if self.active_selection:
            return self.active_selection.to_dict()
        return None

class BrushState:
    def __init__(self):
        self.color = (1.0, 1.0, 1.0, 1.0)
        self.size = 10.0
        self.hardness = 1.0

class ToolState:
    def __init__(self):
        self.active_tool = "pointer"
        self.selection = SelectionState()
        self.brush = BrushState()

# Global editor state
editor_state = ToolState()
