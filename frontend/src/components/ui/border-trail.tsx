"use client";
import { cn } from "@/lib/utils";
import { motion, type Transition } from "framer-motion";

type BorderTrailProps = {
  className?: string;
  // The trail paints only inside the wrapper's transparent border ring; the
  // default 1px reads on a small card but drowns on a full-bleed canvas —
  // pass e.g. "border-[3px]" here to thicken the visible track.
  containerClassName?: string;
  size?: number;
  transition?: Transition;
  delay?: number;
  onAnimationComplete?: () => void;
  style?: React.CSSProperties;
};

export function BorderTrail({
  className,
  containerClassName,
  size = 60,
  transition,
  delay,
  onAnimationComplete,
  style,
}: BorderTrailProps) {
  // Annotated: framer-motion v11 types `ease` as Easing, and an unannotated
  // literal widens it to `string`, failing the Transition assignment.
  const BASE_TRANSITION: Transition = {
    repeat: Infinity,
    duration: 5,
    ease: "linear",
  };

  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0 rounded-[inherit] border border-transparent [mask-clip:padding-box,border-box] [mask-composite:intersect] [mask-image:linear-gradient(transparent,transparent),linear-gradient(#000,#000)]",
        containerClassName
      )}
    >
      <motion.div
        className={cn("absolute aspect-square bg-zinc-500", className)}
        style={{
          width: size,
          offsetPath: `rect(0 auto auto 0 round ${size}px)`,
          ...style,
        }}
        animate={{
          offsetDistance: ["0%", "100%"],
        }}
        transition={{
          ...(transition ?? BASE_TRANSITION),
          delay: delay,
        }}
        onAnimationComplete={onAnimationComplete}
      />
    </div>
  );
}
