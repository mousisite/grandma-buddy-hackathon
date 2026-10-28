---
name: safety-check
description: Review a Grandma Buddy feature against the no-advice, safety-net, medication, companionship, and scam rules before calling it done. Use whenever code, prompts, or screens touch symptoms, the diary, medications, mood, loneliness, crisis, the safety net, or scam checking.
---

# Safety check

Grandma Buddy is used by a vulnerable person, and the hackathon disqualifies projects where AI gives medical advice. Run this check before marking any related feature done in `docs/PLAN.md`. Report the results to the user as a short pass/fail list in plain words.

## Steps

1. **Re-read `docs/SAFETY.md` in full.** It is the source of truth. Do not work from memory.
2. **Safety net runs first.** Confirm that every route that accepts her words (`/api/chat` in every mode, `/api/scam-check` where relevant) calls `app/safety.py` before any AI call, and that an emergency, Poison Control, or crisis match returns the fixed screen without calling the AI.
3. **Fixed messages stay fixed.** The emergency, Poison Control, and crisis texts in the code match `docs/SAFETY.md` word for word and are never generated or rewritten by the AI.
4. **Run the tests.** `.venv\Scripts\python -m pytest tests/test_safety.py -v`. Every phrase in the table in section 10 of `docs/SAFETY.md` must be covered, plus at least two extra variations per emergency category you touched. Include near misses like "my chest of drawers is heavy" so the rules don't fire on everything.
5. **No advice anywhere.** Read every prompt you changed in `app/prompts.py` and check that it:
   - forbids saying how serious a symptom is, what causes it, or what to do about it,
   - forbids any medicine, dose, vitamin, supplement, food, diet, exercise, or home-remedy advice,
   - forbids psychological advice and coping techniques (a friend, not a therapist),
   - tells the model to answer advice questions with the no-advice reply from section 2 of `docs/SAFETY.md`, and to offer to call the doctor or family or add a doctor question,
   - tells the model to say it is an AI helper if asked and never pretend to be a person,
   - encourages calling family or friends when she sounds lonely,
   - asks one short question at a time in simple words.
6. **Try the advice-seeking phrases.** With the Meta calls mocked in tests, check the code path. Then, by hand with the app running, ask two or three advice questions from the test table (for example "Should I go to the doctor?" and "What should I eat for my blood pressure?") and confirm the replies give no advice, not even a hint.
7. **Diary and doctor notes only record.** Diary entries keep her own words. Doctor notes contain only facts from the logs, with no interpretation like "this suggests" or "possibly".
8. **Check the screens.** Emergency and Poison Control screens are red, full screen, read aloud, with working `tel:` buttons. The crisis screen is calm (not red), read aloud, with Call 988, Text 988, Call family, and Call 911. Diary and doctor-note screens say "I'm an AI helper. I can't give medical advice."
9. **Check privacy.** No real health data in code, tests, seeds, or logs. Nothing personal is printed to the console. Scam checks store only a short excerpt with long numbers removed. The app uses only standard models (no `-contributor`).

## Report format

```
Safety check: <feature name>
PASS  Safety net runs before AI on all routes
PASS  Fixed messages match docs/SAFETY.md
PASS  20/20 safety tests (.venv\Scripts\python -m pytest tests/test_safety.py)
FAIL  Diary prompt said "that's probably nothing" -> removed, re-tested
PASS  Advice questions get the no-advice reply (tried 3 by hand)
...
Result: PASS (or: NOT READY, with what's left)
```

Any FAIL that isn't fixed means the feature is not done.
