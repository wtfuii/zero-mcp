# AGENTS.md

## What this is

`zero-mcp` — a **local MCP server over stdio** for the German broker **Finanzen.net ZERO**. It is a thin, typed MCP wrapper around the PyPI package **`finanzen-zero-api`** (import name `zero_api`), the unofficial client maintained at <https://github.com/wtfuii/zero-api>. All broker HTTP, login (Cognito SRP), sessions, models and 2FA live in that library; this repository only exposes them as MCP tools.

The server is started by an MCP host (Claude Desktop, Claude Code, Cursor, …) as a child process and speaks MCP on **stdout/stdin**. There is no HTTP listener, no web UI and no browser automation. The broker login is `https://mein.finanzen-zero.net`.

## Non-negotiable conventions

- **Strong typing everywhere**: full annotations, `mypy --strict` must pass; no untyped public functions. Use the library's Pydantic models rather than bare dicts for broker data.
- **Vertical slice architecture**: one module per broker slice under `src/zero_mcp/tools/` (`account`, `instrument`, `portfolio`, `watchlist`, `orders`, `sessiontan`). A slice owns its tool definitions, argument mapping and docstrings. There is no shared "services" layer; genuinely shared code is `config.py`, `client.py`, `errors.py` and `serialization.py` at package root.
- **Thin wrapper**: never re-implement broker endpoints, login, retries or 2FA here. Add missing capabilities to `finanzen-zero-api` first, then expose them. Do not add `httpx`/`requests` calls to this repository.
- **stdio only**: the server is launched locally. Do not add an HTTP/SSE transport unless the user explicitly asks. **stdout is the MCP protocol channel**: never print to stdout (the one stderr `print` in `main()` is for a startup configuration error), and never let a library write there. Diagnostics go to stderr via `logging`.
- **One lazy client**: tools obtain the broker client only through `ClientProvider.session()`, which holds a process-wide lock for the whole broker interaction. The client is created on the first tool call, never at import or server construction, so `tools/list` works without credentials. Keep the lazy creation and the serialization: the client keeps mutable session state (cookies, refresh, 2FA unlock) that must not be raced by concurrent MCP tool calls. Never call the client outside `session()`.
- **Credentials are environment variables only**: `ZERO_USERNAME` (the login e-mail address) and `ZERO_PASSWORD`. Never add a credentials file, CLI password flag, hard-coded secret, or log the password/username. `Settings.password` is a `SecretStr`; keep it that way.
- **Real money**: `place_order` and `cancel_order` are annotated `destructiveHint=True` and `readOnlyHint=False`. `ZERO_READ_ONLY=true` must remove every mutating tool from registration (and from the tool list), not merely reject calls. Never weaken this default behaviour. `ZERO_YOLO_MODE` (alias `YOLO_MODE`) is off by default and may only remove the model-level confirmation from the server instructions and order tool descriptions; it must not change annotations, read-only gating or the broker's 2FA, and a host's own approval prompt is outside the server's control.
- **Errors**: tool failures are translated in `errors.py` into `ToolError` with an actionable message (missing config, bad login, 2FA, broker rejection, network). Unknown exceptions stay unexpected tool errors.

## Repository layout

```
src/zero_mcp/
├── __init__.py          # version only
├── __main__.py          # python -m zero_mcp
├── server.py            # MCPServer construction, tool registration, main()
├── config.py            # pydantic-settings, ZERO_* env vars, lazy credential check
├── client.py            # ClientProvider protocol + lazy, lock-protected ZeroClient
├── errors.py            # broker exceptions → ToolError
├── serialization.py     # Pydantic model → JSON-safe dict (snake_case, Decimal→str)
├── py.typed             # PEP 561 marker
└── tools/
    ├── _annotations.py  # shared ToolAnnotations (READ_ONLY, ADDITIVE, DESTRUCTIVE)
    ├── _helpers.py      # ISIN normalization
    ├── account.py
    ├── instrument.py
    ├── portfolio.py
    ├── watchlist.py
    ├── orders.py
    └── sessiontan.py
tests/
├── conftest.py          # env isolation, mock client/provider, account fixture
├── test_config.py
├── test_packaging.py    # PyPI name/version and console script invariants
├── test_server.py       # registration, annotations, errors, real stdio subprocess
└── test_tools.py        # argument mapping and output per slice
```

## MCP SDK specifics

- The project uses **MCP Python SDK v2** (`mcp>=2.3,<3`), whose server class is `mcp.server.MCPServer` — **not** the v1 `FastMCP` import. `MCPServer` is generic; annotate it as `MCPServer[Any]`.
- Tools are plain synchronous functions registered with `@server.tool(annotations=...)`. They are blocking on purpose (HTTP + 2FA push), and the SDK runs them off the event loop.
- Structured output: return `dict[str, Any]` (never a bare list — the SDK wraps lists in `{"result": [...]}`). Lists are nested under a named key (`positions`, `orders`, `entries`, `devices`, `bars`) with a `count` where useful. Use `serialization.dump` / `dump_many`.
- Output keys are the library's **snake_case field names**, not broker camelCase aliases. Decimals are JSON strings to preserve precision; datetimes are ISO 8601. `get_chart` deliberately rebuilds each bar to expose `open` instead of the model's Python-only `open_`.
- Tool names have no prefix (`get_account`, `place_order`, …); the server is namespaced by the MCP host. Keep names verb-first and stable.
- `place_order` resolves a missing `mic_code` from the instrument's default trading venue (one extra master-data call); an explicit MIC skips that call.
- Tool descriptions are user-facing model instructions. The order tools combine their docstrings with the active confirmation or YOLO rule; they must state side effects, blocking behaviour and the confirmation requirement.
- When adding/removing/renaming a tool, update **all** of: registration, tests (`tests/test_server.py` tool sets), README tool table, and `READ_TOOLS`/`WRITE_TOOLS` expectations.

## Testing

- **No live broker calls in tests, ever.** No real credentials, no network. Tests use a `unittest.mock.Mock` client behind a fake `ClientProvider`; fixtures that need parsing use the real `zero_api` Pydantic models.
- The test suite also launches the real `python -m zero_mcp` over stdio with `ZERO_READ_ONLY=true`. This guards stdout cleanliness and the entrypoint; keep that test.
- Async tests use `pytest.mark.anyio` with the `asyncio` backend (`anyio_backend` fixture in `tests/conftest.py`). Do not add `pytest-asyncio`.
- Verify with `uv run mypy .` **then** `uv run pytest`. Both must be green; CI runs the same order.

## Tooling (chosen setup)

- Python **3.13+**, managed with **uv** (`uv sync`, `uv add <pkg>`, `uv run <cmd>`).
- `uv lock` is committed; CI uses `uv sync --locked`. After changing dependencies, run `uv lock` (or `uv sync`) and commit `uv.lock`.
- Runtime dependencies are deliberately few: `finanzen-zero-api`, `mcp`, `pydantic`, `pydantic-settings`. Do not add a web framework, browser, or HTTP client.
- Keep the `finanzen-zero-api` range (`>=0.1.0,<0.2.0`) aligned with the library's alpha status. If the library changes model shapes, update this wrapper and its tests rather than loosening validation.
- Build/verify packaging with `uv build`; CI also runs `uvx twine check --strict dist/*`.
- The PyPI distribution is **`finanzen-zero-mcp`** (import package `zero_mcp`, console script `zero-mcp`). The version is duplicated in `pyproject.toml` and `src/zero_mcp/__init__.py`; keep them equal. Releases are cut by pushing a `vX.Y.Z` tag, which runs `.github/workflows/release.yml` (PyPI Trusted Publishing). See `RELEASING.md` before changing the package name, version scheme or publish workflow.

## Status

Alpha (`0.1.0`). Tools exist for all slices the library currently supports: cash account, instrument search/detail/chart, depot positions, watchlist, orders, and 2FA order-execution status/devices/unlock. The conventions above were set by the owner. If code and this file disagree, fix the code or update this file — do not silently drift.
