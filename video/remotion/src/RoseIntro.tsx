// The opening of the demo video, as one Remotion composition:
//   the title card, then Rose talking (the HeyGen clip, or the stand-in
//   still until it exists) with her words as captions and a small label
//   beside her as she names each trouble; a cutaway to her phone right
//   after "so I leave it alone." (the scam texts) and another right after
//   "odd calls, odd letters." (an unknown call); the rest of her story and
//   "Then my daughter set up Buddy."; then a fade to the app's page color
//   so the cut to Buddy is clean.
// The clip, the cut times and the words come from src/data.ts
// (scripts/video_remotion_data.py). Render: npx remotion render RoseIntro ../rose-intro.mp4
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import React from "react";
import { AbsoluteFill, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions, firstSaid } from "./Captions";
import { PHONE_CALL_SECONDS, PHONE_TEXTS_SECONDS, PhoneCall, PhoneTexts } from "./Phone";
import { TitleCard } from "./TitleCard";
import { CAPTIONS, CLIP, CLIP_SECONDS, CUT_1, CUT_2 } from "./data";
import { color, font, seconds } from "./theme";

const TITLE_SECONDS = 3.2;
const TITLE_FADE = 0.5;
const TAIL_SECONDS = 1.0; // the fade to the page color and a short hold

// The four troubles Buddy answers later, named beside Rose as she says them.
const LABELS = [
  { word: "phone", text: "the phone" },
  { word: "glasses", text: "her glasses" },
  { word: "pills", text: "her pills" },
  { word: "letters", text: "odd calls and letters" },
];

const Label: React.FC<{ text: string; atMs: number; offsetMs: number; row: number }> = ({ text, atMs, offsetMs, row }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const start = Math.round(((atMs - offsetMs) / 1000) * fps);
  const rise = spring({ frame: frame - start, fps, config: { damping: 16, stiffness: 110 } });
  const gone = interpolate(frame - start, [seconds(2.6), seconds(2.9)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  if (frame < start || frame > start + seconds(2.9)) {
    return null;
  }
  return (
    <div
      style={{
        position: "absolute",
        left: 1290,
        top: 300 + row * 92,
        display: "flex",
        alignItems: "center",
        gap: 16,
        fontFamily: font.sans,
        fontSize: 30,
        fontWeight: 600,
        color: color.text2,
        opacity: rise * gone,
        transform: `translateX(${(1 - rise) * 24}px)`,
      }}
    >
      <span style={{ width: 48, height: 1, background: color.borderStrong }} />
      {text}
    </div>
  );
};

const Honesty: React.FC = () => {
  const frame = useCurrentFrame();
  const show = interpolate(frame, [seconds(0.6), seconds(1.0), seconds(6.0), seconds(6.4)], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 96,
        top: 72,
        display: "flex",
        alignItems: "center",
        gap: 20,
        height: 84,
        padding: "0 36px 0 28px",
        borderRadius: 999,
        border: `1px solid ${color.borderStrong}`,
        background: "rgba(255, 255, 255, 0.94)",
        boxShadow: "0 8px 24px rgba(28, 27, 25, 0.12)",
        fontFamily: font.sans,
        fontSize: 34,
        fontWeight: 600,
        color: color.text,
        opacity: show,
      }}
    >
      <span
        style={{
          width: 40,
          height: 40,
          borderRadius: "50%",
          background: `radial-gradient(circle at 40% 35%, #FFD8A8 0%, ${color.peach} 40%, ${color.rose} 72%, ${color.violet} 100%)`,
        }}
      />
      Rose is made up. Her voice and pictures are AI.
    </div>
  );
};

// One stretch of Rose talking: from one moment of the clip to another.
const Rose: React.FC<{ from: number; to: number; first?: boolean; last?: boolean }> = ({ from, to, first, last }) => {
  const frame = useCurrentFrame();
  const length = seconds(to - from);
  const fadeOut = last ? interpolate(frame, [length - seconds(0.6), length], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  const fadeIn = first ? interpolate(frame, [0, seconds(0.4)], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  const offsetMs = from * 1000;
  return (
    <AbsoluteFill style={{ background: color.bg }}>
      <OffthreadVideo
        src={staticFile(CLIP)}
        trimBefore={seconds(from)}
        trimAfter={seconds(to)}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />
      {LABELS.map((label, row) => {
        const atMs = firstSaid(CAPTIONS, label.word);
        const inside = atMs >= from * 1000 && atMs < to * 1000;
        return inside ? <Label key={label.word} text={label.text} atMs={atMs} offsetMs={offsetMs} row={row} /> : null;
      })}
      <Captions captions={CAPTIONS} offsetMs={offsetMs} />
      {first ? <Honesty /> : null}
      <AbsoluteFill style={{ background: color.bg, opacity: Math.max(fadeIn, fadeOut), pointerEvents: "none" }} />
    </AbsoluteFill>
  );
};

export const roseIntroFrames = (): number =>
  seconds(TITLE_SECONDS) -
  seconds(TITLE_FADE) +
  seconds(CUT_1) +
  seconds(PHONE_TEXTS_SECONDS) +
  seconds(CUT_2 - CUT_1) +
  seconds(PHONE_CALL_SECONDS) +
  seconds(CLIP_SECONDS - CUT_2) +
  seconds(TAIL_SECONDS);

export const RoseIntro: React.FC = () => {
  return (
    <TransitionSeries>
      <TransitionSeries.Sequence name="Title" durationInFrames={seconds(TITLE_SECONDS)}>
        <TitleCard />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: seconds(TITLE_FADE) })} />
      <TransitionSeries.Sequence name="Rose, to the phone" durationInFrames={seconds(CUT_1)}>
        <Rose from={0} to={CUT_1} first />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="Her phone: the scam texts" durationInFrames={seconds(PHONE_TEXTS_SECONDS)}>
        <PhoneTexts />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="Rose, to the call" durationInFrames={seconds(CUT_2 - CUT_1)}>
        <Rose from={CUT_1} to={CUT_2} />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="Her phone: the unknown call" durationInFrames={seconds(PHONE_CALL_SECONDS)}>
        <PhoneCall />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="Rose, to the end" durationInFrames={seconds(CLIP_SECONDS - CUT_2)}>
        <Rose from={CUT_2} to={CLIP_SECONDS} last />
      </TransitionSeries.Sequence>
      <TransitionSeries.Sequence name="Hold on the page color" durationInFrames={seconds(TAIL_SECONDS)}>
        <AbsoluteFill style={{ background: color.bg }} />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
