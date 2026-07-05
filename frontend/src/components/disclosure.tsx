export function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`w-3.5 h-3.5 transition-transform duration-300 ease-out ${open ? "rotate-180" : ""}`}
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  );
}

// Height-animated disclosure: the grid-rows 0fr→1fr trick animates to the
// content's intrinsic height with no JS measuring; visibility is transitioned
// too so collapsed inputs drop out of the tab order only after the close ends.
export function Reveal({ open, children }: { open: boolean; children: React.ReactNode }) {
  return (
    <div
      className={`grid transition-[grid-template-rows,visibility] duration-300 ease-in-out ${
        open ? "grid-rows-[1fr] visible" : "grid-rows-[0fr] invisible"
      }`}
    >
      <div className="overflow-hidden min-h-0">{children}</div>
    </div>
  );
}
