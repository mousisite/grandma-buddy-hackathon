// Buddy's design tokens (static/styles.css, docs/DESIGN.md), so the opening
// looks like the app it introduces. Light theme only: the video is light.
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const color = {
  bg: "#F7F7F5",
  surface: "#FFFFFF",
  tint: "#EFEEEA",
  border: "rgba(28, 27, 25, 0.08)",
  borderStrong: "rgba(28, 27, 25, 0.14)",
  text: "#1C1B19",
  text2: "#5C5953",
  primary: "#1C1B19",
  onPrimary: "#FFFFFF",
  // Buddy's colors: only inside the orb, never for words.
  amber: "#F6B042",
  peach: "#F78C5B",
  rose: "#E1607E",
  violet: "#8B6CF2",
};

export const font = {
  sans: '"Figtree", system-ui, sans-serif',
  serif: '"Newsreader", Georgia, serif',
};

// The app's own font files, copied to public/fonts by scripts/video_remotion_data.py's setup.
// loadFont waits for them before any frame is drawn.
loadFont({ family: "Figtree", url: staticFile("fonts/Figtree.ttf"), weight: "300 900" });
loadFont({ family: "Newsreader", url: staticFile("fonts/Newsreader.ttf"), weight: "200 800" });

// The shadow of the one raised element on a screen (styles.css --shadow-raised).
export const shadowRaised =
  "0 1px 2px rgba(28, 27, 25, 0.05), 0 8px 24px rgba(28, 27, 25, 0.07), 0 28px 56px -16px rgba(28, 27, 25, 0.16)";

export const seconds = (s: number) => Math.round(s * FPS);
