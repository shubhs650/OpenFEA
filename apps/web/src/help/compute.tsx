import { createContext, useContext, useEffect, useId, useState } from "react";
import type { ReactNode } from "react";

const Compute = createContext<{
  active: boolean;
  set: (id: string, active: boolean) => void;
}>({
  active: false,
  set: () => {},
});
export function ComputeProvider({ children }: { children: ReactNode }) {
  const [sources, setSources] = useState<Set<string>>(new Set());
  const [set] = useState(() => (id: string, active: boolean) => {
    setSources((old) => {
      if (old.has(id) === active) return old;
      const next = new Set(old);
      if (active) next.add(id);
      else next.delete(id);
      return next;
    });
  });
  return (
    <Compute.Provider value={{ active: sources.size > 0, set }}>
      {children}
    </Compute.Provider>
  );
}
export function useComputeActivity(active: boolean) {
  const id = useId();
  const { set } = useContext(Compute);
  useEffect(() => {
    set(id, active);
    return () => set(id, false);
  }, [active, id, set]);
}
export function useComputing() {
  return useContext(Compute).active;
}
