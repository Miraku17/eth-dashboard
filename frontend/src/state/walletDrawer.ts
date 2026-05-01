import { create } from "zustand";

type State = {
  address: string | null;
  open: boolean;
  show: (address: string) => void;
  close: () => void;
};

export const useWalletDrawer = create<State>((set) => ({
  address: null,
  open: false,
  show: (address) => set({ address, open: true }),
  close: () => set({ open: false }),
}));
