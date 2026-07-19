/* AI 群聊 — WeChat-style multi-room chat
 *
 * 数据模型（全部 localStorage）：
 *   rooms: Room[] —— 每个 Room 自带 roles / groupRules / announcement / history
 *   currentRoomId: 当前选中的群
 *   apiKey: Anthropic key
 *
 * 后端无状态，每次 POST 推一整个群配置 + history。
 */

const STORAGE_KEYS = {
    rooms: "ai_chat_rooms",
    currentRoomId: "ai_chat_current_room",
    contacts: "ai_chat_contacts",   // "通讯录" — 预置 + 用户保存的可复用角色
    apikey: "anthropic_api_key",
};

const ROLE_COLORS = ["#10a37f", "#3b82f6", "#8b5cf6", "#ef4444", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1"];

const DEFAULT_MODELS = [
    { value: "claude-haiku-4-5-20251001", label: "claude-haiku-4-5 (Haiku)" },
    { value: "claude-sonnet-5", label: "claude-sonnet-5 (Sonnet)" },
    { value: "claude-opus-4-7", label: "claude-opus-4-7 (Opus)" },
    { value: "claude-opus-4-8", label: "claude-opus-4-8 (Opus)" },
    { value: "claude-fable-5", label: "claude-fable-5 (Fable)" },
];

/** Internal state */
const state = {
    rooms: [],            // Room[]
    currentRoomId: null,  // string | null
    contacts: [],         // Role[] — reusable address book of AI roles
    apiKey: "",
    currentStream: null,  // AbortController
    activeStreamingBubbles: new Set(),

    // Room modal scratchpad
    roomDraft: null,       // { id?, name, announcement, groupRules, members: Role[], customRoles: Role[] }
    editingRoomId: null,
    // Role modal scratchpad
    roleDraft: null,       // { idx?: number, target: 'member'|'custom'|'contact', name, system_prompt, model }
};

function newRoomId() {
    return "room_" + Date.now().toString(36) + "_" + (state.rooms.length + 1);
}

function makeDefaultRoom() {
    return {
        id: newRoomId(),
        name: "代码评审小组",
        announcement: "每轮最多 3 次模型间对话，最后必须给出最终结论。不要复述别人已经说过的话。用中文回答。",
        groupRules: "",
        roles: [
            { name: "代码手", system_prompt: "你是一位务实的工程师，回答时给出可执行的建议和最小可工作示例，不空谈架构。", model: "claude-sonnet-5" },
            { name: "审查员", system_prompt: "你是一位细致的代码审查员，每次必须挑出至少两个潜在问题，否则投票放弃方案。", model: "claude-opus-4-7" },
        ],
        history: [],
    };
}

/* ───── Init ───── */
document.addEventListener("DOMContentLoaded", async () => {
    loadState();
    if (!state.contacts.length) await fetchPresetContacts();
    if (!state.rooms.length) {
        state.rooms = [makeDefaultRoom()];
        saveState();
    }
    state.currentRoomId = state.currentRoomId && state.rooms.find(r => r.id === state.currentRoomId)
        ? state.currentRoomId
        : state.rooms[0].id;
    saveState();

    renderRoomList();
    renderCurrentRoom();
    bindEvents();
    updateApiKeyStatus();
    if (!state.apiKey) openApiKeyModal();
});

async function fetchPresetContacts() {
    try {
        const resp = await fetch("/api/presets/roles");
        if (resp.ok) {
            const presets = await resp.json();
            state.contacts = presets.map(p => ({ name: p.name, system_prompt: p.system_prompt, model: p.model }));
        }
    } catch { /* fall back to empty */ }
    if (!state.contacts.length) {
        state.contacts = [
            { name: "研究员", system_prompt: "你是一位严谨的研究员，回答时喜欢引用数据和文献，先承认不确定性再给出推断。", model: "claude-haiku-4-5-20251001" },
            { name: "代码手", system_prompt: "你是一位务实的工程师，回答时给出可执行的建议和最小可工作示例，不空谈架构。", model: "claude-sonnet-5" },
        ];
    }
    saveState();
}

/* ───── Persistence ───── */
function loadState() {
    try { state.rooms = JSON.parse(localStorage.getItem(STORAGE_KEYS.rooms) || "[]"); } catch { state.rooms = []; }
    state.currentRoomId = localStorage.getItem(STORAGE_KEYS.currentRoomId) || null;
    try { state.contacts = JSON.parse(localStorage.getItem(STORAGE_KEYS.contacts) || "[]"); } catch { state.contacts = []; }
    state.apiKey = localStorage.getItem(STORAGE_KEYS.apikey) || "";
}
function saveState() {
    localStorage.setItem(STORAGE_KEYS.rooms, JSON.stringify(state.rooms));
    if (state.currentRoomId) localStorage.setItem(STORAGE_KEYS.currentRoomId, state.currentRoomId);
    localStorage.setItem(STORAGE_KEYS.contacts, JSON.stringify(state.contacts));
    localStorage.setItem(STORAGE_KEYS.apikey, state.apiKey);
}

function currentRoom() {
    return state.rooms.find(r => r.id === state.currentRoomId) || null;
}

/* ───── Room list (left sidebar) ───── */
function renderRoomList(filter = "") {
    const list = document.getElementById("room-list");
    const emptyEl = document.getElementById("room-list-empty");
    list.innerHTML = "";
    const filtered = state.rooms.filter(r => !filter || (r.name || "").toLowerCase().includes(filter.toLowerCase()));
    if (!filtered.length) {
        list.style.display = "none";
        emptyEl.style.display = "";
        emptyEl.querySelector(".room-list-empty-title").textContent = filter ? "没有匹配的群聊" : "还没有群聊";
        emptyEl.querySelector(".room-list-empty-sub").textContent = filter ? "换个关键词试试" : "点右上角「＋」拉一个群";
        return;
    }
    list.style.display = "";
    emptyEl.style.display = "none";
    // Sort: rooms with more recent history first
    const sorted = [...filtered].sort((a, b) => {
        const at = lastMessageTime(a);
        const bt = lastMessageTime(b);
        return bt - at;
    });
    sorted.forEach(room => {
        const last = room.history[room.history.length - 1];
        const lastPreview = last ? truncate(stripMarkdown(last.content), 28) : "新群聊，还没有消息";
        const active = room.id === state.currentRoomId;
        const card = document.createElement("div");
        card.className = "room-card" + (active ? " active" : "");
        card.dataset.roomId = room.id;
        const membersText = `${(room.roles || []).length} 位成员`;
        card.innerHTML = `
            <div class="room-avatar">${escapeHtml(initials(room.name))}</div>
            <div class="room-card-info">
                <div class="room-card-name">${escapeHtml(room.name || "未命名群聊")}</div>
                <div class="room-card-preview">${escapeHtml(lastPreview)}</div>
            </div>
            <div class="room-card-meta">${escapeHtml(membersText)}</div>
        `;
        card.addEventListener("click", () => switchRoom(room.id));
        list.appendChild(card);
    });
}

function lastMessageTime(room) {
    if (!room.history.length) return 0;
    return room.history.length; // simple proxy — newest last means most messages
}

function switchRoom(roomId) {
    if (state.currentStream) stopStream();
    state.currentRoomId = roomId;
    saveState();
    renderRoomList();
    renderCurrentRoom();
}

/* ───── Current room (right pane) ───── */
function renderCurrentRoom() {
    const empty = document.getElementById("chat-empty");
    const view = document.getElementById("chat-view");
    const room = currentRoom();
    if (!room) {
        empty.style.display = "";
        view.style.display = "none";
        renderRoomList();
        return;
    }
    empty.style.display = "none";
    view.style.display = "";

    // Chat header avatar
    const avatarEl = document.getElementById("current-room-avatar");
    avatarEl.textContent = initials(room.name);
    avatarEl.style.background = getRoomGradient(room.id);

    document.getElementById("current-room-name").textContent = room.name || "未命名群聊";
    document.getElementById("current-room-members").textContent = `${(room.roles || []).length} 位成员`;

    // Member strip
    renderMemberStrip(room);

    const banner = document.getElementById("announcement-banner");
    const bannerText = document.getElementById("announcement-text");
    if (room.announcement && room.announcement.trim()) {
        banner.style.display = "";
        bannerText.textContent = room.announcement;
    } else {
        banner.style.display = "none";
    }

    renderMessages();
}

function renderMessages() {
    const wrap = document.getElementById("messages");
    wrap.innerHTML = "";
    const room = currentRoom();
    if (!room) return;
    room.history.forEach((msg) => {
        if (msg.role === "user") appendUserMessage(msg.content);
        else appendAssistantMessage(msg.name, msg.content, false);
    });
    scrollToBottom();
}

function appendUserMessage(text) {
    const wrap = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "msg msg-user";
    div.innerHTML = `
        <div class="msg-avatar msg-avatar-user">我</div>
        <div class="bubble-wrap"><div class="bubble">${escapeHtml(text)}</div></div>
    `;
    wrap.appendChild(div);
    scrollToBottom();
}
function appendAssistantMessage(roleName, initialText = "", streaming = false) {
    const wrap = document.getElementById("messages");
    const room = currentRoom() || { roles: [] };
    const idx = room.roles.findIndex(r => r.name === roleName);
    const color = idx >= 0 ? roleColor(idx) : "#888";
    const initial = idx >= 0 ? roleInitial(room.roles[idx].name) : roleInitial(roleName);

    const div = document.createElement("div");
    div.className = "msg msg-assistant" + (streaming ? " streaming" : "");
    div.dataset.role = roleName;
    const showPlaceholder = streaming && !initialText;
    div.innerHTML = `
        <div class="msg-avatar" style="background:${color}">${escapeHtml(initial)}</div>
        <div class="bubble-wrap">
            <div class="msg-header">
                <span class="msg-author">${escapeHtml(roleName)}</span>
                <span class="msg-role-tag">${escapeHtml(shortModel(room.roles[idx]?.model || ""))}</span>
            </div>
            <div class="bubble${showPlaceholder ? " bubble-typing" : ""}">${showPlaceholder ? '<span class="typing-dots"><span></span><span></span><span></span></span>' : renderMarkdown(initialText)}</div>
        </div>
    `;
    wrap.appendChild(div);
    if (streaming) state.activeStreamingBubbles.add(div);
    scrollToBottom();
    return div;
}

function appendErrorMessage(text) {
    const wrap = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "msg-error";
    div.textContent = text;
    wrap.appendChild(div);
    scrollToBottom();
}

function appendDeltaToBubble(roleName, delta) {
    const wrap = document.getElementById("messages");
    const bubbles = wrap.querySelectorAll(`.msg-assistant[data-role="${cssEscape(roleName)}"]`);
    if (!bubbles.length) { appendAssistantMessage(roleName, delta, true); return; }
    const bubble = bubbles[bubbles.length - 1];
    const accumulated = (bubble.dataset.raw || "") + delta;
    bubble.dataset.raw = accumulated;
    bubble.querySelector(".bubble").innerHTML = renderMarkdown(accumulated);
    scrollToBottom();
}

function finalizeBubble(roleName) {
    const wrap = document.getElementById("messages");
    const bubbles = wrap.querySelectorAll(`.msg-assistant[data-role="${cssEscape(roleName)}"]`);
    if (!bubbles.length) return;
    const bubble = bubbles[bubbles.length - 1];
    bubble.classList.remove("streaming");
    const text = bubble.dataset.raw || bubble.querySelector(".bubble").textContent;
    const room = currentRoom();
    if (room) {
        room.history.push({ role: "assistant", name: roleName, content: text });
        saveState();
        renderRoomList();
    }
    state.activeStreamingBubbles.delete(bubble);
}

/* ───── SSE send ───── */
async function sendMessage(text) {
    if (!text.trim()) return;
    const room = currentRoom();
    if (!room) { showToast("请先选择或创建一个群聊"); return; }
    if (!room.roles.length) { showToast("群里还没有 AI 成员，先在「设置」里添加"); return; }
    if (!state.apiKey) { openApiKeyModal(); return; }

    appendUserMessage(text);
    room.history.push({ role: "user", name: "用户", content: text });
    saveState();
    renderRoomList();

    document.getElementById("composer-input").value = "";
    autoSize(document.getElementById("composer-input"));
    setSending(true);

    const ctrl = new AbortController();
    state.currentStream = ctrl;

    try {
        const resp = await fetch("/api/chatroom/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                history: room.history.filter(m => m.content && m.content.trim() !== ""),
                room: {
                    room_id: room.id,
                    roles: room.roles,
                    announcement: room.announcement || "",
                    group_rules: room.groupRules || "",
                },
                api_key: state.apiKey,
            }),
            signal: ctrl.signal,
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ error: resp.statusText }));
            appendErrorMessage(err.error || "请求失败");
            return;
        }

        await streamSSE(resp);
    } catch (e) {
        if (e.name !== "AbortError") appendErrorMessage(`发送失败：${e.message}`);
    } finally {
        setSending(false);
        state.currentStream = null;
    }
}

async function streamSSE(resp) {
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        // Per SSE spec, frames are separated by a blank line. Tolerate \n\n
        // (our backend), \r\n\r\n (some proxies), and mixed line endings.
        const frames = buf.split(/\r?\n\r?\n/);
        buf = frames.pop();
        for (const frame of frames) parseSSEFrame(frame);
    }
    if (buf.trim()) parseSSEFrame(buf);
}

function parseSSEFrame(frame) {
    let event = "message";
    let data = "";
    for (const line of frame.split(/\r?\n/)) {
        if (!line) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).replace(/^\s/, "") + "\n";
    }
    handleSSEEvent(event, data.replace(/\n$/, ""));
}

function handleSSEEvent(event, data) {
    let payload = {};
    try { payload = data && data !== "null" ? JSON.parse(data) : null; } catch {}
    switch (event) {
        case "role_start": appendAssistantMessage(payload.role, "", true); break;
        case "text": appendDeltaToBubble(payload.role, payload.delta); break;
        case "role_end": finalizeBubble(payload.role); break;
        case "error": appendErrorMessage(payload.message || "未知错误"); break;
        case "done": break;
    }
}

function stopStream() {
    if (state.currentStream) state.currentStream.abort();
    state.activeStreamingBubbles.forEach(b => b.classList.remove("streaming"));
    state.activeStreamingBubbles.clear();
    setSending(false);
}

function setSending(sending) {
    document.getElementById("btn-send").style.display = sending ? "none" : "";
    document.getElementById("btn-stop").style.display = sending ? "" : "none";
    const status = document.getElementById("composer-footer-status");
    if (status) status.textContent = sending ? "发送中…" : "就绪";
}

/* ───── Member strip & room avatar helpers ───── */
function renderMemberStrip(room) {
    const strip = document.getElementById("member-strip");
    if (!strip) return;
    strip.innerHTML = "";
    const roles = room.roles || [];
    const VISIBLE_MAX = 8;
    const visible = roles.slice(0, VISIBLE_MAX);
    visible.forEach((r, i) => {
        const item = document.createElement("div");
        item.className = "member-strip-item";
        item.innerHTML = `
            <div class="member-strip-avatar" style="background:${roleColor(i)}">${escapeHtml(roleInitial(r.name))}</div>
            <div class="member-strip-name">${escapeHtml(r.name)}</div>
        `;
        item.addEventListener("click", () => openRoomModal(room.id));
        strip.appendChild(item);
    });
    if (roles.length > VISIBLE_MAX) {
        const more = document.createElement("div");
        more.className = "member-strip-item";
        more.innerHTML = `<div class="member-strip-more">+${roles.length - VISIBLE_MAX}</div>`;
        more.addEventListener("click", () => openRoomModal(room.id));
        strip.appendChild(more);
    }
}

const ROOM_GRADIENTS = [
    "linear-gradient(135deg, #07c160, #2ecc71)",
    "linear-gradient(135deg, #3b82f6, #60a5fa)",
    "linear-gradient(135deg, #8b5cf6, #a78bfa)",
    "linear-gradient(135deg, #ef4444, #f87171)",
    "linear-gradient(135deg, #f59e0b, #fbbf24)",
    "linear-gradient(135deg, #ec4899, #f472b6)",
];
function getRoomGradient(roomId) {
    if (!roomId) return ROOM_GRADIENTS[0];
    let h = 0;
    for (let i = 0; i < roomId.length; i++) h = (h * 31 + roomId.charCodeAt(i)) | 0;
    return ROOM_GRADIENTS[Math.abs(h) % ROOM_GRADIENTS.length];
}

function updateApiKeyStatus() {
    const dot = document.getElementById("apikey-status-dot");
    if (!dot) return;
    if (state.apiKey) {
        dot.className = "status-dot status-dot-ok";
        dot.title = "API Key 已配置";
    } else {
        dot.className = "status-dot status-dot-pending";
        dot.title = "未配置 API Key";
    }
}

/* ───── Mention popup ───── */
let mentionActive = false;
let mentionStart = -1;
let mentionSelectedIdx = 0;

function bindMentionPopup() {
    const input = document.getElementById("composer-input");
    input.addEventListener("input", onComposerInput);
    input.addEventListener("keydown", onComposerKeydown);
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".composer-input-wrap")) hideMentionPopup();
    });
}

function onComposerInput(e) {
    autoSize(e.target);
    const room = currentRoom(); if (!room) return;
    const text = e.target.value;
    const pos = e.target.selectionStart;
    let i = pos - 1;
    while (i >= 0 && text[i] !== " " && text[i] !== "\n" && text[i] !== "@") i--;
    if (i >= 0 && text[i] === "@") {
        const fragment = text.slice(i + 1, pos);
        const matches = room.roles.filter(r => r.name.startsWith(fragment));
        if (matches.length) {
            mentionActive = true;
            mentionStart = i;
            mentionSelectedIdx = 0;
            showMentionPopup(matches, room.roles);
            return;
        }
    }
    hideMentionPopup();
}

function onComposerKeydown(e) {
    if (!mentionActive) {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(e.target.value); }
        return;
    }
    const popup = document.getElementById("mention-popup");
    const items = popup.querySelectorAll(".mention-item");
    if (e.key === "ArrowDown") { e.preventDefault(); mentionSelectedIdx = (mentionSelectedIdx + 1) % items.length; updateMentionActive(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mentionSelectedIdx = (mentionSelectedIdx - 1 + items.length) % items.length; updateMentionActive(); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); items[mentionSelectedIdx]?.click(); }
    else if (e.key === "Escape") { hideMentionPopup(); }
}

function showMentionPopup(matches, allRoles) {
    const popup = document.getElementById("mention-popup");
    popup.innerHTML = "";
    matches.forEach((r, idx) => {
        const i = allRoles.indexOf(r);
        const item = document.createElement("div");
        item.className = "mention-item" + (idx === 0 ? " active" : "");
        item.innerHTML = `<span class="avatar-mini" style="background:${roleColor(i)}">${escapeHtml(roleInitial(r.name))}</span> @${escapeHtml(r.name)}`;
        item.addEventListener("click", () => insertMention(r.name));
        popup.appendChild(item);
    });
    popup.style.display = "";
}

function updateMentionActive() {
    document.querySelectorAll(".mention-item").forEach((it, i) => it.classList.toggle("active", i === mentionSelectedIdx));
}

function hideMentionPopup() {
    document.getElementById("mention-popup").style.display = "none";
    mentionActive = false;
}

function insertMention(roleName) {
    const input = document.getElementById("composer-input");
    const text = input.value;
    const before = text.slice(0, mentionStart) + `@${roleName} `;
    const after = text.slice(input.selectionStart);
    input.value = before + after;
    input.focus();
    const cursor = before.length;
    input.setSelectionRange(cursor, cursor);
    hideMentionPopup();
    autoSize(input);
}

/* ───── Utilities ───── */
function autoSize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
}
function scrollToBottom() {
    const wrap = document.getElementById("messages");
    wrap.scrollTop = wrap.scrollHeight;
}
function roleColor(idx) { return ROLE_COLORS[idx % ROLE_COLORS.length]; }
function roleInitial(name) { return ([...(name || "")].slice(0, 1).join("")) || "?"; }
function initials(name) {
    return [...(name || "")].slice(0, 2).join("");
}
function shortModel(m) { return (m || "").replace(/^claude-/, "").replace(/-\d+(-\d+)?$/, ""); }
function truncate(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
function stripMarkdown(s) { return (s || "").replace(/[*`#>\-\[\]\(\)!]/g, "").replace(/\s+/g, " ").trim(); }

function escapeHtml(s) {
    return (s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
function cssEscape(s) { return (s || "").replace(/"/g, '\\"'); }

function showToast(text) {
    const t = document.getElementById("toast");
    t.textContent = text;
    t.style.display = "";
    setTimeout(() => t.style.display = "none", 2200);
}

/* Minimal, safe markdown renderer */
function renderMarkdown(md) {
    let text = md || "";
    const codeBlocks = [];
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        codeBlocks.push({ lang, code });
        return `CODE${codeBlocks.length - 1}`;
    });
    text = escapeHtml(text);
    text = text.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
    text = text.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    text = text.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    text = text.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    text = text.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    text = text.replace(/^---$/gm, "<hr>");
    text = text.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");
    text = text.replace(/^(\s*)[-*] (.+)$/gm, '<li>$2</li>');
    text = text.replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g, "<ul>$1</ul>");
    text = text.replace(/^(\s*)\d+\. (.+)$/gm, '<li>$2</li>');
    text = text.replace(/^((?:.+\|.+)\n)+$/gm, (block) => {
        const rows = block.trim().split("\n");
        if (rows.length < 2) return block;
        if (!/^\|?[\s-:|]+\|[\s-:|]+$/.test(rows[1])) return block;
        const headers = rows[0].split("|").map(s => s.trim()).filter(Boolean);
        let html = "<table><thead><tr>" + headers.map(h => `<th>${h}</th>`).join("") + "</tr></thead><tbody>";
        for (let i = 2; i < rows.length; i++) {
            const cells = rows[i].split("|").map(s => s.trim()).filter(Boolean);
            if (cells.length) html += "<tr>" + cells.map(c => `<td>${c}</td>`).join("") + "</tr>";
        }
        html += "</tbody></table>";
        return html;
    });
    text = text.split(/\n{2,}/).map(chunk => {
        if (/^\s*<(h\d|ul|ol|li|pre|blockquote|table|hr)/.test(chunk)) return chunk;
        if (chunk.includes("CODE")) return chunk;
        return `<p>${chunk.replace(/\n/g, "<br>")}</p>`;
    }).join("\n");
    text = text.replace(/CODE(\d+)/g, (_, i) => {
        const b = codeBlocks[+i];
        return `<pre><code>${escapeHtml(b.code)}</code></pre>`;
    });
    return text;
}

/* ───── Event bindings ───── */
function bindEvents() {
    bindMentionPopup();
    document.getElementById("btn-send").addEventListener("click", () => {
        sendMessage(document.getElementById("composer-input").value);
    });
    document.getElementById("btn-stop").addEventListener("click", stopStream);
    document.getElementById("btn-new-room").addEventListener("click", () => openRoomModal(null));
    document.getElementById("btn-empty-new-room").addEventListener("click", () => openRoomModal(null));
    document.getElementById("btn-room-settings").addEventListener("click", () => openRoomModal(currentRoom()?.id));
    document.getElementById("btn-announcement").addEventListener("click", openAnnouncementViewer);
    document.getElementById("announcement-edit-btn").addEventListener("click", () => openRoomModal(currentRoom()?.id));
    document.getElementById("btn-clear-history").addEventListener("click", () => {
        const room = currentRoom(); if (!room) return;
        if (!confirm(`清空「${room.name}」的对话记录？`)) return;
        room.history = [];
        saveState();
        renderMessages();
        renderRoomList();
    });
    document.getElementById("btn-leave-room").addEventListener("click", () => {
        const room = currentRoom(); if (!room) return;
        if (!confirm(`退出并删除群聊「${room.name}」？`)) return;
        const idx = state.rooms.findIndex(r => r.id === room.id);
        state.rooms.splice(idx, 1);
        state.currentRoomId = state.rooms[0]?.id || null;
        saveState();
        renderRoomList();
        renderCurrentRoom();
    });
    document.getElementById("btn-apikey").addEventListener("click", openApiKeyModal);
    const searchInput = document.getElementById("room-search");
    const searchClear = document.getElementById("room-search-clear");
    searchInput.addEventListener("input", (e) => {
        renderRoomList(e.target.value);
        searchClear.style.display = e.target.value ? "" : "none";
    });
    searchClear.addEventListener("click", () => {
        searchInput.value = "";
        renderRoomList("");
        searchClear.style.display = "none";
        searchInput.focus();
    });

    // Universal modal close buttons
    document.querySelectorAll("[data-modal-close]").forEach(btn => {
        btn.addEventListener("click", () => {
            const modal = btn.closest(".modal");
            if (modal) modal.style.display = "none";
        });
    });
    // Escape closes topmost modal
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        const openModals = Array.from(document.querySelectorAll(".modal")).filter(m => m.style.display !== "none");
        if (openModals.length) {
            openModals[openModals.length - 1].style.display = "none";
            hideMentionPopup();
        }
    });

    bindRoomModal();
    bindRoleModal();
    bindApiKeyModal();
    bindAnnouncementModal();
}

/* ───── Room modal (create / edit) ───── */
function openRoomModal(roomId) {
    state.editingRoomId = roomId || null;
    let base;
    if (roomId) {
        const r = state.rooms.find(x => x.id === roomId);
        base = {
            id: r.id,
            name: r.name,
            announcement: r.announcement || "",
            groupRules: r.groupRules || "",
            members: r.roles.map(rl => ({ ...rl })),
            customRoles: [],
        };
    } else {
        base = { id: null, name: "", announcement: "", groupRules: "", members: [], customRoles: [] };
    }
    state.roomDraft = base;

    document.getElementById("room-modal-title").textContent = roomId ? "编辑群聊" : "发起群聊";
    document.getElementById("room-name").value = base.name;
    document.getElementById("room-announcement").value = base.announcement;
    document.getElementById("room-rules").value = base.groupRules;
    document.getElementById("room-save").textContent = roomId ? "保存" : "创建群聊";
    document.getElementById("member-picker").style.display = "none";
    document.getElementById("custom-role-list").innerHTML = "";
    renderRoomDraftMembers();
    document.getElementById("room-modal").style.display = "";
}

function renderRoomDraftMembers() {
    const wrap = document.getElementById("room-member-list");
    wrap.innerHTML = "";
    const allMembers = [...state.roomDraft.members, ...state.roomDraft.customRoles];
    if (!allMembers.length) {
        wrap.innerHTML = `<div class="member-empty">还没有群成员。点上方「从通讯录添加」拉入 AI 角色。</div>`;
        return;
    }
    allMembers.forEach((r, i) => {
        const isCustom = i >= state.roomDraft.members.length;
        const localIdx = isCustom ? i - state.roomDraft.members.length : i;
        const card = document.createElement("div");
        card.className = "member-chip";
        card.innerHTML = `
            <span class="member-chip-avatar" style="background:${roleColor(i)}">${escapeHtml(roleInitial(r.name))}</span>
            <div class="member-chip-info">
                <div class="member-chip-name">${escapeHtml(r.name)}</div>
                <div class="member-chip-model">${escapeHtml(shortModel(r.model))}</div>
            </div>
            <button class="member-chip-remove" title="移除">✕</button>
        `;
        card.querySelector(".member-chip-remove").addEventListener("click", () => {
            if (isCustom) state.roomDraft.customRoles.splice(localIdx, 1);
            else state.roomDraft.members.splice(localIdx, 1);
            renderRoomDraftMembers();
        });
        card.querySelector(".member-chip-info").addEventListener("click", () => {
            openRoleModal({ target: isCustom ? "custom" : "member", idx: localIdx, role: r });
        });
        wrap.appendChild(card);
    });
}

function bindRoomModal() {
    document.getElementById("room-cancel").addEventListener("click", () => {
        document.getElementById("room-modal").style.display = "none";
    });
    document.getElementById("room-save").addEventListener("click", () => {
        const name = document.getElementById("room-name").value.trim();
        if (!name) { showToast("请输入群名"); return; }
        const announcement = document.getElementById("room-announcement").value;
        const groupRules = document.getElementById("room-rules").value;
        const roles = [...state.roomDraft.members, ...state.roomDraft.customRoles];
        if (!roles.length) { showToast("群里至少要有一个 AI 成员"); return; }

        if (state.editingRoomId) {
            const room = state.rooms.find(r => r.id === state.editingRoomId);
            room.name = name;
            room.announcement = announcement;
            room.groupRules = groupRules;
            room.roles = roles;
        } else {
            const room = {
                id: newRoomId(),
                name,
                announcement,
                groupRules,
                roles,
                history: [],
            };
            state.rooms.unshift(room);
            state.currentRoomId = room.id;
        }
        saveState();
        document.getElementById("room-modal").style.display = "none";
        renderRoomList();
        renderCurrentRoom();
    });

    document.getElementById("btn-add-member").addEventListener("click", () => {
        const picker = document.getElementById("member-picker");
        picker.style.display = picker.style.display === "none" ? "" : "none";
        if (picker.style.display !== "none") {
            document.getElementById("member-picker-search").value = "";
            renderMemberPicker("");
        }
    });
    document.getElementById("member-picker-search").addEventListener("input", (e) => renderMemberPicker(e.target.value));
    document.getElementById("btn-add-custom-role").addEventListener("click", () => {
        openRoleModal({ target: "custom", idx: null });
    });
}

function renderMemberPicker(filter = "") {
    const list = document.getElementById("member-picker-list");
    list.innerHTML = "";
    const existingNames = new Set([
        ...state.roomDraft.members.map(r => r.name),
        ...state.roomDraft.customRoles.map(r => r.name),
    ]);
    const filtered = state.contacts.filter(c => !existingNames.has(c.name))
        .filter(c => !filter || c.name.toLowerCase().includes(filter.toLowerCase()));
    if (!filtered.length) {
        list.innerHTML = `<div class="member-empty">通讯录里没有可选的角色了。</div>`;
        return;
    }
    filtered.forEach((c) => {
        const i = state.contacts.indexOf(c);
        const item = document.createElement("div");
        item.className = "member-picker-item";
        item.innerHTML = `
            <span class="member-chip-avatar" style="background:${roleColor(i)}">${escapeHtml(roleInitial(c.name))}</span>
            <div class="member-chip-info">
                <div class="member-chip-name">${escapeHtml(c.name)}</div>
                <div class="member-chip-model">${escapeHtml(shortModel(c.model))}</div>
            </div>
        `;
        item.addEventListener("click", () => {
            state.roomDraft.members.push({ ...c });
            renderRoomDraftMembers();
            renderMemberPicker(document.getElementById("member-picker-search").value);
        });
        list.appendChild(item);
    });
}

/* ───── Role modal — used inside room modal ───── */
function openRoleModal(draft) {
    state.roleDraft = { ...draft };
    if (!draft.role && draft.target === "custom" && draft.idx === null) {
        state.roleDraft = { target: "custom", idx: null, name: "", system_prompt: "", model: "claude-haiku-4-5-20251001" };
    } else if (draft.role) {
        state.roleDraft = { target: draft.target, idx: draft.idx, name: draft.role.name, system_prompt: draft.role.system_prompt, model: draft.role.model };
    }
    document.getElementById("role-modal-title").textContent = draft.role ? "编辑角色" : "新建角色";
    const modelSelect = document.getElementById("role-model");
    modelSelect.innerHTML = DEFAULT_MODELS.map(m => `<option value="${m.value}">${m.label}</option>`).join("");
    document.getElementById("role-name").value = state.roleDraft.name || "";
    document.getElementById("role-prompt").value = state.roleDraft.system_prompt || "";
    modelSelect.value = state.roleDraft.model || DEFAULT_MODELS[0].value;
    document.getElementById("role-modal").style.display = "";
}

function bindRoleModal() {
    document.getElementById("role-cancel").addEventListener("click", () => {
        document.getElementById("role-modal").style.display = "none";
    });
    document.getElementById("role-save").addEventListener("click", () => {
        const name = document.getElementById("role-name").value.trim();
        const prompt = document.getElementById("role-prompt").value.trim();
        const model = document.getElementById("role-model").value;
        if (!name) { showToast("请输入角色名字"); return; }
        if (!prompt) { showToast("请输入系统 prompt"); return; }
        const role = { name, system_prompt: prompt, model };
        if (state.roleDraft.idx === null || state.roleDraft.idx === undefined) {
            // Append to either contacts or to the custom role list inside the room draft
            if (state.roleDraft.target === "custom") {
                state.roomDraft.customRoles.push(role);
            } else {
                state.roomDraft.members.push(role);
            }
        } else {
            if (state.roleDraft.target === "custom") {
                state.roomDraft.customRoles[state.roleDraft.idx] = role;
            } else {
                state.roomDraft.members[state.roleDraft.idx] = role;
            }
        }
        document.getElementById("role-modal").style.display = "none";
        renderRoomDraftMembers();
    });
}

/* ───── Announcement modal ───── */
function openAnnouncementViewer() {
    const room = currentRoom();
    document.getElementById("announcement-view").value = room?.announcement || "";
    document.getElementById("announcement-modal").style.display = "";
}

function bindAnnouncementModal() {
    document.getElementById("announcement-close").addEventListener("click", () => {
        document.getElementById("announcement-modal").style.display = "none";
    });
    document.getElementById("announcement-edit").addEventListener("click", () => {
        document.getElementById("announcement-modal").style.display = "none";
        openRoomModal(state.currentRoomId);
    });
}

/* ───── API key modal ───── */
function openApiKeyModal() {
    document.getElementById("apikey-input").value = state.apiKey;
    document.getElementById("apikey-modal").style.display = "";
}
function bindApiKeyModal() {
    document.getElementById("apikey-cancel").addEventListener("click", () => {
        document.getElementById("apikey-modal").style.display = "none";
    });
    document.getElementById("apikey-save").addEventListener("click", () => {
        state.apiKey = document.getElementById("apikey-input").value.trim();
        saveState();
        document.getElementById("apikey-modal").style.display = "none";
        updateApiKeyStatus();
    });
}
