/**
 * toolContext.ts — Extended with full Qteee-Vulkan tool set
 *
 * Mirrors UiTools::Tool enum from Qteee toolDef.hpp
 */
import { createContext, useContext } from 'react';

// ── Full tool enum (matches Qteee UiTools::Tool) ──────────────────────────
export type ActiveTool =
  // Timeline editing tools
  | 'pointer'       // V  — select/move
  | 'razor'         // C  — cut
  | 'ripple'        // R  — ripple edit
  | 'slip'          // Y  — slip edit
  | 'hand'          // H  — pan
  | 'selectLeft'    // ←
  | 'selectRight'   // →
  // Creation tools
  | 'text'          // T  — add text clip
  | 'solid'         // O  — add solid/color clip
  // Shape sub-tools (Q to cycle, flyout for sub-type)
  | 'shape:rect'
  | 'shape:circle'
  | 'shape:ellipse'
  | 'shape:star'
  | 'shape:polygon'
  | 'shape:line'
  | 'shape:arc'
  | 'shape:path'    // bezier pen
  // Adjustment
  | 'adjustment';

/** Shape-type string extracted from a shape tool id */
export function shapeTypeOf(tool: ActiveTool): string | null {
  if (tool.startsWith('shape:')) return tool.slice(6);
  return null;
}

export function isShapeTool(tool: ActiveTool): boolean {
  return tool.startsWith('shape:');
}

export function isEditTool(tool: ActiveTool): boolean {
  return ['pointer','razor','ripple','slip','hand','selectLeft','selectRight'].includes(tool);
}

export function isCreationTool(tool: ActiveTool): boolean {
  return !isEditTool(tool);
}

// ── CSS cursor for each tool ───────────────────────────────────────────────
export const TOOL_CURSOR: Record<string, string> = {
  pointer:       'default',
  razor:         'url("data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 20 20\'><text y=\'16\' font-size=\'16\'>✂</text></svg>") 4 16, crosshair',
  ripple:        'col-resize',
  slip:          'ew-resize',
  hand:          'grab',
  selectLeft:    'w-resize',
  selectRight:   'e-resize',
  text:          'text',
  solid:         'crosshair',
  adjustment:    'crosshair',
  'shape:rect':  'crosshair',
  'shape:circle':'crosshair',
  'shape:ellipse':'crosshair',
  'shape:star':  'crosshair',
  'shape:polygon':'crosshair',
  'shape:line':  'crosshair',
  'shape:arc':   'crosshair',
  'shape:path':  'crosshair',
};

// ── Context ────────────────────────────────────────────────────────────────
export interface ToolCtx {
  activeTool:    ActiveTool;
  setTool:       (t: ActiveTool) => void;
  lastShapeTool: ActiveTool;            // remembers last shape sub-type
  setLastShape:  (t: ActiveTool) => void;
}

export const ToolContext = createContext<ToolCtx>({
  activeTool:    'pointer',
  setTool:       () => {},
  lastShapeTool: 'shape:rect',
  setLastShape:  () => {},
});

export function useTool() {
  return useContext(ToolContext);
}
