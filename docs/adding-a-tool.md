# Adding a tool

Every workflow in Sieve is a **tool**: a class that builds one page in the app.

## 1. Create the module

Create `src/sieve/tools/<tool_name>.py`:

```python
from PySide6.QtWidgets import QLabel

from sieve.context import AppContext
from sieve.tools.base import Tool
from sieve.ui.widgets import ToolPage


class ExampleTool(Tool):
    id = "example"                  # stable, never rename after release
    name = "Example"
    description = "One line explaining what the tool does."
    category = "Scraping"
    icon = "tool"                   # sidebar icon, see sieve/ui/icons.py

    def create_widget(self, context: AppContext):
        page = ToolPage(self.name, self.description)
        page.content.addWidget(QLabel("Tool UI goes here"), 1)
        return page
```

## 2. Register it

Add an instance to `all_tools()` in `src/sieve/tools/__init__.py`. The order of
the list is the order in the sidebar.

## Guidelines

- **Fit the tool in one screen.** Use `ToolPage` (no page scrolling) and put input and
  output side by side, so the main action and its result are always visible.
- **Check the UI on Windows before releasing.** Every push that touches the UI runs the
  *UI preview* workflow, which renders each page (and `load_demo()` if the page has it).
- **Never block the UI thread.** Run network and file work with
  `sieve.ui.tasks.run_in_background`; it supports progress reporting and cancellation.
- **Use the shared proxy pool** via `context.proxy_pool()` instead of tool-specific
  proxy settings. `Proxy.for_requests()` and `Proxy.for_playwright()` return the
  right format for each library.
- **Browser automation** should use the system Microsoft Edge
  (`channel="msedge"` in Playwright) so no browser has to be bundled.
- **Keep logic separate from widgets** so it can be unit-tested without Qt.
- **Data the user maintains** (keyword lists, presets) goes into `sieve.storage.JsonDocument`,
  which lives in `%APPDATA%\Sieve\data` and survives restarts, updates and reinstalls.
  Save it as the user edits and implement `save_state()` on the page; the main window
  calls it when the app closes.
- **Secrets** (API keys, logins) go into `context.credentials`, never into settings.
- Add tests under `tests/` and an entry under `[Unreleased]` in `CHANGELOG.md`.
