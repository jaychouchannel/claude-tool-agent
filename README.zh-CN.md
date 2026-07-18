<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude-Haiku%204.5%20|%20Sonnet%205%20|%20Opus%204.8-7b46fe?logo=anthropic" alt="Claude" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
  <img src="https://img.shields.io/badge/SSE-Streaming-brightgreen" alt="SSE" />
</p>

<h1 align="center">AI 群聊 — 微信风多人聊天室</h1>
<p align="center">
  <em>像微信一样建群、拉 AI 角色进群、写群公告，然后一起聊天。</em>
  <br /><a href="#quick-start">快速开始</a> ·
  <a href="#features">功能</a> ·
  <a href="#architecture">架构</a> ·
  <a href="#usage">使用</a>
  <br /><b>语言：</b> <a href="README.md">English</a> · <a href="README.zh-CN.md">中文（当前）</a>
</p>

---

## 概述

**AI 群聊** 把单一 AI 对话变成了 **微信风的多房间群聊平台**。你可以创建多个聊天群，每个群都有自己的名字、AI 角色名单（从通讯录拉入或现场创建）、群公告与聊天历史 —— 全部保存在浏览器本地。

- **左侧栏**：群列表带搜索 —— 一键切换房间
- **群管理**：创建、编辑、删除群；每个群有独立角色、公告、规则与历史
- **通讯录**：预设的 AI 角色定义（研究员 / 代码手 / 创意家 / 评论家 / 编剧 / 历史学家），可拉入任何群
- **本群专属角色**：只属于某个群的一次性角色
- **群公告 + 补充规则**：公告作为聊天顶部横幅显示，并拼接到每个 AI 角色的 system prompt 前面；补充规则跟在其后
- **@链式发言**：输入 `@角色名` 指定下一个发言的角色
- **SSE 流式输出**：每次 AI 回复逐 token 流式呈现，带闪烁光标
- **无状态后端**：所有房间配置都存在 `localStorage`；服务端每次 POST 都拿到全量所需数据

### 为什么这样设计？

微信式房间让你能独立管理 **多个 AI 讨论面板**：一个代码评审群、一个头脑风暴群、一个写作工坊 —— 每个都有自己的角色名单和规则，全都用你已经熟悉的 UI。切换上下文只需点一下，不用重新加载配置。

---

## 快速开始

```bash
git clone https://github.com/<YOUR_USER>/claude-tool-agent.git
cd claude-tool-agent

python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

# 方式 A：在环境变量中设置 API key
$env:ANTHROPIC_API_KEY = "sk-ant-..."          # PowerShell
# export ANTHROPIC_API_KEY="sk-ant-..."         # bash / zsh

uvicorn app.main:app --reload --port 8000
```

打开 [http://localhost:8000](http://localhost:8000)。

没有环境变量？首次启动时 UI 会弹出 API Key 输入框 —— 粘贴后只存在浏览器的 `localStorage` 里（除了直连 Anthropic，不会发往任何其他地方）。

默认会创建 **代码评审小组** 群，自带两个角色（代码手 + 审查员），开箱即聊。通讯录里还预置了 6 个 AI 角色，可拉入任意新群。

---

## 功能

| 能力 | 说明 |
|---|---|
| **多房间** 🏠 | 左侧栏可无限创建群。每个群独立维护名字、成员、公告、规则与历史，搜索与切换一键完成。 |
| **通讯录** 📇 | 6 个预置 AI 角色（研究员 / 代码手 / 创意家 / 评论家 / 编剧 / 历史学家）—— 拉入任意群，或为本群创建自定义角色。 |
| **群公告** 📢 | 聊天顶部横幅展示，并拼接到每个 AI 角色的 system prompt 前。可与可选的补充规则组合使用。 |
| **群成员管理** 👥 | 带搜索的「从通讯录拉人」选择器，加上本群专属自定义角色。点击任一成员卡片可编辑其 prompt 与模型。 |
| **混合模型阵容** 🧠 | 每个角色可使用不同的 Claude 档位 —— Haiku 走快速廉价的回复，Sonnet 走均衡工作，Opus 处理硬推理，Fable 增加多样性。一个群内可自由混搭。 |
| **@链式发言** 🔗 | 在消息中输入 `@角色名` 邀请指定角色接着发言 —— 编排器据此重新排序本轮发言队列。角色之间也可以互相 @。 |
| **SSE 流式输出** ⚡ | 每个角色的回复经 Server-Sent Events 逐 token 流式呈现 —— 实时看着讨论展开，活跃角色上有闪烁光标。 |
| **停止按钮** ⛔ | 流式过程中可点停止 —— 通过 `AbortController` 中断 SSE 连接，部分回复保留。 |
| **Markdown 渲染** ✨ | 标题、列表、代码块、表格、引用、链接、行内代码 —— 全部安全渲染（转换前先对 HTML 转义）。 |
| **历史持久化** 💾 | 每个群的完整历史在 `localStorage` 中跨刷新保留。可用「清空记录」按群清空，或用「退出群聊」整个删除群。 |
| **自带 Key** 🔑 | 在 UI 中粘贴你的 Anthropic key（本地存储），或在服务端设置 `ANTHROPIC_API_KEY`。 |
| **零后端状态** ☁️ | FastAPI 服务端无状态 —— 每个请求携带完整的房间配置与历史。多开几个进程即可横向扩容。 |

---

## 架构

```
┌──────────────────────────┐       SSE (text/event-stream)       ┌─────────────────────────┐
│  浏览器 (static/)         │  <────────────────────────────────  │  FastAPI (app/main.py)  │
│                          │      POST /api/chatroom/send         │                         │
│  index.html              │                                     │  chatroom.py (router)   │
│  styles.css              │                                     │  orchestrator/          │
│  app.js                  │                                     │   ├── room.py           │
│   - 角色卡片             │                                     │   │   (Role, RoomConfig)│
│   - 聊天气泡             │                                     │   ├── mentions.py       │
│   - @弹窗                │                                     │   │   (parse / strip)  │
│   - SSE 流读取           │                                     │   └── engine.py         │
│   - localStorage 状态    │                                     │       (turn scheduler) │
└──────────────────────────┘                                     └──────────┬──────────────┘
                                                                            │
                                                                ┌───────────▼─────────────┐
                                                                │  anthropic SDK          │
                                                                │  client.messages.stream │
                                                                │  (一个角色一次调用)      │
                                                                └─────────────────────────┘
```

### 轮次调度（`orchestrator/engine.py`）

1. 拿到用户消息 + 角色配置 + 历史 + 群规则
2. **解析 @mention**：扫描消息中的 `@角色名`；若有，这些角色按 @顺序 依次发言；否则所有角色按注册顺序发言
3. 对每个发言角色依次：
   - 拼 system prompt = `群规则 + 该角色的 system_prompt`
   - 拼消息线程：之前历史 + 用户消息（适当处去掉 `@name` 前缀，避免模型鹦鹉学舌）
   - 调用 `client.messages.stream(...)`，token 到达即 yield `text` SSE 事件
   - 完成后把该角色回复追加到历史，进入下一个发言者
4. 发出 `role_start` / `text` / `role_end` / `done` 事件，让前端干净地渲染角色切换

轮次上限为 `MAX_TURNS = 20` —— 防止 @链失控的安全网，正常使用很少触达。

### SSE 事件协议

| 事件 | 负载 | 含义 |
|---|---|---|
| `role_start` | `{"role": "研究员"}` | 某角色即将开始发言；前端创建空气泡 |
| `text` | `{"role": "研究员", "delta": "..."}` | 当前角色的流式 token 片段 |
| `role_end` | `{"role": "研究员"}` | 该角色发言结束；定稿气泡并存入历史 |
| `error` | `{"message": "..."}` | 出错（鉴权、网络、模型错误） |
| `done` | `null` | 本轮结束；关闭流 |

---

## 项目结构

```
.
├── README.md                         # 英文版
├── README.zh-CN.md                   # 中文版（本文件）
├── LICENSE
├── requirements.txt                 # anthropic, fastapi, uvicorn, httpx, python-dotenv —— 就这些
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI 应用、静态挂载、健康检查
│   ├── chatroom.py                  # POST /api/chatroom/send —— SSE 路由
│   ├── config.py                    # 环境变量加载 + 默认 API key/模型
│   └── orchestrator/
│       ├── __init__.py
│       ├── room.py                  # Role / RoomConfig / Message 数据类
│       ├── mentions.py              # @mention 解析器 + 前缀剥离器
│       └── engine.py                # 轮次调度器 + Anthropic 流式
└── static/
    ├── index.html                   # 聊天室布局、弹窗、角色面板
    ├── styles.css                   # 气泡样式、角色配色、弹窗
    └── app.js                        # SSE 读取、角色 CRUD、@弹窗、markdown
```

---

## 使用

### 创建群（微信风）

1. 点击左侧栏左上角的 **＋** → 打开 **发起群聊** 弹窗
2. 填群名（例如 `代码评审小组`）
3. 写 **群公告** —— 每轮都拼到每个 AI 角色的 system prompt 前，并在聊天顶部以横幅展示
4.（可选）添加 **补充规则**，作为更细的协调提示，附在公告之后
5. **从通讯录拉成员** —— 点「＋ 从通讯录添加」打开联系人选择器，点任一预置角色即可加入本群
6. **或新建本群专属角色** —— 点「＋ 新建本群专属角色」，定义名字 / system prompt / 模型
7. 点 **创建群聊** —— 新群出现在左侧栏顶部

### 群公告 vs. 补充规则

- **群公告**：群里的「宪法」—— 高层协调规则。例如：*"每轮最多 3 次模型间对话，最后必须给出最终结论。用中文回答；不要复述别人已经说过的话。"*
- **补充规则**：更细的提示。例如：*"#代码手 在写代码前先让 #研究员 确认需求"*（`#` 前缀在送给模型前会被剥离，不让讨论显得嘈杂）

后端把它们合并为：`【群公告】\n{announcement}\n\n【补充规则】\n{group_rules}`（空段会被丢掉）。

### 编辑 / 删除群

- 在聊天头部点 **⚙ 设置** 重新打开群弹窗进行编辑
- **清空记录** 只清会话历史，保留群
- **退出群聊** 整个删除群

### 切换群

点击左侧栏任一群卡片即可切换。每个群独立保留自己的角色、公告、规则与完整历史。切换时会中断当前流。

### 示例群

- **代码评审组**：`代码手`（Sonnet，务实工程师）+ `审查员`（Opus，严谨审查者）+ `架构师`（Sonnet，大局观）。群公告："审查员必须挑出至少两个问题，否则投票放弃方案。"
- **写作工坊**：`主笔`（Opus）+ `编辑`（Sonnet）+ `校对`（Haiku，快）。群公告："主笔先写一段，编辑提建议，校对最后改错别字。每轮 3 次对话后输出定稿。"
- **辩论俱乐部**：`正方`（Sonnet）+ `反方`（Sonnet）+ `评委`（Opus）。群公告："正方反方各陈述 1 次，评委给出胜负判决。"

### @mention 行为

- 在你的消息里：`@研究员 你觉得呢？@代码手 也说说` → 研究员 先发言，然后 代码手 —— 其他角色本轮跳过
- 角色能看到之前包含 @mention 的回合，所以它们明白谁在跟谁对话
- 编排器会从角色回复里剥离开头的 `@角色名` 前缀，避免转录堆满冗余 @

---

## 配置参考

### API Key 优先级

```
UI 输入 (localStorage)            ← 每次请求附带，优先于环境变量
   ↓ 若缺
ANTHROPIC_API_KEY 环境变量         ← 在 shell 或 .env 中设置
   ↓ 若缺
401 from Anthropic               ← 首次发送时报错
```

### 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key；若 UI 未提供则为必填 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | 未指定模型时的回退模型 |

UI 里的按角色模型选择永远胜过 `ANTHROPIC_MODEL`。

---

## 路线图

- [ ] 持久化房间（服务端会话存储，刷新保留多角色中间回合）
- [ ] 分支对话（从任一消息分叉出 what-if 线程）
- [ ] 每角色每会话的 token 与成本计量
- [ ] 多用户房间 + 鉴权参与者

---

## 常见问题

**问：我需要 Anthropic API key 吗？**  
答：需要 —— 每个角色的回复都是真实的 Claude API 调用。可在 [console.anthropic.com](https://console.anthropic.com) 获取。

**问：一段对话多少钱？**  
答：每个角色的一轮就是一次带完整历史作为上下文的 Claude 调用。默认角色（Haiku + Sonnet）加短对话，几美分级别。Opus 角色配长历史会明显更贵 —— Opus 是成本主驱动。

**问：角色能调用工具或上网吗？**  
答：本版本不能 —— 编排器是纯聊天。工具调用未来可能回归，按角色单独配置。

**问：如果某个角色陷在自我 @里出不来怎么办？**  
答：`engine.py` 里的 `MAX_TURNS = 20` 上限会强行打断任何循环。可按喜好调整。

**问：能上生产吗？**  
答：不能 —— 这是个 demo，无鉴权、无限流、无防滥用。请在本地或你自己的鉴权层后面运行。UI 里的 API key 除了去 Anthropic 之外不会离开浏览器。

---

## 贡献

欢迎贡献！请先开个 issue 讨论重大改动。

1. Fork → feature 分支 → commit → PR
2. diff 保持聚焦；本代码库刻意保持小巧
3. 提交前本地跑 `python -m uvicorn app.main:app --reload` 验证

---

## 许可证

[MIT](LICENSE) —— 随意用、改、分享。
