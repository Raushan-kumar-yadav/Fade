/**
 * selectionContext.ts
 * Shared selected state so Timeline → Inspector can communicate.
 */
import { createContext, useContext } from 'react';

export type SelectedItem =
  | { type: 'clip'; clipId: string; clipName: string; clipType: string; trackIndex: number }
  | { type: 'transition'; id: string; trackId: string; data: any };

export interface SelectionCtx {
  selected:   SelectedItem | null;
  setSelected: (c: SelectedItem | null) => void;
}

export const SelectionContext = createContext<SelectionCtx>({
  selected:    null,
  setSelected: () => {},
});

export function useSelection() {
  return useContext(SelectionContext);
}
