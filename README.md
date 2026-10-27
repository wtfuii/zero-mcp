<h1 align="center">zero-mcp</h1>

<p align="center">
  <strong>MCP server for the German broker Finanzen.net ZERO</strong> 🇩🇪<br>
  Local stdio MCP server wrapping the unofficial Python client <code>finanzen-zero-api</code>.
</p>

<p align="center">
  <a href="https://github.com/wtfuii/zero-mcp/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/wtfuii/zero-mcp/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/finanzen-zero-mcp/"><img alt="PyPI" src="https://img.shields.io/pypi/v/finanzen-zero-mcp?logo=pypi&logoColor=white"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.13+" src="https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="https://mypy.readthedocs.io/en/stable/"><img alt="mypy: strict" src="https://img.shields.io/badge/mypy-strict-2A6DB2"></a>
  <a href="#development"><img alt="Tests: offline only" src="https://img.shields.io/badge/tests-offline%20only-success"></a>
  <a href="https://github.com/wtfuii/zero-mcp/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
  <a href="#project-status"><img alt="Status: alpha" src="https://img.shields.io/badge/status-alpha-orange.svg"></a>
</p>

> **Unofficial and unsupported.** Finanzen.net ZERO has no public API. This server wraps
> [`finanzen-zero-api`](https://github.com/wtfuii/zero-api), which mimics the broker's private
> web/app endpoints; they can change at any time. Use it only on an account you are allowed to
> automate, and never with money you cannot afford to lose. **Order tools move real money.**

`zero-mcp` turns the [`finanzen-zero-api`](https://github.com/wtfuii/zero-api) Python client into a
local [Model Context Protocol](https://modelcontextprotocol.io) server. It is published on PyPI as
[`finanzen-zero-mcp`](https://pypi.org/project/finanzen-zero-mcp/) and installs the `zero-mcp`
console script. An MCP host such as Claude Desktop, Claude Code or Cursor starts the server over
**stdio**, and an assistant can then read the account, search instruments, inspect charts, list depot
positions and watchlist entries, review orders, and — when explicitly enabled — place
or cancel orders. Per-order confirmation is required by default and can be disabled with
`ZERO_YOLO_MODE=true`.

```json
{
  "mcpServers": {
    "finanzen-zero": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/zero-mcp", "zero-mcp"],
      "env": {
        "ZERO_USERNAME": "you@example.com",
        "ZERO_PASSWORD": "your-password"
      }
    }
  }
}
```

---

## Contents

- [Features](#features)
- [Tools](#tools)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Connect an MCP host](#connect-an-mcp-host)
- [Usage examples](#usage-examples)
- [Authentication and 2FA](#authentication-and-2fa)
- [Output conventions](#output-conventions)
- [Safety and security](#safety-and-security)
- [Architecture](#architecture)
- [Development](#development)
- [Limitations](#limitations)
- [Project status](#project-status)
- [License](#license)

## Features

- **Full slice coverage.** Account, instrument search/master data/detail/charts, depot positions,
  watchlist, orders, and the app-push 2FA that unlocks order execution.
- **Local stdio only.** The MCP host spawns the process; there is no listening port, no browser and
  no Playwright/Selenium dependency.
- **Lazy login.** `tools/list` and server startup need no credentials. The first broker call logs in
  through Cognito SRP over plain HTTP; later calls reuse the in-memory session and refresh it
  automatically.
- **One serialized session.** All tools share a single lock-protected `ZeroClient`; broker calls are
  serialized so concurrent MCP tool requests cannot race the login, session refresh, 2FA unlock or
  order flow.
- **Typed end to end.** Pydantic models from `finanzen-zero-api`, `mypy --strict`, JSON-safe output
  with precision-preserving decimal strings and ISO 8601 timestamps.
- **Errors meant for a model.** Missing configuration, bad credentials, 2FA timeouts, broker
  rejections and network failures become actionable MCP tool errors instead of stack traces.
- **Read-only switch.** `ZERO_READ_ONLY=true` removes every mutating tool — orders, 2FA unlock and
  watchlist changes — from the exposed tool list.
- **Optional YOLO switch.** `ZERO_YOLO_MODE=true` (alias `YOLO_MODE`) tells the assistant to place
  and cancel orders without asking for per-order confirmation. Off by default; the broker's 2FA push
  still applies, and `ZERO_READ_ONLY` still wins.
- **Offline test suite.** A mocked broker client and a real stdio subprocess test; no live calls, no
  credentials needed in CI.

## Tools

Fifteen tools are registered in the default (trading-enabled) mode. Tools marked **write** are not
registered when `ZERO_READ_ONLY=true`.

| Tool | Kind | What it does |
|---|---|---|
| `get_account` | read | Cash account (Verrechnungskonto): buying/transfer power, IBAN, saldo, closing date. |
| `search_instruments` | read | Typeahead search by name, WKN or ISIN; per-asset-class hit counts. |
| `get_instrument` | read | Master record: asset class, trading state, fees, venues and MIC codes. |
| `get_instrument_detail` | read | Market data and fundamentals: quote, ranges, volume, profile, dividends. |
| `get_chart` | read | Price history for one scale (`Intraday` … `Maximum`). |
| `get_positions` | read | Depot positions with quantity, latest quote and entry quotes. |
| `get_watchlist` | read | Watchlist entries with quotes and metadata. |
| `list_orders` | read | Orders from one filter bucket (the broker's UI tabs) — `Open` (working, default), `Filled` (executed) or `Canceled` — with `has_next` pagination info. |
| `get_session_status` | read | Whether the session is unlocked for order execution. |
| `list_enrolled_devices` | read | Devices that can receive the 2FA push (with serials). |
| `add_to_watchlist` | write | Add an instrument by ISIN. |
| `remove_from_watchlist` | write | Remove an instrument by ISIN. |
| `unlock_order_execution` | write | Send the app push and wait for approval. |
| `place_order` | **write, real money** | Place a market/limit/stop-limit/OCO/trailing-stop order. |
| `cancel_order` | **write, real money** | Cancel an open order by its `order_id`. |

Order execution auto-unlocks the 2FA session when needed. Passing no `device_serial` uses
`ZERO_DEFAULT_DEVICE`, then the only enrolled device; with several devices and no default, the call
refuses rather than guessing. Order tools can block for up to 60 seconds while the push is approved.

By default the server instructions require the user's explicit confirmation before `place_order` or
`cancel_order`. Setting `ZERO_YOLO_MODE=true` removes that instruction and tells the model to trade
autonomously; it does not change the 2FA push or the host's own tool-approval prompt.

## Requirements

| Requirement | Why |
|---|---|
| **Python 3.13+** | The project targets 3.13 and is strictly typed. |
| **A Finanzen.net ZERO account** | Email + password login is the only supported method. |
| **The ZERO mobile app** | Needed only for order execution: the 2FA push is approved on a paired device. Read-only tools work without it. |
| **Network access to `mein.finanzen-zero.net`** | Every endpoint lives there. There is no sandbox. |
| **An MCP host** | Claude Desktop, Claude Code, Cursor, or any client that launches local stdio servers. |
| **uv (recommended)** | Installs dependencies and provides the `uv run` launch command; alternatively run the `.venv` console script directly. |

## Installation

From this checkout, with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/wtfuii/zero-mcp.git
cd zero-mcp
uv sync
```

`uv sync` installs the server and its dependencies into `.venv`. The MCP host should run the
`zero-mcp` console script through `uv run` (see [Connect an MCP host](#connect-an-mcp-host)).

With pip, once the package is published:

```bash
pip install finanzen-zero-mcp
zero-mcp
```

Or run it without installing, with [uv](https://docs.astral.sh/uv/):

```bash
uvx --from finanzen-zero-mcp zero-mcp
```

The PyPI distribution is `finanzen-zero-mcp`; the console script keeps the shorter name `zero-mcp`.
`zero-mcp` reads MCP messages from stdin and writes them to stdout. Running it directly in a
terminal will appear to hang; that is expected — an MCP host normally owns the process.

## Configuration

Configuration is read from environment variables, which the MCP host passes to the stdio process.

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `ZERO_USERNAME` | for any broker call | — | The ZERO login **e-mail address** (the client's `email`). |
| `ZERO_PASSWORD` | for any broker call | — | The ZERO account password. |
| `ZERO_DEFAULT_DEVICE` | no | — | 2FA device serial used when several devices are enrolled. |
| `ZERO_READ_ONLY` | no | `false` | `true` removes all mutating tools from the server. |
| `ZERO_YOLO_MODE` | no | `false` | `true` skips the per-order confirmation for real-money orders. Alias: `YOLO_MODE`. |

Startup and `tools/list` work without credentials; a tool call then fails with a clear
`not configured` message. Credentials are held in memory by the `ZeroClient`, are never written to
disk by this server, and are never logged. The password is stored as a `SecretStr`.

`ZERO_YOLO_MODE` (alias `YOLO_MODE`; the prefixed name wins if both are set) removes the
confirmation requirement from the server instructions and the order tools. It is ignored when
`ZERO_READ_ONLY=true`, because no order tools are registered then. The broker's app-push 2FA and any
tool-approval prompt configured in the MCP host are **not** affected: the server cannot override its
host.

> Environment variables are visible to the spawned process and (depending on the host) to other
> local processes. Do not commit an MCP config containing your password, and prefer
> `ZERO_READ_ONLY=true` unless you actively want trading tools.

## Connect an MCP host

### Claude Desktop / Cursor / generic JSON config

Use an **absolute path** to this checkout:

```json
{
  "mcpServers": {
    "finanzen-zero": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/zero-mcp", "zero-mcp"],
      "env": {
        "ZERO_USERNAME": "you@example.com",
        "ZERO_PASSWORD": "your-password",
        "ZERO_DEFAULT_DEVICE": "optional-device-serial",
        "ZERO_READ_ONLY": "false"
      }
    }
  }
}
```

- Claude Desktop: `claude_desktop_config.json` (Settings → Developer → Edit Config).
- Cursor: `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global).
- Any host that accepts `command`/`args`/`env`.

GUI hosts often start with a minimal `PATH` that does not contain `uv`. After `uv sync`, point the
config at the console script directly instead:

```json
{
  "mcpServers": {
    "finanzen-zero": {
      "command": "/absolute/path/to/zero-mcp/.venv/bin/zero-mcp",
      "env": {
        "ZERO_USERNAME": "you@example.com",
        "ZERO_PASSWORD": "your-password"
      }
    }
  }
}
```

On Windows the script is `.venv\Scripts\zero-mcp.exe`.

### Claude Code

```bash
claude mcp add finanzen-zero \
  --env ZERO_USERNAME=you@example.com \
  --env ZERO_PASSWORD=your-password \
  --env ZERO_READ_ONLY=false \
  -- uv run --directory /absolute/path/to/zero-mcp zero-mcp
```

### Read-only setup

Enable only the ten read tools and keep the trading surface out of the model's context entirely:

```json
{
  "mcpServers": {
    "finanzen-zero": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/zero-mcp", "zero-mcp"],
      "env": {
        "ZERO_USERNAME": "you@example.com",
        "ZERO_PASSWORD": "your-password",
        "ZERO_READ_ONLY": "true"
      }
    }
  }
}
```

Restart the MCP host after changing environment variables. The process logs its mode and whether
credentials are configured to **stderr** on startup, never to stdout.

## Usage examples

Once the server is connected, ask the assistant in natural language:

- “What is my current buying power and next closing date?”
- “Search for Apple and show me the one-year chart.”
- “Which positions do I hold and what are they worth at the latest quote?”
- “List my open orders and cancel order ID `GBR…`.” — requires confirmation and 2FA approval.
- “Place a limit buy for 1 share of Apple at €200 on gettex.” — the assistant repeats every
  parameter and asks for explicit confirmation before calling `place_order`, unless
  `ZERO_YOLO_MODE=true` is set.
- “I approved the push — check whether order execution is unlocked.”

The assistant discovers the account by calling the read tools. There is no separate login tool: the
first call logs in, and the shared session is reused afterwards.

## Authentication and 2FA

Login is handled entirely by `finanzen-zero-api`:

1. The first broker call performs a Cognito SRP login over HTTP through the broker's `/apic/authc`
   proxy. No browser and no API key are involved.
2. The one-hour IdToken is refreshed with the refresh-token cookie; a rejected session is
   re-established once and the request retried.
3. Sessions are in memory. Restarting the MCP server logs in again; no cookies are persisted.

Order execution additionally requires the app-push **session TAN** unlock:

1. `place_order` / `cancel_order` probe `is_authorized`; when locked they request a push to the
   configured device and wait for approval.
2. `unlock_order_execution` exposes that step explicitly, with a configurable timeout and no-op when
   already unlocked.
3. If exactly one device is enrolled it is used automatically. With several devices, set
   `ZERO_DEFAULT_DEVICE` or call `list_enrolled_devices` and pass a serial.

Keep the host clock synchronized (NTP): SRP signs a UTC timestamp, and large clock skew makes the
login fail.

## Output conventions

- Tool results are JSON objects. Lists are nested under a descriptive key (`positions`, `orders`,
  `entries`, `devices`, `bars`) and usually come with a `count`.
- Keys use the Python client's **snake_case** field names (the names documented in the
  `finanzen-zero-api` README), not the broker's camelCase wire aliases.
- Account, position, order and watchlist amounts are **decimal strings** (e.g. `"1000.50"`) so
  precision survives the JSON round-trip. Parse them before doing arithmetic. Market-data values
  such as chart bars and instrument detail quotes keep the broker's wire floats and are numbers.
- Timestamps are ISO 8601 strings; dates use `YYYY-MM-DD`. Account amounts are EUR; instrument and
  order prices use the instrument's quote currency (`quote_currency_code`), not necessarily EUR.
- Failures are MCP `isError` results with a human/model-readable message, including the broker's
  HTTP status, error code and field errors when available.

## Safety and security

- **Real orders.** `place_order` and `cancel_order` are marked `destructiveHint` and
  `readOnlyHint=false`. A market order can fill immediately and cannot be undone. Only enable them
  when you intend to let the assistant trade. If a `place_order` call fails after submission
  (timeout or network error), check `list_orders` before retrying — the order may already exist.
- **YOLO mode is a footgun.** `ZERO_YOLO_MODE=true` (alias `YOLO_MODE`) removes the model-level
  requirement to ask before placing or cancelling an order. It does not bypass the broker's 2FA push,
  it does not override `ZERO_READ_ONLY`, and it does not change an MCP host's own approval prompt —
  configure that in the host separately. Use it only on an account and with amounts you can afford
  to trade without a human in the loop.
- **Read-only by default is a choice.** The server defaults to full functionality to mirror the
  library. Set `ZERO_READ_ONLY=true` for a safe default; this also removes the 2FA unlock tool.
- **No credential storage.** Passwords arrive via environment variables and stay in memory. This
  server does not read `.env` files, keychains or config files. Treat MCP host config files as
  secrets when they contain `ZERO_PASSWORD`.
- **2FA is not bypassed.** Order execution still requires approval on the paired phone. The server
  only automates the request/poll/verify flow.
- **Unofficial.** The broker can change or block these private endpoints at any time. Schema drift is
  surfaced as a tool error rather than silently wrong data.
- **Your responsibility.** Automating a brokerage account may violate the broker's terms. Use only
  an account you are allowed to automate.

## Architecture

```
src/zero_mcp/
├── server.py          # MCPServer (MCP SDK v2), dynamic tool registration, stdio main()
├── config.py          # ZERO_* env settings, lazy credential validation
├── client.py          # ClientProvider + lazy, lock-protected shared ZeroClient
├── errors.py          # zero_api/httpx exceptions → actionable ToolError
├── serialization.py   # Pydantic model → JSON-safe dict
├── __main__.py        # python -m zero_mcp
└── tools/             # vertical slices, one module per broker area
    ├── account.py
    ├── instrument.py
    ├── portfolio.py
    ├── watchlist.py
    ├── orders.py
    └── sessiontan.py
```

The MCP server is deliberately thin: it owns argument mapping, error translation, tool annotations,
read-only gating and the confirmation/YOLO instructions. Everything else — HTTP, SRP login, refresh,
2FA, Pydantic models — belongs to [`finanzen-zero-api`](https://github.com/wtfuii/zero-api).

## Development

```bash
uv sync
uv run mypy .          # strict; run first
uv run pytest          # offline; no broker calls
uv build               # wheel + sdist
uvx twine check --strict dist/*
```

To exercise the server by hand, launch it through any MCP client or the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run --directory . zero-mcp
```

Set `ZERO_USERNAME`/`ZERO_PASSWORD` in the inspector's environment only if you intend to make live
(read-only) calls. There is **no live smoke test in CI** and tests must never contact the broker.

See [AGENTS.md](AGENTS.md) for the architecture rules, MCP SDK conventions and contribution
constraints. Adding a tool means touching registration, tests, the README tool table and (if it
mutates state) the read-only gate.

Releases are cut from a `vX.Y.Z` tag and published to PyPI through Trusted Publishing; the workflow
also attaches the wheel and sdist to a GitHub release. See [RELEASING.md](RELEASING.md) for the
one-time registry setup and the release checklist.

## Limitations

- **Unofficial, alpha.** The underlying client is `0.1.x`; the wrapper pins
  `finanzen-zero-api>=0.1.0,<0.2.0`. Model or endpoint changes can break tool output until the
  wrapper is updated.
- **stdio only.** No HTTP/SSE transport, no multi-user server, no OAuth. One process, one account.
- **No order modification.** The broker client supports placing and cancelling, not amending.
- **Blocking 2FA.** `place_order`, `cancel_order` and `unlock_order_execution` wait for the phone
  approval; MCP hosts with a short tool timeout may abort the call before the push is accepted.
- **No streaming quotes.** Charts and details are snapshots returned by the private endpoints.
- **No pagination helper.** `list_orders` returns one page and `has_next`; the page size is bounded
  by the tool's `size` argument (max 1000).
- **Unknown rate limits.** The broker publishes none; avoid tight polling loops.

## Project status

Alpha (`0.1.0`). All slices currently supported by `finanzen-zero-api` are wrapped: account,
instruments, portfolio, watchlist, orders and session TAN/2FA. The tool surface may change between
minor versions while the wrapper stabilizes. Pin the version you depend on.

## License

MIT — see [LICENSE](LICENSE). This project is not affiliated with Finanzen.net, Finanzen.net ZERO,
or Baader Bank.
