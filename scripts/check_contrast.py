# scripts/check_contrast.py
# Measures the contrast of every text color the app uses against the
# background it sits on (WCAG 2 formula), in light AND dark mode, and fails
# if any is too low. Text needs at least 4.5:1; large text, icons, and the
# edges of fields and controls 3:1.
#
# Run it by hand after changing a color in static/styles.css:
#   .venv\Scripts\python scripts\check_contrast.py
# The colors below must match the tokens at the top of styles.css.

THEMES = {
    "light": {
        "bg": "#F7F7F5",
        "surface": "#FFFFFF",
        "text": "#1C1B19",
        "text-2": "#5C5953",
        "primary": "#1C1B19",
        "on-primary": "#FFFFFF",
        "success": "#1E7350",
        "warning": "#9A5B00",
        "danger": "#C21F3A",
        "field-edge": "#8C8880",
        "tint": "#EFEEEA",
        # The pill reminder card where Buddy's warm light is strongest: its
        # amber and rose glows (styles.css .pill-banner) over the card.
        "card-glow": "#FCEDE2",
    },
    "dark": {
        "bg": "#131211",
        "surface": "#1D1C1A",
        "text": "#F3F1EC",
        "text-2": "#ADA89F",
        "primary": "#F3F1EC",
        "on-primary": "#131211",
        "success": "#5BC79A",
        "warning": "#F0B45A",
        "danger": "#FF6B7F",
        "field-edge": "#77726A",
        "tint": "#262522",
        "card-glow": "#413125",
    },
}

# The emergency and Poison Control screens look the same in both themes.
EMERGENCY = {"alarm": "#A8162E", "white": "#FFFFFF"}

# (text or edge color, background, what it is, minimum ratio)
PAIRS = [
    ("text", "bg", "body text and headings", 4.5),
    ("text-2", "bg", "secondary text", 4.5),
    ("text", "surface", "text on cards, sheets, and fields", 4.5),
    ("text-2", "surface", "secondary text on cards", 4.5),
    ("text", "tint", "text on chips and pressed rows", 4.5),
    ("text-2", "tint", "secondary text on chips", 4.5),
    ("on-primary", "primary", "main buttons (Talk to Buddy, Save)", 4.5),
    ("bg", "text", "toasts", 4.5),
    ("success", "bg", "taken, looks safe", 4.5),
    ("success", "surface", "taken, on cards", 4.5),
    ("warning", "bg", "likely scam, missed", 4.5),
    ("warning", "surface", "warnings on cards", 4.5),
    ("field-edge", "surface", "edges of fields, switches, and checkboxes", 3),
    ("field-edge", "tint", "a switch's knob when it is off", 3),
    ("text", "bg", "focus ring", 3),
    ("text", "card-glow", "Buddy's words on the pill reminder card", 4.5),
    ("text-2", "card-glow", "\"Pill time\" and its time on the card", 4.5),
]


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def check(label: str, colors: dict, pairs: list) -> int:
    failures = 0
    for text, background, what, minimum in pairs:
        ratio = contrast(colors[text], colors[background])
        ok = ratio >= minimum
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label:5}  {ratio:5.1f}:1  {text} on {background}  ({what}, needs {minimum}:1)")
    return failures


def main() -> int:
    failures = 0
    for theme, colors in THEMES.items():
        failures += check(theme, colors, PAIRS)
    failures += check("both", EMERGENCY, [("white", "alarm", "emergency and Poison Control screens", 4.5)])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
