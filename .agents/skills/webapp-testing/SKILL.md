---
name: webapp-testing
description: Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.
license: Complete terms in LICENSE.txt
---

# Web Application Testing

To test local web applications, write native Python Playwright scripts.

**Helper Scripts Available**:
- `scripts/with_server.py` - Manages server lifecycle (supports multiple servers)

**Always run scripts with `--help` first** to see usage. DO NOT read the source until you try running the script first and find that a customized solution is abslutely necessary. These scripts can be very large and thus pollute your context window. They exist to be called directly as black-box scripts rather than ingested into your context window.

## Decision Tree: Choosing Your Approach

```
User task → Is it static HTML?
    ├─ Yes → Read HTML file directly to identify selectors
    │         ├─ Success → Write Playwright script using selectors
    │         └─ Fails/Incomplete → Treat as dynamic (below)
    │
    └─ No (dynamic webapp) → Is the server already running?
        ├─ No → Run: python scripts/with_server.py --help
        │        Then use the helper + write simplified Playwright script
        │
        └─ Yes → Reconnaissance-then-action:
            1. Navigate and wait for networkidle
            2. Take screenshot or inspect DOM
            3. Identify selectors from rendered state
            4. Execute actions with discovered selectors
```

## Example: Using with_server.py

To start a server, run `--help` first, then use the helper:

**Single server:**
```bash
python scripts/with_server.py --server "npm run dev" --port 5173 -- python your_automation.py
```

**Multiple servers (e.g., backend + frontend):**
```bash
python scripts/with_server.py \
  --server "cd backend && python server.py" --port 3000 \
  --server "cd frontend && npm run dev" --port 5173 \
  -- python your_automation.py
```

To create an automation script, include only Playwright logic (servers are managed automatically):
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) # Always launch chromium in headless mode
    page = browser.new_page()
    page.goto('http://localhost:5173') # Server already running and ready
    page.wait_for_load_state('networkidle') # CRITICAL: Wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **Inspect rendered DOM**:
   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. **Identify selectors** from inspection results

3. **Execute actions** using discovered selectors

## Common Pitfall

❌ **Don't** inspect the DOM before waiting for `networkidle` on dynamic apps
✅ **Do** wait for `page.wait_for_load_state('networkidle')` before inspection

## Best Practices

- **Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly. 
- Use `sync_playwright()` for synchronous scripts
- Always close the browser when done
- Use descriptive selectors: `text=`, `role=`, CSS selectors, or IDs
- Add appropriate waits: `page.wait_for_selector()` or `page.wait_for_timeout()`

## Reference Files

- **examples/** - Examples showing common patterns:
  - `element_discovery.py` - Discovering buttons, links, and inputs on a page
  - `static_html_automation.py` - Using file:// URLs for local HTML
  - `console_logging.py` - Capturing console logs during automation

## Windows and this project (added by the Grandma Buddy project, October 2026)

Everything above this section is Anthropic's original. These notes win where they differ. `scripts/with_server.py` was also changed for Windows (see the note at its top).

- This computer runs Windows with PowerShell. Run Python as `.venv\Scripts\python` (the project's environment), never `python3`, and never run bash or `.sh` scripts.
- Playwright belongs in `requirements.txt`, so it's installed into `.venv` with the other packages. The Chromium test browser is already downloaded on this computer. If Playwright says the browser is missing, ask the user to run `.venv\Scripts\python -m playwright install chromium`. Don't download it yourself.
- Put browser-check scripts in `scripts/browser_checks/` (for example `check_home.py`). Save screenshots to `test-output/`, which git ignores. Never use `/tmp`.
- Start our app and run a check in one command:

  ```
  .venv\Scripts\python .agents/skills/webapp-testing/scripts/with_server.py --server ".venv\Scripts\python -m uvicorn app.main:app --port 8000" --port 8000 -- .venv\Scripts\python scripts/browser_checks/check_home.py
  ```

  If it says port 8000 is already in use, the app is already running in another terminal. Run the check script directly against http://localhost:8000 instead, or ask the user to stop the app first.
- Run headless by default. If the user wants to watch the browser, launch with `headless=False`.
- After taking a screenshot, look at the image before saying a screen looks right.
- To test the Talk button without a real microphone, give Chromium a fake microphone that plays a WAV file:

  ```python
  browser = p.chromium.launch(headless=True, args=[
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--use-file-for-fake-audio-capture=test-output/sample_speech.wav",
  ])
  context = browser.new_context(permissions=["microphone"])
  page = context.new_page()
  ```

  Use a short made-up recording, never a real recording of Grandma. Ask the user for one if `test-output/sample_speech.wav` doesn't exist.
- A browser check that triggers chat or transcription calls the real Meta API, which costs money. Check layout and buttons without speaking when you can, and keep voice tests few.
