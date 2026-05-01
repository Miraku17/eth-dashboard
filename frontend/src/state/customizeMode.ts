import { create } from "zustand";

type State = {
  editing: boolean;
  toggle: () => void;
  exit: () => void;
};

export const useCustomizeMode = create<State>((set) => ({
  editing: false,
  toggle: () => set((s) => ({ editing: !s.editing })),
  exit: () => set({ editing: false }),
}));
