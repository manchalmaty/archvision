import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn convention: merge conditional classes AND resolve Tailwind conflicts
// (the last conflicting utility wins), so `cn("bg-zinc-500", className)` lets
// a caller's `bg-brand-500` actually override the default.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
