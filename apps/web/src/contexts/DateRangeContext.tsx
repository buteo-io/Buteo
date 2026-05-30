import React, { createContext, useContext, useState, useMemo } from "react";
import { defaultRange, Range, toIsoZ } from "../utils/time";

type DateRangeContextType = {
  range: Range;
  setRange: React.Dispatch<React.SetStateAction<Range>>;
  fromIso: string;
  toIso: string;
};

const DateRangeContext = createContext<DateRangeContextType | null>(null);

export function DateRangeProvider({ children }: { children: React.ReactNode }) {
  const [range, setRange] = useState<Range>(defaultRange());

  const fromIso = useMemo(() => toIsoZ(range.from), [range.from]);
  const toIso = useMemo(() => toIsoZ(range.to), [range.to]);

  return (
    <DateRangeContext.Provider value={{ range, setRange, fromIso, toIso }}>
      {children}
    </DateRangeContext.Provider>
  );
}

export function useDateRange() {
  const context = useContext(DateRangeContext);
  if (!context) {
    throw new Error("useDateRange must be used within a DateRangeProvider");
  }
  return context;
}
