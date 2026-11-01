# app/labels.py
# A pill from a photo of its bottle (docs/SPEC.md feature 4, docs/SAFETY.md
# section 5). A family member photographs the bottle; Muse Spark reads the
# medicine's name and the label's words as printed into a strict form;
# plain code trims them to what the Add a pill form takes. That is all:
# the words only fill in the form, the family member checks each one
# against the bottle before saving, and the times are always typed by the
# family. Nothing is stored here, and the photo is never saved or logged.

from app import meta_client, prompts

MAX_NAME = 80  # the form's limits (app/routes/meds.py)
MAX_LABEL = 200

SCHEMA = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "name": {"type": "string"},
        "label": {"type": "string"},
    },
    "required": ["readable", "name", "label"],
    "additionalProperties": False,
}

COULDNT_READ = ("I couldn’t read that label. Could you take another photo, closer, with the label flat and in good "
                "light? Or type it in.")
NOT_NOW = "Buddy couldn’t read the label just now. Please try again in a moment, or type it in."
CHECK_IT = "From the photo. Please check both against the bottle before saving."


def trimmed(words: str, most: int) -> str:
    """One line of plain words, cut at a word to fit the form."""
    words = " ".join(str(words).split())
    if len(words) <= most:
        return words
    return words[:most].rsplit(" ", 1)[0].rstrip(" ,;:")


def read_label(image: str) -> dict:
    """What the bottle says: {"name", "label"}, as printed. ValueError
    (COULDNT_READ) when Spark can't read it; meta_client.MetaError when
    Spark can't be reached."""
    messages = [
        {"role": "developer", "content": prompts.PILL_LABEL},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is the photo of the bottle."},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    form = meta_client.structured(messages, "pill_label", SCHEMA, reasoning="low", max_tokens=1500)
    name = trimmed(form.get("name", ""), MAX_NAME)
    label = trimmed(form.get("label", ""), MAX_LABEL)
    if form.get("readable") is not True or not name or not label:
        raise ValueError(COULDNT_READ)
    return {"name": name, "label": label}
