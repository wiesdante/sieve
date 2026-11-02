# Adding a tool

Every workflow in Sieve is a **tool**: a class that builds one page in the app.

## 1. Create the module

Create `src/sieve/tools/<tool_name>.py`:

```python
from PySide6.QtWidgets import QLabel

from sieve.context import AppContext
from sieve.tools.base import Tool
from sieve.ui.widgets import Page


class ExampleTool(Tool):
    id = "example"                  # stable, never rename after release
    name = "Example"
    description = "One line explaining what the tool does."
    category = "Scraping"

    def create_widget(self, context: AppContext):
        page = Page(self.name, self.description)
        page.content.addWidget(QLabel("Tool UI goes here"))
        page.finish()
        return page
```

## 2. Register it

Add an instance to `all_tools()` in `src/sieve/tools/__init__.py`. The order of
the list is the order in the sidebar.

## Guidelines

- **Never block the UI thread.** Run network and file work with
  `sieve.ui.tasks.run_in_background`; it supports progress reporting and cancellation.
- **Use the shared proxy pool** via `context.proxy_pool()` instead of tool-specific
  proxy settings. `Proxy.for_requests()` and `Proxy.for_playwright()` return the
  right format for each library.
- **Browser automation** should use the system Microsoft Edge
  (`channel="msedge"` in Playwright) so no browser has to be bundled.
- **Keep logic separate from widgets** so it can be unit-tested without Qt.
- **Secrets** (API keys, logins) go into `context.credentials`, never into settings.
- Add tests under `tests/` and an entry under `[Unreleased]` in `CHANGELOG.md`.
