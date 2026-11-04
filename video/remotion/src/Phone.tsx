// Rose's phone, full screen, as the scam messages arrive: the same two
// cutaways as video/cutaways/src/phone.html, drawn in React so the
// Remotion opening is one project. Every number, name and message is
// made up (555 numbers are reserved for fiction). The chime and the
// ring are the sine-wave sounds from scripts/video_cutaways.py.
import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { color, font, seconds } from "./theme";

const bubble =
  "M21 12a8 8 0 0 1-8 8H8l-4 3v-5.5A8 8 0 0 1 13 4a8 8 0 0 1 8 8z";

const Icon: React.FC<{ d: string; size: number; stroke?: number }> = ({ d, size, stroke = 2 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="#fff" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const PhoneFrame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: color.bg, alignItems: "center", justifyContent: "center", fontFamily: font.sans }}>
    <div
      style={{
        position: "relative",
        width: 460,
        height: 940,
        padding: 14,
        borderRadius: 64,
        background: color.text,
        boxShadow:
          "0 1px 2px rgba(28, 27, 25, 0.08), 0 24px 48px rgba(28, 27, 25, 0.18), 0 60px 90px -30px rgba(28, 27, 25, 0.3)",
      }}
    >
      <div
        style={{
          position: "relative",
          width: 432,
          height: 912,
          borderRadius: 52,
          overflow: "hidden",
          background: "linear-gradient(160deg, #E4E9F0 0%, #CBD5E1 55%, #B6C3D3 100%)",
        }}
      >
        <div style={{ position: "absolute", top: 28, left: "50%", width: 124, height: 36, marginLeft: -62, borderRadius: 20, background: color.text, zIndex: 5 }} />
        {children}
      </div>
    </div>
  </AbsoluteFill>
);

const LockScreen: React.FC = () => (
  <>
    <div style={{ marginTop: 118, textAlign: "center", fontSize: 92, fontWeight: 300, letterSpacing: "-0.02em", lineHeight: 1, color: color.text }}>10:24</div>
    <div style={{ marginTop: 8, textAlign: "center", fontSize: 23, fontWeight: 500, color: "#3C3A36" }}>Tuesday, November 3</div>
  </>
);

const Note: React.FC<{ from: string; body: string; at: number; pushedBy?: number }> = ({ from, body, at, pushedBy = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const arrive = spring({ frame: frame - at, fps, config: { damping: 16, stiffness: 120 } });
  const pushed = pushedBy > 0 ? spring({ frame: frame - pushedBy, fps, config: { damping: 16, stiffness: 120 } }) : 0;
  if (frame < at) {
    return null;
  }
  return (
    <div
      style={{
        position: "absolute",
        left: 16,
        right: 16,
        top: 300,
        minHeight: 150,
        padding: "16px 18px",
        borderRadius: 24,
        background: "rgba(255, 255, 255, 0.88)",
        boxShadow: "0 8px 24px rgba(28, 27, 25, 0.1)",
        display: "grid",
        gridTemplateColumns: "44px 1fr",
        columnGap: 12,
        opacity: arrive,
        transform: `translateY(${-60 * (1 - arrive) + 162 * pushed}px)`,
      }}
    >
      <div style={{ width: 44, height: 44, borderRadius: 12, background: "#34C759", display: "grid", placeItems: "center" }}>
        <Icon d={bubble} size={26} />
      </div>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 16, fontWeight: 600, color: color.text2 }}>
          <span>Messages</span>
          <span style={{ fontWeight: 500 }}>now</span>
        </div>
        <div style={{ marginTop: 2, fontSize: 20, fontWeight: 600, color: color.text }}>{from}</div>
        <div style={{ marginTop: 2, fontSize: 19, lineHeight: 1.3, color: color.text }}>{body}</div>
      </div>
    </div>
  );
};

// 4.5 s: the prize text arrives at 0.5 s, the "grandson in jail" text on top of it at 2.3 s.
export const PHONE_TEXTS_SECONDS = 4.5;
export const PhoneTexts: React.FC = () => (
  <PhoneFrame>
    <LockScreen />
    <Note at={seconds(0.5)} pushedBy={seconds(2.3)} from="+1 (800) 555-0142" body="CONGRATULATIONS! YOU HAVE WON $5,000! Send a $50 processing fee in gift cards within 24 hours. Do not tell anyone." />
    <Note at={seconds(2.3)} from="Unknown" body="Grandma it's me, I'm in jail. Send $2,000 in gift cards and don't tell mom." />
    <Sequence from={seconds(0.5)} durationInFrames={seconds(0.6)}>
      <Audio src={staticFile("sfx/chime.wav")} />
    </Sequence>
    <Sequence from={seconds(2.3)} durationInFrames={seconds(0.6)}>
      <Audio src={staticFile("sfx/chime.wav")} />
    </Sequence>
  </PhoneFrame>
);

// 3.2 s: a call from an unknown number, rings pulsing outward, ringing twice.
export const PHONE_CALL_SECONDS = 3.2;
export const PhoneCall: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const screen = interpolate(t, [0, 0.3], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const ring = (i: number) => {
    if (t < 0.3) {
      return { opacity: 0, scale: 1 };
    }
    const phase = ((t - 0.3) * 0.8 + i * 0.5) % 1;
    return { opacity: (1 - phase) * 0.8, scale: 1 + phase * 0.9 };
  };
  return (
    <PhoneFrame>
      <LockScreen />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(180deg, #2E333B 0%, #15171B 100%)",
          color: "#fff",
          textAlign: "center",
          opacity: screen,
        }}
      >
        <div style={{ marginTop: 160, fontSize: 42, fontWeight: 500, letterSpacing: "-0.01em" }}>Unknown number</div>
        <div style={{ marginTop: 10, fontSize: 22, color: "rgba(255,255,255,0.7)" }}>incoming call…</div>
        <div style={{ position: "absolute", top: 380, left: "50%", width: 150, height: 150, marginLeft: -75 }}>
          {[0, 1].map((i) => {
            const r = ring(i);
            return (
              <div
                key={i}
                style={{ position: "absolute", inset: 0, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.55)", opacity: r.opacity, transform: `scale(${r.scale})` }}
              />
            );
          })}
          <div style={{ position: "absolute", inset: 0, borderRadius: "50%", background: "rgba(255,255,255,0.16)", display: "grid", placeItems: "center" }}>
            <svg viewBox="0 0 24 24" width={84} height={84} fill="none" stroke="#fff" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 21a8 8 0 0 1 16 0" />
            </svg>
          </div>
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 96, display: "flex", justifyContent: "center", gap: 120 }}>
          <div style={{ display: "grid", justifyItems: "center", gap: 12, fontSize: 18, color: "rgba(255,255,255,0.85)" }}>
            <div style={{ width: 86, height: 86, borderRadius: "50%", background: "#FF3B30", display: "grid", placeItems: "center" }}>
              <svg viewBox="0 0 24 24" width={40} height={40} fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.7 13.3a13 13 0 0 1-2-2l1.3-1.6a1 1 0 0 0 .2-1L9.3 5.5a1 1 0 0 0-1-.7H5.2A2 2 0 0 0 3.2 7a16 16 0 0 0 13.8 13.8 2 2 0 0 0 2.2-2v-3.1a1 1 0 0 0-.7-1l-3.2-.9a1 1 0 0 0-1 .2z" />
                <path d="M3 3l18 18" />
              </svg>
            </div>
            <span>Decline</span>
          </div>
          <div style={{ display: "grid", justifyItems: "center", gap: 12, fontSize: 18, color: "rgba(255,255,255,0.85)" }}>
            <div style={{ width: 86, height: 86, borderRadius: "50%", background: "#34C759", display: "grid", placeItems: "center" }}>
              <Icon d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z" size={40} />
            </div>
            <span>Accept</span>
          </div>
        </div>
      </div>
      <Sequence from={seconds(0.3)} durationInFrames={seconds(1.1)}>
        <Audio src={staticFile("sfx/ring.wav")} />
      </Sequence>
      <Sequence from={seconds(1.8)} durationInFrames={seconds(1.1)}>
        <Audio src={staticFile("sfx/ring.wav")} />
      </Sequence>
    </PhoneFrame>
  );
};
