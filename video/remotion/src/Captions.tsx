// Rose's words as she says them, in Buddy's own reading style: a short
// line at a time, words not yet spoken in the second text color, spoken
// words in ink (docs/DESIGN.md, "like song lyrics"). The words and their
// times come from Whisper (src/data.ts).
import { createTikTokStyleCaptions, type Caption } from "@remotion/captions";
import React, { useMemo } from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { color, font } from "./theme";

type Props = {
  captions: Caption[];
  // Where this video segment starts inside the whole clip, in ms: the
  // segment's frame 0 is that moment of the clip.
  offsetMs: number;
};

export const Captions: React.FC<Props> = ({ captions, offsetMs }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const now = offsetMs + (frame / fps) * 1000;

  const { pages } = useMemo(
    () => createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: 2400 }),
    [captions],
  );
  const index = pages.findIndex((page, i) => {
    const next = pages[i + 1];
    return now >= page.startMs - 150 && (next === undefined || now < next.startMs - 150);
  });
  const page = pages[index];
  if (!page) {
    return null;
  }
  const pageEnd = page.tokens[page.tokens.length - 1].toMs;
  if (now > pageEnd + 900) {
    return null; // she paused: nothing to read
  }
  const arrive = interpolate(now, [page.startMs - 150, page.startMs + 100], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 96,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          maxWidth: 1460,
          padding: "18px 36px",
          borderRadius: 24,
          background: "rgba(247, 247, 245, 0.78)",
          backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)",
          fontFamily: font.sans,
          fontSize: 58,
          fontWeight: 500,
          lineHeight: 1.25,
          letterSpacing: "-0.01em",
          textAlign: "center",
          opacity: arrive,
          transform: `translateY(${(1 - arrive) * 10}px)`,
        }}
      >
        {page.tokens.map((token, i) => {
          const spoken = now >= token.fromMs;
          const active = spoken && now < token.toMs;
          return (
            <span
              key={i}
              style={{
                color: spoken ? color.text : color.text2,
                display: "inline-block",
                transform: active ? "translateY(-2px)" : "none",
                transition: "none",
                whiteSpace: "pre",
              }}
            >
              {token.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};

// The moment (ms into the clip) a word is first said, for the labels
// beside Rose. -1 when Whisper didn't hear it.
export const firstSaid = (captions: Caption[], word: string): number => {
  const found = captions.find((c) => c.text.trim().replace(/[.,!?]/g, "").toLowerCase() === word);
  return found ? found.startMs : -1;
};
