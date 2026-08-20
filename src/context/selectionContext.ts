/**
 * selectionContext.ts
 * Shared selected-clip state so Timeline → Inspector can communicate.
 */
import { createContext, useContext } from 'react';

export interface SelectedClip {
  clipId:     string;
  clipName:   string;
  clipType:   string;
  trackIndex: number;
}

export interface SelectionCtx {
  selected:   SelectedClip | null;
  setSelected: (c: SelectedClip | null) => void;
}

export const SelectionContext = createContext<SelectionCtx>({
  selected:    null,
  setSelected: () => {},
});

export function useSelection() {
  return useContext(SelectionContext);
}
