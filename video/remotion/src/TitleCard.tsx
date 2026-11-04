// The title card: the orb arrives, then the name word by word (a blur
// lifting, not a slide), then the two quiet lines. Once landed, nothing
// moves but the orb's own slow breathing.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Orb } from "./Orb";
import { color, font } from "./theme";

const Word: React.FC<{ text: string; at: number }> = ({ text, at }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [at, at + 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <span style={{ display: "inline-block", opacity: p, filter: `blur(${(1 - p) * 8}px)`, marginRight: "0.22em" }}>
      {text}
    </span>
  );
};

export const TitleCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const orbIn = spring({ frame, fps, config: { damping: 18, stiffness: 90 } });
  const lead = interpolate(frame, [24, 36], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const tag = interpolate(frame, [34, 48], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: color.bg, alignItems: "center", justifyContent: "center", fontFamily: font.sans }}>
      <div style={{ transform: `scale(${0.7 + orbIn * 0.3})`, opacity: orbIn, marginBottom: 72 }}>
        <Orb size={360} />
      </div>
      <h1
        style={{
          margin: 0,
          fontFamily: font.serif,
          fontWeight: 400,
          fontSize: 148,
          letterSpacing: "-0.025em",
          lineHeight: 1.05,
          color: color.text,
        }}
      >
        <Word text="Grandma" at={12} />
        <Word text="Buddy" at={16} />
      </h1>
      <p style={{ margin: "20px 0 0", fontSize: 48, fontWeight: 500, color: color.text2, opacity: lead }}>
        built for my grandma
      </p>
      <p
        style={{
          position: "absolute",
          bottom: 88,
          margin: 0,
          padding: "0 28px",
          height: 64,
          lineHeight: "62px",
          border: `1px solid ${color.borderStrong}`,
          borderRadius: 999,
          background: color.surface,
          color: color.text2,
          fontSize: 26,
          fontWeight: 600,
          opacity: tag,
          transform: `translateY(${(1 - tag) * 8}px)`,
        }}
      >
        Meta Global AI Developer Hackathon 2026
      </p>
    </AbsoluteFill>
  );
};
