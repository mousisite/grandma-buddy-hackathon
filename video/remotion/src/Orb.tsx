// Buddy, the living orb (static/buddy.js and styles.css "Buddy, the orb"):
// a glow, a core of warm light with four blurred color blobs that drift,
// and a soft shine. Every frame is a function of the frame number, so a
// render is always the same.
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { color } from "./theme";

type Props = { size: number; style?: React.CSSProperties };

export const Orb: React.FC<Props> = ({ size, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const breathe = 1 + Math.sin((t / 6) * Math.PI * 2) * 0.02; // 0.98 to 1.02 over 6 s, as in the app
  const turn = (t / 24) * 360; // the colors flow around once in 24 s

  const blob = (
    name: string,
    place: React.CSSProperties,
    drift: number,
  ): React.CSSProperties => ({
    position: "absolute",
    width: "78%",
    height: "78%",
    borderRadius: "50%",
    filter: `blur(${size * 0.09}px)`,
    background: `radial-gradient(circle, ${name} 0%, transparent 68%)`,
    transform: `translate(${Math.sin(t / drift) * size * 0.04}px, ${Math.cos(t / drift) * size * 0.04}px)`,
    ...place,
  });

  return (
    <div style={{ position: "relative", width: size, height: size, ...style }}>
      <div
        style={{
          position: "absolute",
          inset: "-22%",
          borderRadius: "50%",
          background:
            "radial-gradient(closest-side, rgba(247, 140, 91, 0.55), rgba(225, 96, 126, 0.28) 55%, rgba(139, 108, 242, 0) 100%)",
          filter: `blur(${size * 0.13}px)`,
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          overflow: "hidden",
          transform: `scale(${breathe})`,
          background: `radial-gradient(circle at 40% 35%, #FFD8A8 0%, ${color.peach} 40%, ${color.rose} 72%, ${color.violet} 100%)`,
          boxShadow:
            "inset 0 0 0 1px rgba(255, 255, 255, 0.22), inset 0 -18px 48px rgba(139, 108, 242, 0.35), inset 0 12px 32px rgba(255, 255, 255, 0.3)",
        }}
      >
        <div style={{ position: "absolute", inset: 0, transform: `rotate(${turn}deg)` }}>
          <div style={blob(color.amber, { top: "-14%", left: "-8%" }, 12)} />
          <div style={blob(color.peach, { top: "14%", right: "-22%" }, 13)} />
          <div style={blob(color.rose, { bottom: "-18%", left: "6%" }, 11)} />
          <div style={blob(color.violet, { right: "-14%", bottom: "-10%" }, 14)} />
        </div>
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "50%",
            background: "radial-gradient(circle at 32% 24%, rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0) 36%)",
          }}
        />
      </div>
    </div>
  );
};
