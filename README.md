<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude-Haiku%204.5%20|%20Sonnet%205%20|%20Opus%204.8-7b46fe?logo=anthropic" alt="Claude" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
  <img src="https://img.shields.io/badge/SSE-Streaming-brightgreen" alt="SSE" />
</p>

<h1 align="center">AI 群聊 — WeChat-style Multi-Room Chatroom</h1>
<p align="center">
  <em>像微信一样建群、拉 AI 角色进群、写群公告，然后一起聊天。</em>
  <br /><a href="#quick-start">Quick Start</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#usage">Usage</a>
  <br /><b>Languages:</b> <a href="README.md">English (current)</a> · <a href="README.zh-CN.md">中文</a>
</p>

---

## Overview

**AI 群聊** turns a single AI chat into a **WeChat-style multi-room group chat platform**. Create multiple chat groups, each with its own name, roster of AI roles (pulled from an address book or created on the fly), group announcement, and conversation history — all persisted in your browser.

- **Left sidebar**: group list with search — switch between rooms instantly
- **Room management**: create, edit, and delete groups; each group has its own roles, announcement, rules, and chat history
- **Contact library**: preset AI role definitions (研究员 / 代码手 / 创意家 / 评论家 / 编剧 / 历史学家) that you can pull into any group
- **Custom roles per room**: one-off roles that belong only to a specific group
- **Group announcement + rules**: the announcement is shown as a banner at the top of the chat and prepended to every AI role's system prompt; supplementary rules go after it
- **@Mention chaining**: type `@角色名` to direct specific roles to speak next
- **SSE token streaming**: every AI reply streams token-by-token with a blinking cursor
- **Stateless backend**: all room config lives in `localStorage`; the server receives everything it needs in each POST

### Why?

WeChat-style rooms let you manage **multiple AI discussion panels** independently: a code-review room, a brainstorming room, a writing workshop — each with its own roster and rules, all in the same UI you already know how to use. Switching context is one click, no config reloading needed.

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

If no env key is set, the UI will prompt you for one on first launch — paste it into the API Key modal and it's stored in the browser's `localStorage` only (never sent anywhere except directly to Anthropic).

A default group **代码评审小组** is seeded with two roles (代码手 + 审查员) so you can start chatting immediately. The contact library also ships with 6 preset AI roles you can pull into any new group.

---

## Features

| Capability | Description |
|---|---|
| **多房间 (Multi-Room)** 🏠 | Create unlimited chat groups in the left sidebar. Each has independent name, members, announcement, rules, and history. Search and switch in one click. |
| **通讯录 (Contact Library)** 📇 | 6 preset AI roles (研究员 / 代码手 / 创意家 / 评论家 / 编剧 / 历史学家) — pull any into a group, or create custom roles per room. |
| **群公告 (Group Announcement)** 📢 | A notice shown as a banner at the top of the chat and prepended to every AI role's system prompt. Combined with optional supplementary rules. |
| **群成员管理** 👥 | Pull-from-address-book picker with search, plus per-room custom roles. Click any member chip to edit its prompt and model. |
| **Mixed Model Roster** 🧠 | Each role can use a different Claude tier — Haiku for fast cheap replies, Sonnet for balanced work, Opus for hard reasoning, Fable for variety. Mix freely within one group. |
| **@Mention Chaining** 🔗 | Type `@角色名` in your message to invite specific roles to speak next — the orchestrator re-orders the turn queue accordingly. Roles can @mention each other too. |
| **SSE Token Streaming** ⚡ | Each role's reply streams token-by-token via Server-Sent Events — watch the discussion unfold live, with a blinking cursor on the active role. |
| **Stop Button** ⛔ | Hit stop mid-stream — the SSE connection is aborted via `AbortController` and partial replies are kept. |
| **Markdown Rendering** ✨ | Headings, lists, code blocks, tables, blockquotes, links, inline code — all rendered safely (HTML escaped before transforms). |
| **History Persistence** 💾 | Every group's full history survives page refresh in `localStorage`. Clear per-group with the 「清空记录」 button, or delete a group entirely with 「退出群聊」. |
| **Bring-Your-Own-Key** 🔑 | Paste your Anthropic key in the UI (stored locally) or set `ANTHROPIC_API_KEY` server-side. |
| **Zero Backend State** ☁️ | The FastAPI server is stateless — every request carries the full room config and history. Scale horizontally by just running more processes. |

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

### Creating a Group (WeChat-style)

1. Click **＋** in the top-left of the sidebar → **发起群聊** modal opens
2. Enter a group name (e.g. `代码评审小组`)
3. Write the **群公告** (group announcement) — this is prepended to every AI role's system prompt on every turn, and shown as a banner at the top of the chat
4. (Optional) Add **补充规则** for finer coordination cues appended after the announcement
5. **Pull members from 通讯录** — click 「＋ 从通讯录添加」 to open the contact picker, then click any preset role to add it to the group
6. **Or create custom roles** just for this room — click 「＋ 新建本群专属角色」 and define name / system prompt / model
7. Click **创建群聊** — the new group appears at the top of the sidebar

### Group Announcement vs. Supplementary Rules

- **群公告** (announcement): the "constitution" of the room — high-level coordination. Example: *"每轮最多 3 次模型间对话，最后必须给出最终结论。用中文回答；不要复述别人已经说过的话。"*
- **补充规则** (rules): finer cues. Example: *"#代码手 在写代码前先让 #研究员 确认需求"* (the `#` prefix is stripped before being shown to the model so the discussion isn't noisy)

Backend merges them as: `【群公告】\n{announcement}\n\n【补充规则】\n{group_rules}` (whichever sections are empty are dropped).

### Editing / Deleting a Room

- In the chat header, click **⚙ 设置** to reopen the room modal for edits
- **清空记录** wipes the conversation history but keeps the room
- **退出群聊** deletes the room entirely

### Switching Rooms

Click any room card in the left sidebar to switch. Each room keeps its own roles, announcement, rules, and full history. Active stream is aborted on switch.

### Example Rooms

- **Code review panel**: `代码手` (Sonnet, pragmatic engineer) + `审查员` (Opus, meticulous reviewer) + `架构师` (Sonnet, big-picture thinker). Group announcement: "审查员必须挑出至少两个问题，否则投票放弃方案。"
- **Writing workshop**: `主笔` (Opus) + `编辑` (Sonnet) + `校对` (Haiku, fast). Group announcement: "主笔先写一段，编辑提建议，校对最后改错别字。每轮 3 次对话后输出定稿。"
- **Debate club**: `正方` (Sonnet) + `反方` (Sonnet) + `评委` (Opus). Group announcement: "正方反方各陈述 1 次，评委给出胜负判决。"

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
| `ANTHROPIC_MAX_TOKENS` | `4096` | Max output tokens per AI reply |

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
