<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude-Haiku%204.5%20|%20Sonnet%205%20|%20Opus%204.8-7b46fe?logo=anthropic" alt="Claude" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
  <img src="https://img.shields.io/badge/SSE-Streaming-brightgreen" alt="SSE" />
</p>

<h1 align="center">Claude 多角色聊天室</h1>
<p align="center">
  <em>Multi-Role Chatroom — multiple Claude instances, each with its own personality and model, conversing together in real time.</em>
  <br /><a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#usage">Usage</a>
</p>

---

## Overview

**Claude 多角色聊天室** turns a single AI chat into an **intelligent discussion panel**. You define several roles — each with a name, a system prompt, and a Claude model — then send them a message. Every role replies in turn, can @mention others for chained follow-ups, and follows a natural-language group rule you set.

Built on FastAPI and the Anthropic SDK, with a pure-JavaScript frontend that streams each role's response token-by-token via Server-Sent Events. No database, no WebSocket, no model orchestration platform — just an orchestrator that schedules each role's Claude call and serialises the SSE stream.

### Why?

Single-agent chatbots answer your question and stop. But many real tasks — brainstorming a feature, stress-testing a design, writing + reviewing code — benefit from **multiple perspectives in the same thread**: a sceptical reviewer, a pragmatic engineer, a domain expert. Hand-rolling that as separate prompts is tedious. This project makes it a first-class UI: configure once, then watch the conversation unfold.

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
# export ANTHROPIC_API_KEY="sk-ant-..."         # bash / zsh

uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

No env key? The UI will prompt you for one on first launch — paste it into the API Key modal and it's stored in the browser's `localStorage` only (never sent anywhere except directly to Anthropic).

Two default roles — **研究员** (Haiku) and **代码手** (Sonnet) — are seeded automatically so you can start chatting immediately. Edit, add, or delete them via the roles panel on the left.

---

## Features

| Capability | Description |
|---|---|
| **Multiple Roles** 🎭 | Define any number of roles, each with its own name, system prompt, and Claude model. Roles reply in registration order; a `MAX_TURNS=20` ceiling prevents infinite loops. |
| **Mixed Model Roster** 🧠 | Each role can use a different Claude tier — Haiku for fast cheap replies, Sonnet for balanced work, Opus for hard reasoning, Fable for variety. Mix freely within one conversation. |
| **@Mention Chaining** 🔗 | Type `@角色名` in your message to invite specific roles to speak next — the orchestrator re-orders the turn queue accordingly. Works mid-conversation too: roles can @mention each other. |
| **Group Rules** 📜 | A natural-language "group公告" applied to every role on every turn. Use it to set turn limits, coordination rules ("don't repeat what others said", "agree on a conclusion before ending"). |
| **SSE Token Streaming** ⚡ | Each role's reply is streamed token-by-token via Server-Sent Events — watch the discussion unfold live, with a blinking cursor on the active role. |
| **Streaming Stop Button** ⛔ | Send a long message and regret it? Hit the stop button — the SSE connection is aborted via `AbortController` and partial replies are preserved in history. |
| **Markdown Rendering** ✨ | Headings, lists, code blocks, tables, blockquotes, links, inline code — all rendered safely. HTML is escaped before markdown transforms, so model output cannot inject markup. |
| **History Persistence** 💾 | Full conversation history survives page refresh, stored in `localStorage`. Clear it with one button when you want a fresh slate. |
| **Role Import / Export** 📥📤 | Configure roles + group rules once, export to JSON, share with teammates or check into a repo. Import via the file picker. |
| **Bring-Your-Own-Key** 🔑 | Paste your Anthropic key in the UI (stored locally, never sent to any third party) or configure it server-side via `ANTHROPIC_API_KEY`. |
| **Zero Backend State** ☁️ | The FastAPI server is stateless — every request carries the full room config and history. Scale horizontally by just running more processes; sticky sessions not needed. |

---

## Architecture

```
┌──────────────────────────┐       SSE (text/event-stream)       ┌─────────────────────────┐
│  Browser (static/)        │  <────────────────────────────────  │  FastAPI (app/main.py)  │
│                          │      POST /api/chatroom/send         │                         │
│  index.html              │                                     │  chatroom.py (router)   │
│  styles.css              │                                     │  orchestrator/          │
│  app.js                  │                                     │   ├── room.py           │
│   - role cards           │                                     │   │   (Role, RoomConfig)│
│   - chat bubbles         │                                     │   ├── mentions.py       │
│   - @mention popup       │                                     │   │   (parse / strip)  │
│   - SSE stream reader    │                                     │   └── engine.py         │
│   - localStorage state   │                                     │       (turn scheduler) │
└──────────────────────────┘                                     └──────────┬──────────────┘
                                                                            │
                                                                ┌───────────▼─────────────┐
                                                                │  anthropic SDK          │
                                                                │  client.messages.stream │
                                                                │  (one call per role)    │
                                                                └─────────────────────────┘
```

### Turn Scheduling (`orchestrator/engine.py`)

1. Take the user message + role config + history + group rules
2. **Resolve mentions**: scan the message for `@role_name`; if any are found, those roles speak next (in mention order); otherwise all roles speak in registration order
3. For each speaking role in turn:
   - Build the system prompt = `group_rules + this role's system_prompt`
   - Build the message thread: prior history + the user message (with `@name` prefixes stripped where appropriate so models don't parrot the convention back)
   - Call `client.messages.stream(...)` and yield `text` SSE events as tokens arrive
   - On completion, append the role's reply to history and proceed to the next speaker
4. Emit `role_start` / `text` / `role_end` / `done` events so the frontend can render role transitions cleanly

Turn cap is `MAX_TURNS = 20` — a backstop against a runaway mention cycle, not normally hit in practice.

### SSE Event Protocol

| Event | Payload | Meaning |
|---|---|---|
| `role_start` | `{"role": "研究员"}` | A role is about to start speaking; frontend creates an empty bubble |
| `text` | `{"role": "研究员", "delta": "..."}` | A streamed token chunk for the active role |
| `role_end` | `{"role": "研究员"}` | The role finished; finalise its bubble and persist to history |
| `error` | `{"message": "..."}` | Something went wrong (auth, network, model error) |
| `done` | `null` | Whole turn complete; close the stream |

---

## Project Structure

```
.
├── README.md
├── LICENSE
├── requirements.txt                 # anthropic, fastapi, uvicorn, httpx, python-dotenv — that's it
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app, static mount, health check
│   ├── chatroom.py                  # POST /api/chatroom/send — SSE route
│   ├── config.py                    # env loading + default API key/model
│   └── orchestrator/
│       ├── __init__.py
│       ├── room.py                  # Role / RoomConfig / Message dataclasses
│       ├── mentions.py              # @mention parser + prefix stripper
│       └── engine.py                # turn scheduler + Anthropic streaming
└── static/
    ├── index.html                   # chatroom layout, modals, role panel
    ├── styles.css                   # bubble styles, role colors, modal
    └── app.js                       # SSE reader, role CRUD, mention popup, markdown
```

---

## Usage

### Configuration

For each role, set:

- **Name** — what others @mention to invite it; also displayed as the bubble author
- **System prompt** — the role's persona and instructions ("you are a sceptical reviewer…")
- **Model** — pick from the dropdown (Haiku / Sonnet / Opus / Fable); custom model IDs also accepted

The **group rule** (群公告) is prepended to every role's system prompt on every turn — it's the shared "constitution" of the room. Use it for things like:

- *"#代码手 在写代码前先让 #研究员 确认需求"*
- *"每轮最多 3 次模型间对话，然后必须给出最终结论"*
- *"用中文回答；不要复述别人已经说过的内容"*

### Example Rooms

- **Code review panel**: `代码手` (Sonnet, pragmatic engineer) + `审查员` (Opus, meticulous reviewer) + `架构师` (Sonnet, big-picture thinker). Group rule: "审查员必须挑出至少两个问题，否则投票放弃方案。"
- **Writing workshop**: `主笔` (Opus) + `编辑` (Sonnet) + `校对` (Haiku, fast). Group rule: "主笔先写一段，编辑提建议，校对最后改错别字。每轮 3 次对话后输出定稿。"
- **Debate club**: `正方` (Sonnet) + `反方` (Sonnet) + `评委` (Opus). Group rule: "正方反方各陈述 1 次，评委给出胜负判决。"

### @Mention Behaviour

- In your user message: `@研究员 你觉得呢？@代码手 也说说` → 研究员 speaks first, then 代码手 — others are skipped this turn
- Roles see prior turns with @mentions in them, so they understand who was addressing whom
- The orchestrator strips leading `@role_name` prefixes from role replies so the transcript doesn't pile up redundant mentions

---

## Configuration Reference

### API Key Precedence

```
UI input (localStorage)         ← submitted per-request, beats env
   ↓ if absent
ANTHROPIC_API_KEY env var       ← set in shell or .env
   ↓ if absent
401 from Anthropic              ← happens on first send
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key; required if UI doesn't supply one |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Fallback model for roles that don't specify one |

Per-role model selection in the UI always wins over `ANTHROPIC_MODEL`.

---

## Roadmap

- [ ] Persisted rooms (server-side session storage so a refresh keeps partial multi-role turns)
- [ ] Branching conversations (fork from any message into a what-if thread)
- [ ] Token + cost meter per role per conversation
- [ ] Multi-user rooms with authenticated participants

---

## FAQ

**Q: Do I need an Anthropic API key?**  
A: Yes — every role's reply is a real Claude API call. Get one at [console.anthropic.com](https://console.anthropic.com).

**Q: How much does a conversation cost?**  
A: Each role's turn is one Claude call with the full history as context. With default roles (Haiku + Sonnet) and short conversations, a few cents. With Opus roles and long histories, noticeably more — Opus roles are the dominant cost driver.

**Q: Can roles call tools or browse the web?**  
A: Not in this version — the orchestrator is pure chat. Tool use may return in a future release, scoped per-role.

**Q: What if a role gets stuck mentioning itself forever?**  
A: The `MAX_TURNS = 20` ceiling in `engine.py` breaks any cycle. Tune it to your taste.

**Q: Is this production-ready?**  
A: No — it's a demo with no auth, no rate limiting, no abuse protection. Run it locally or behind your own auth layer. The API key in the UI never leaves the browser except to Anthropic.

---

## Contributing

Contributions are welcome! Please open an issue first to discuss major changes.

1. Fork → feature branch → commit → PR
2. Keep diffs focused; the codebase is intentionally small
3. Run `python -m uvicorn app.main:app --reload` to verify locally before submitting

---

## License

[MIT](LICENSE) — use it, modify it, share it.
