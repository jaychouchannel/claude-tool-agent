<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude-Haiku%204.5%20|%20Sonnet%205%20|%20Opus%204.8-7b46fe?logo=anthropic" alt="Claude" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
  <img src="https://img.shields.io/badge/Status-Demo-yellow" alt="Status" />
</p>

<h1 align="center">Claude Tool-Use Agent</h1>
<p align="center">
  An LLM tool-calling agent demo built with Claude API &amp; FastAPI — chat interface, live SSE streaming, multi-tool orchestration.
  <br /><a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#add-a-new-tool">Add a Tool</a>
</p>

---

## Quick Start

```bash
git clone https://github.com/<YOUR_USER>/claude-tool-agent.git
cd claude-tool-agent

python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

# Option A: set API key in environment
$env:ANTHROPIC_API_KEY = "sk-ant-..."          # PowerShell
# export ANTHROPIC_API_KEY="sk-ant-..."        # bash / zsh

uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).  
No env key? Click the gear icon in the top-right corner and paste your key into the UI.

---

## Features

| Capability | Description |
|---|---|
| **Web Search** 🔍 | DuckDuckGo HTML scraping — no API key or registration needed. Returns top results with titles, snippets, and links. |
| **Python Code Execution** 🐍 | Runs arbitrary Python snippets via `subprocess` with a 10‑second timeout and 5 KB output truncation. |
| **Wikipedia Lookup** 📚 | Fetches the best-matching Wikipedia page summary via the public REST API — great for encyclopedic facts, biographies, geography. |
| **File Read** 📄 | Reads text files inside the project root (sandboxed — paths outside the project are rejected; binary extensions are blocked). |
| **Multi‑Turn Tool Loop** 🔄 | Claude decides whether to call one tool, multiple tools, or chain tools across multiple rounds — all within a single conversation. |
| **SSE Real‑Time Streaming** ⚡ | Every text token, tool call, and tool result streams to the browser as it happens via Server‑Sent Events. |
| **LangChain Endpoint** 🔌 | An alternative `/api/chat/langchain` route runs the same tools through `langchain-anthropic`'s `create_react_agent` — compare two implementations of the same agent with one click. |
| **Bring‑Your‑Own‑Key** 🔑 | Input your API key in the UI (saved to `localStorage`) or configure it server‑side via environment variable. |
| **Model Switch** 🧠 | Defaults to `claude-haiku-4-5-20251001` (fast & cheap). Override with `ANTHROPIC_MODEL=claude-sonnet-5` or `claude-opus-4-8`. |

> ⚠️ **Security Notice**: The `run_python_code` tool executes code via `subprocess` with minimal sandboxing. It is **not production‑grade isolation**. For local learning and demos only — **do not deploy to a public internet endpoint without authentication**.

---

## Screenshots

*Coming soon — add a screenshot of the chat UI to `static/screenshot.png` and it will appear here.*

---

## Architecture

```
┌─────────────────────┐         SSE (text/event-stream)      ┌───────────────────────┐
│  Browser (index.html)│  <────────────────────────────────  │  FastAPI (main.py)     │
│  - ChatGPT-style UI   │       POST /api/chat               │  - POST /api/chat      │
│  - fetch + Readable   │                                     │  - GET  / (static)     │
│    Stream parser      │                                     │  - GET  /api/health    │
└─────────────────────┘                                     └────────┬──────────────┘
                                                                     │
                                                            ┌────────▼──────────┐
                                                            │  Agent (agent.py)  │
                                                            │                    │
                                                            │  1. messages.create │
                                                            │  2. if tool_use →   │
                                                            │     run tool        │
                                                            │  3. append result   │
                                                            │  4. repeat (max 10) │
                                                            │  5. SSE yield       │
                                                            └────────┬──────────┘
                                                                     │
                                               ┌─────────────────────┼─────────────────────┐
                                               │                     │                     │
                                      ┌────────▼────────┐   ┌───────▼─────────┐   ┌───────▼─────────┐
                                      │  tools/registry  │   │  tools/search   │   │ tools/code_runner│
                                      │  (dispatch)      │   │ (DuckDuckGo)    │   │ (subprocess)     │
                                      └──────────────────┘   └─────────────────┘   └─────────────────┘
```

### Event Flow

1. User types a message in the browser
2. Frontend sends `POST /api/chat` with `{message, api_key?, history?}`
3. `agent.py` calls Claude API with tool definitions
4. If Claude responds with text → yield `text` SSE event → rendered in chat bubble
5. If Claude responds with `tool_use` → yield `tool_use` SSE event → tool card shown, tool executed server‑side
6. Tool result → yield `tool_result` SSE event → result card shown, fed back to Claude
7. Repeat steps 4–6 until Claude stops (`end_turn`) or iteration limit (10) reached
8. Yield `done` SSE event → session ends

---

## Project Structure

```
.
├── README.md                          # This file
├── LICENSE                            # MIT License
├── requirements.txt                   # Python dependencies
├── .env.example                       # API key template
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI application & SSE routes
│   ├── agent.py                       # Agentic loop (Claude + tool orchestration)
│   ├── langchain_agent.py             # LangChain alternative agent (create_react_agent)
│   ├── config.py                      # Environment variable loading & model selection
│   └── tools/
│       ├── __init__.py
│       ├── registry.py                # Tool registry: name → run function, Anthropic tool specs
│       ├── search.py                  # web_search tool (DuckDuckGo HTML scraping)
│       ├── code_runner.py             # run_python_code tool (subprocess execution)
│       ├── wikipedia.py               # wikipedia_search tool (Wikipedia REST API summary)
│       └── file_read.py               # file_read tool (sandboxed text-file reader)
└── static/
    └── index.html                     # Single‑page chat frontend (HTML + CSS + JS)
```

---

## LangChain vs Native Agent

Two endpoints expose the same tool suite, letting you compare approaches side-by-side:

| Endpoint | Backend | When to use |
|---|---|---|
| `POST /api/chat` | `app/agent.py` — hand-rolled tool loop over the raw Anthropic SDK | Zero extra dependencies; tight control over the loop; best for learning the bare tool-use API |
| `POST /api/chat/langchain` | `app/langchain_agent.py` — `langchain-anthropic`'s `create_react_agent` | Compare idioms; reuse LangChain ecosystem (loaders, memory, chains); useful when planning to swap in other LangChain-compatible tools |

Both produce the same SSE event stream (`text`, `tool_use`, `tool_result`, `error`, `done`) — the frontend doesn't need to know which backend is in use.

---

## Try It

Click the examples below to see the agent orchestrate tools in real time:

> - *"Search for the latest Anthropic model releases"* → triggers `web_search`
> - *"Calculate 2 to the power of 100"* → triggers `run_python_code`
> - *"What is the population of Tokyo?"* → triggers `wikipedia_search`
> - *"Read app/config.py and explain how model selection works"* → triggers `file_read`
> - *"Search for today's BTC price and convert it to CNY"* → triggers `web_search` → `run_python_code` in a chain

---

## Configuration

### API Key Precedence

```
UI input box (submitted per‑request)  →  ANTHROPIC_API_KEY environment variable  →  401 error
```

### Model Selection

```bash
export ANTHROPIC_MODEL="claude-haiku-4-5-20251001"   # default — fastest, cheapest
export ANTHROPIC_MODEL="claude-sonnet-5"              # balanced — smarter, still fast
export ANTHROPIC_MODEL="claude-opus-4-8"              # most capable — handle complex tool chains
```

No restart needed — the change takes effect on the next chat request.

---

## Add a New Tool

Extending the agent is a three‑step process:

**1. Create the tool file** (`app/tools/my_tool.py`):

```python
TOOL_SPEC = {
    "name": "my_tool",
    "description": "What this tool does.",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
        },
        "required": ["param1"],
    },
}

def run(param1: str) -> str:
    # Your tool logic — return a string for Claude to read
    return f"Result: {param1}"
```

**2. Register it** in `app/tools/registry.py`:

```python
from . import my_tool

_TOOLS[my_tool.TOOL_SPEC["name"]] = my_tool.run
# Also add my_tool.TOOL_SPEC to the list in get_tool_specs()
```

**3. Done** — the agent loop discovers and dispatches tools automatically. No routing changes needed.

---

## FAQ

**Q: Do I need an API key to run this?**  
A: Yes — you need an [Anthropic API key](https://console.anthropic.com). The web search tool itself is free (DuckDuckGo), but every agent request calls Claude under the hood.

**Q: Is the `run_python_code` tool safe?**  
A: It runs `subprocess` with a 10‑second timeout and 5 KB output truncation. This is **not** a secure sandbox. Use it for learning and demos on your local machine. Do **not** deploy this to a public endpoint without authentication and real sandboxing (e.g., Docker containers, gVisor, or a serverless sandbox).

**Q: Can I use this in production?**  
A: Not as‑is. It lacks authentication, rate limiting, proper sandboxing, and observability. Treat it as a reference implementation for learning the tool‑calling pattern.

**Q: What if the agent gets stuck in a loop?**  
A: The loop caps at 10 iterations. If Claude keeps calling tools, you'll see the cycle continue until it either produces a final answer or hits the limit and returns the last response.

---

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add some feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

[MIT](LICENSE) — use it, modify it, share it.
