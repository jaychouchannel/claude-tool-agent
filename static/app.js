/* Claude 多角色聊天室 — 完全前端逻辑
 *
 * 状态：roles / group_rules / history / api_key 全在前端 localStorage
 * 后端无状态，每次 POST 推全部 history + room 配置
 */

const STORAGE_KEYS = {
    roles: "claude_chatroom_roles",
    rules: "claude_chatroom_group_rules",
    history: "claude_chatroom_history",
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

const state = {
    roles: [],
    groupRules: "",
    history: [],
    apiKey: "",
    currentStream: null,
    editingRoleIdx: null,
    activeStreamingBubbles: new Set(),
};

/* ───── Init ───── */
document.addEventListener("DOMContentLoaded", async () => {
    loadState();
    renderRoles();
    renderMessages();
    bindEvents();
    if (!state.roles.length) {
        seedDefaultRoles();
        renderRoles();
    }
    if (!state.apiKey) openApiKeyModal();
});

function seedDefaultRoles() {
    state.roles = [
        { name: "研究员", system_prompt: "你是一位严谨的研究员，回答时喜欢引用数据和文献，先承认不确定性再给出推断。", model: "claude-haiku-4-5-20251001" },
        { name: "代码手", system_prompt: "你是一位务实的工程师，回答时给出可执行的建议和最小可工作示例，不空谈架构。", model: "claude-sonnet-5" },
    ];
    state.groupRules = "讨论时不要重复别人已经说过的话。可以在回复中用 @角色名 邀请下一位发言。每轮最多 3 次模型间对话。";
    saveState();
}

/* ───── Persistence ───── */
function loadState() {
    try { state.roles = JSON.parse(localStorage.getItem(STORAGE_KEYS.roles) || "[]"); } catch { state.roles = []; }
    state.groupRules = localStorage.getItem(STORAGE_KEYS.rules) || "";
    try { state.history = JSON.parse(localStorage.getItem(STORAGE_KEYS.history) || "[]"); } catch { state.history = []; }
    state.apiKey = localStorage.getItem(STORAGE_KEYS.apikey) || "";
}
function saveState() {
    localStorage.setItem(STORAGE_KEYS.roles, JSON.stringify(state.roles));
    localStorage.setItem(STORAGE_KEYS.rules, state.groupRules);
    localStorage.setItem(STORAGE_KEYS.history, JSON.stringify(state.history));
    localStorage.setItem(STORAGE_KEYS.apikey, state.apiKey);
}

/* ───── Roles panel ───── */
function renderRoles() {
    const list = document.getElementById("roles-list");
    list.innerHTML = "";
    state.roles.forEach((role, idx) => {
        const card = document.createElement("div");
        card.className = "role-card";
        card.innerHTML = `
            <div class="role-avatar" style="background:${roleColor(idx)}">${roleInitial(role.name)}</div>
            <div class="role-info">
                <div class="role-name">${escapeHtml(role.name)}</div>
                <div class="role-model">${escapeHtml(shortModel(role.model))}</div>
            </div>
            <button class="role-delete" title="删除">×</button>
        `;
        card.addEventListener("click", (e) => {
            if (e.target.classList.contains("role-delete")) {
                if (confirm(`删除角色「${role.name}」？`)) {
                    state.roles.splice(idx, 1);
                    saveState();
                    renderRoles();
                }
                return;
            }
            openRoleModal(idx);
        });
        list.appendChild(card);
    });
}

function roleColor(idx) { return ROLE_COLORS[idx % ROLE_COLORS.length]; }
function roleInitial(name) { return [...name].slice(0, 1).join("").toUpperCase() || "?"; }
function shortModel(m) { return (m || "").replace(/^claude-/, "").replace(/-\d+$/, ""); }

/* ───── Messages ───── */
function renderMessages() {
    const wrap = document.getElementById("messages");
    wrap.innerHTML = "";
    state.history.forEach((msg) => {
        if (msg.role === "user") appendUserMessage(msg.content);
        else appendAssistantMessage(msg.name, msg.content, false);
    });
    scrollToBottom();
}

function appendUserMessage(text) {
    const wrap = document.getElementById("messages");
    const div = document.createElement("div");
    div.className = "msg msg-user";
    div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
    wrap.appendChild(div);
    scrollToBottom();
}

function appendAssistantMessage(roleName, initialText = "", streaming = false) {
    const wrap = document.getElementById("messages");
    const idx = state.roles.findIndex(r => r.name === roleName);
    const color = idx >= 0 ? roleColor(idx) : "#888";
    const initial = idx >= 0 ? roleInitial(roleName) : "?";

    const div = document.createElement("div");
    div.className = "msg msg-assistant" + (streaming ? " streaming" : "");
    div.dataset.role = roleName;
    div.innerHTML = `
        <div class="msg-header">
            <span class="msg-avatar" style="background:${color}">${initial}</span>
            <span class="msg-author">${escapeHtml(roleName)}</span>
        </div>
        <div class="bubble">${renderMarkdown(initialText)}</div>
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
    // Find the latest streaming bubble for this role
    const wrap = document.getElementById("messages");
    const bubbles = wrap.querySelectorAll(`.msg-assistant[data-role="${cssEscape(roleName)}"]`);
    if (!bubbles.length) {
        appendAssistantMessage(roleName, delta, true);
        return;
    }
    const bubble = bubbles[bubbles.length - 1];
    // Accumulate raw text in dataset
    const accumulated = (bubble.dataset.raw || "") + delta;
    bubble.dataset.raw = accumulated;
    bubble.querySelector(".bubble").innerHTML = renderMarkdown(accumulated);
    scrollToBottom();
}

function finalizeBubble(roleName) {
    const wrap = document.getElementById("messages");
    const bubbles = wrap.querySelectorAll(`.msg-assistant[data-role="${cssEscape(roleName)}"]`);
    if (bubbles.length) {
        const bubble = bubbles[bubbles.length - 1];
        bubble.classList.remove("streaming");
        const text = bubble.dataset.raw || bubble.querySelector(".bubble").textContent;
        state.history.push({ role: "assistant", name: roleName, content: text });
        saveState();
        state.activeStreamingBubbles.delete(bubble);
    }
}

/* ───── SSE send ───── */
async function sendMessage(text) {
    if (!text.trim()) return;
    if (!state.roles.length) { showToast("请先添加至少一个角色"); return; }
    if (!state.apiKey) { openApiKeyModal(); return; }

    appendUserMessage(text);
    state.history.push({ role: "user", name: "用户", content: text });
    saveState();

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
                history: state.history.filter(m => m.content.trim() !== "" ),
                room: {
                    room_id: "default",
                    roles: state.roles,
                    group_rules: state.groupRules,
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
        const frames = buf.split("\n\n");
        buf = frames.pop();
        for (const frame of frames) parseSSEFrame(frame);
    }
}

function parseSSEFrame(frame) {
    let event = "message";
    let data = "";
    for (const line of frame.split("\n")) {
        if (!line) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    handleSSEEvent(event, data);
}

function handleSSEEvent(event, data) {
    let payload = {};
    try { payload = data && data !== "null" ? JSON.parse(data) : null; } catch {}

    switch (event) {
        case "role_start":
            appendAssistantMessage(payload.role, "", true);
            break;
        case "text":
            appendDeltaToBubble(payload.role, payload.delta);
            break;
        case "role_end":
            finalizeBubble(payload.role);
            break;
        case "error":
            appendErrorMessage(payload.message || "未知错误");
            break;
        case "done":
            // stream complete
            break;
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
    const text = e.target.value;
    const pos = e.target.selectionStart;
    // Detect @ right before cursor (no spaces)
    let i = pos - 1;
    while (i >= 0 && text[i] !== " " && text[i] !== "\n" && text[i] !== "@") i--;
    if (i >= 0 && text[i] === "@") {
        const fragment = text.slice(i + 1, pos);
        // Only trigger if fragment is empty or matches some role prefix
        const matches = state.roles.filter(r => r.name.startsWith(fragment));
        if (matches.length) {
            mentionActive = true;
            mentionStart = i;
            mentionSelectedIdx = 0;
            showMentionPopup(matches);
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

function showMentionPopup(matches) {
    const popup = document.getElementById("mention-popup");
    popup.innerHTML = "";
    matches.forEach((r, idx) => {
        const i = state.roles.indexOf(r);
        const item = document.createElement("div");
        item.className = "mention-item" + (idx === 0 ? " active" : "");
        item.innerHTML = `<span class="avatar-mini" style="background:${roleColor(i)}">${roleInitial(r.name)}</span> @${escapeHtml(r.name)}`;
        item.addEventListener("click", () => insertMention(r.name));
        popup.appendChild(item);
    });
    popup.style.display = "";
}

function updateMentionActive() {
    const items = document.querySelectorAll(".mention-item");
    items.forEach((it, i) => it.classList.toggle("active", i === mentionSelectedIdx));
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

function escapeHtml(s) {
    return (s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function cssEscape(s) {
    return (s || "").replace(/"/g, '\\"');
}

function showToast(text) {
    const t = document.getElementById("empty-roles-toast");
    t.textContent = text;
    t.style.display = "";
    setTimeout(() => t.style.display = "none", 2000);
}

/* Minimal, safe markdown renderer — enough for chat output
 * Supports: headings, bold/italic, inline code, code blocks, links,
 * blockquote, lists, hr, tables. Renders to safe HTML via escaped text. */
function renderMarkdown(md) {
    let text = md || "";

    // Extract fenced code blocks first (so their content isn't markdown-processed)
    const codeBlocks = [];
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        codeBlocks.push({ lang, code });
        return ` CODE${codeBlocks.length - 1} `;
    });

    // Escape HTML
    text = escapeHtml(text);

    // Inline code
    text = text.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);

    // Bold + italic
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");

    // Links [text](url)
    text = text.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Headings
    text = text.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    text = text.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    text = text.replace(/^# (.+)$/gm, "<h1>$1</h1>");

    // Horizontal rule
    text = text.replace(/^---$/gm, "<hr>");

    // Blockquote
    text = text.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");

    // Lists (very rough)
    text = text.replace(/^(\s*)[-*] (.+)$/gm, '<li>$2</li>');
    text = text.replace(/(<li>[\s\S]*?<\/li>)(?!\s*<li>)/g, "<ul>$1</ul>");
    text = text.replace(/^(\s*)\d+\. (.+)$/gm, '<li>$2</li>');

    // Tables (very simple: rows separated by |, header separator line)
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

    // Paragraphs — wrap loose text blocks
    text = text.split(/\n{2,}/).map(chunk => {
        if (/^\s*<(h\d|ul|ol|li|pre|blockquote|table|hr)/.test(chunk)) return chunk;
        if (chunk.includes(" CODE")) return chunk;
        return `<p>${chunk.replace(/\n/g, "<br>")}</p>`;
    }).join("\n");

    // Restore code blocks
    text = text.replace(/ CODE(\d+) /g, (_, i) => {
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

    document.getElementById("btn-add-role").addEventListener("click", () => openRoleModal(null));
    document.getElementById("btn-rules").addEventListener("click", openRulesModal);
    document.getElementById("btn-apikey").addEventListener("click", openApiKeyModal);
    document.getElementById("btn-clear").addEventListener("click", () => {
        if (!confirm("清空所有对话历史？")) return;
        state.history = [];
        saveState();
        renderMessages();
    });

    document.getElementById("btn-export-roles").addEventListener("click", exportRoles);
    document.getElementById("btn-import-roles").addEventListener("click", () => {
        document.getElementById("import-roles-file").click();
    });
    document.getElementById("import-roles-file").addEventListener("change", importRoles);

    bindRoleModal();
    bindRulesModal();
    bindApiKeyModal();
}

/* ───── Role modal ───── */
function openRoleModal(idx) {
    state.editingRoleIdx = idx;
    const modal = document.getElementById("role-modal");
    const nameInput = document.getElementById("role-name");
    const promptInput = document.getElementById("role-prompt");
    const modelSelect = document.getElementById("role-model");

    // Populate model dropdown with all options
    modelSelect.innerHTML = DEFAULT_MODELS.map(m => `<option value="${m.value}">${m.label}</option>`).join("");

    if (idx === null) {
        document.getElementById("role-modal-title").textContent = "新增角色";
        nameInput.value = "";
        promptInput.value = "";
        modelSelect.value = DEFAULT_MODELS[0].value;
    } else {
        document.getElementById("role-modal-title").textContent = "编辑角色";
        const r = state.roles[idx];
        nameInput.value = r.name;
        promptInput.value = r.system_prompt;
        modelSelect.value = r.model;
        if (![...modelSelect.options].some(o => o.value === r.model)) {
            const opt = document.createElement("option");
            opt.value = r.model; opt.textContent = r.model + " (custom)";
            modelSelect.appendChild(opt);
            modelSelect.value = r.model;
        }
    }
    modal.style.display = "";
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
        if (state.editingRoleIdx === null) {
            state.roles.push(role);
        } else {
            state.roles[state.editingRoleIdx] = role;
        }
        saveState();
        renderRoles();
        document.getElementById("role-modal").style.display = "none";
    });
}

/* ───── Rules modal ───── */
function openRulesModal() {
    document.getElementById("rules-input").value = state.groupRules;
    document.getElementById("rules-modal").style.display = "";
}
function bindRulesModal() {
    document.getElementById("rules-cancel").addEventListener("click", () => {
        document.getElementById("rules-modal").style.display = "none";
    });
    document.getElementById("rules-save").addEventListener("click", () => {
        state.groupRules = document.getElementById("rules-input").value;
        saveState();
        document.getElementById("rules-modal").style.display = "none";
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
    });
}

/* ───── Export / import ───── */
function exportRoles() {
    const data = { roles: state.roles, group_rules: state.groupRules };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "claude-chatroom-roles.json";
    a.click();
    URL.revokeObjectURL(url);
}

function importRoles(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
        try {
            const data = JSON.parse(reader.result);
            if (Array.isArray(data.roles)) state.roles = data.roles;
            if (typeof data.group_rules === "string") state.groupRules = data.group_rules;
            saveState();
            renderRoles();
            showToast("已导入角色配置");
        } catch (err) {
            showToast("导入失败：JSON 格式错误");
        }
    };
    reader.readAsText(file);
    e.target.value = "";
}
