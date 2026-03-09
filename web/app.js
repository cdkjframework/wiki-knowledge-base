const menuItems = Array.from(document.querySelectorAll('.menu-item'));
const toast = document.getElementById('toast');
const chunkState = {
  pageIndex: 1,
  pageSize: 8,
  total: 0,
};
let documentsList = [];
let modelConfigsList = [];
const chatUserInput = document.getElementById('chat-user-id');
const chatSessionInput = document.getElementById('chat-session-id');
const newSessionBtn = document.getElementById('btn-new-session');
const clearHistoryBtn = document.getElementById('btn-clear-history');
const chunkDialog = document.getElementById('chunk-dialog');
const chunkDialogTitle = document.getElementById('chunk-dialog-title');
const chunkDialogText = document.getElementById('chunk-dialog-text');
const chunkDialogClose = document.getElementById('chunk-dialog-close');
const chunkDialogCancel = document.getElementById('chunk-dialog-cancel');
const chunkDialogSave = document.getElementById('chunk-dialog-save');
const chunkEditState = {
  id: null,
  filename: '',
};

function renderKnowledgeSources(results = [], statusText = '') {
  const list = document.getElementById('sources-list');
  const title = document.getElementById('sources-title');
  if (!list || !title) return;

  const items = Array.isArray(results) ? results : [];
  title.textContent = items.length > 0 ? `知识来源 (${items.length})` : '知识来源';
  list.innerHTML = '';

  if (statusText && items.length === 0) {
    const loading = document.createElement('div');
    loading.className = 'sources-empty';
    loading.textContent = statusText;
    list.appendChild(loading);
    return;
  }

  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'sources-empty';
    empty.textContent = '未检索到相关来源';
    list.appendChild(empty);
    return;
  }

  items.forEach((item, idx) => {
    const card = document.createElement('div');
    card.className = 'source-item';

    const header = document.createElement('div');
    header.className = 'source-header';

    const name = document.createElement('div');
    name.className = 'source-name';
    name.textContent = `${idx + 1}. ${String(item.filename || 'unknown')}`;

    const score = document.createElement('div');
    score.className = 'source-score';
    const sim = item.similarity != null ? Number(item.similarity) : null;
    score.textContent = sim == null || Number.isNaN(sim) ? '-' : sim.toFixed(3);

    const text = document.createElement('div');
    text.className = 'source-text';
    text.textContent = String(item.text || item.chunk || item.content || '').slice(0, 180) || '（无内容预览）';

    header.appendChild(name);
    header.appendChild(score);
    card.appendChild(header);
    card.appendChild(text);
    list.appendChild(card);
  });
}

function showToast(message, ok = true) {
  toast.innerHTML = `
    <div class="toast-overlay">
      <div class="toast-dialog ${ok ? 'ok' : 'err'}">
        <div class="toast-icon">${ok ? '✓' : '✕'}</div>
        <div class="toast-message">${String(message).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
        <button class="toast-close" onclick="this.closest('.toast').className='toast'">&times;</button>
      </div>
    </div>
  `;
  toast.className = 'toast show';
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => {
    toast.className = 'toast';
  }, 3200);
}

async function apiRequest(path, options = {}) {
  const init = { method: 'GET', ...options };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    };
    init.body = JSON.stringify(init.body);
  }

  const resp = await fetch(path, init);
  const payload = await resp.json().catch(() => ({}));

  const wrappedCode = Number(payload?.code || resp.status);
  const data = Object.prototype.hasOwnProperty.call(payload || {}, 'data') ? payload.data : payload;
  if (!resp.ok || wrappedCode >= 400) {
    const msg = data?.error || payload?.error || `Request failed (${wrappedCode})`;
    throw new Error(String(msg));
  }
  return data;
}

function addReferencesToMessage(results) {
  if (!Array.isArray(results) || results.length === 0) return;
  renderKnowledgeSources(results);

  const messagesContainer = document.getElementById('chat-messages');
  const messages = messagesContainer.querySelectorAll('.chat-message.assistant');
  if (messages.length === 0) return;
  
  const lastMessage = messages[messages.length - 1];
  const content = lastMessage.querySelector('.message-content');
  
  // 移除旧的操作栏
  const oldActions = content.querySelector('.message-actions');
  if (oldActions) {
    oldActions.remove();
  }
  
  // 创建操作栏
  const actionsBar = document.createElement('div');
  actionsBar.className = 'message-actions';
  
  // 复制按钮
  const copyBtn = document.createElement('button');
  copyBtn.className = 'action-btn copy-btn';
  copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  copyBtn.title = '复制回答';
  copyBtn.addEventListener('click', () => {
    const bubble = lastMessage.querySelector('.message-bubble');
    const text = bubble.innerText || bubble.textContent;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      setTimeout(() => {
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
      }, 1500);
    }).catch(() => {});
  });
  
  // 引用文档
  const refBtn = document.createElement('button');
  refBtn.className = 'action-btn ref-btn';
  const refCount = results.length;
  refBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg><span class="ref-count">${refCount}</span>`;
  
  // 创建引用列表
  const refList = document.createElement('div');
  refList.className = 'ref-tooltip';
  const refTitle = document.createElement('div');
  refTitle.className = 'ref-tooltip-title';
  refTitle.textContent = '引用文档';
  refList.appendChild(refTitle);
  
  results.forEach((item, index) => {
    const refItem = document.createElement('div');
    refItem.className = 'ref-item';
    const fileName = document.createElement('span');
    fileName.className = 'ref-filename';
    fileName.textContent = String(item.filename || 'unknown');
    const similarity = document.createElement('span');
    similarity.className = 'ref-similarity';
    const simValue = item.similarity != null ? (item.similarity * 100).toFixed(1) + '%' : '-';
    similarity.textContent = simValue;
    refItem.appendChild(fileName);
    refItem.appendChild(similarity);
    refList.appendChild(refItem);
  });
  
  const refContainer = document.createElement('div');
  refContainer.className = 'ref-container';
  refContainer.appendChild(refBtn);
  refContainer.appendChild(refList);
  
  actionsBar.appendChild(copyBtn);
  actionsBar.appendChild(refContainer);
  
  content.appendChild(actionsBar);
}

function addUserMessage(text) {
  const messagesContainer = document.getElementById('chat-messages');
  const welcome = messagesContainer.querySelector('.chat-welcome');
  if (welcome) {
    welcome.remove();
  }

  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message user';
  
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '我';
  
  const content = document.createElement('div');
  content.className = 'message-content';
  
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;
  
  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  
  content.appendChild(bubble);
  content.appendChild(time);
  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);
  messagesContainer.appendChild(messageDiv);
  
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addAssistantMessage(text, isLoading = false) {
  const messagesContainer = document.getElementById('chat-messages');
  const welcome = messagesContainer.querySelector('.chat-welcome');
  if (welcome) {
    welcome.remove();
  }

  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message assistant';
  messageDiv.dataset.messageId = Date.now();
  
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'AI';
  
  const content = document.createElement('div');
  content.className = 'message-content';
  
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  if (isLoading) {
    bubble.classList.add('loading');
    bubble.innerHTML = '<span class="loading-dots">正在思考</span>';
  } else {
    bubble.innerHTML = renderMessageContent(text);
  }
  
  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  
  content.appendChild(bubble);
  content.appendChild(time);
  messageDiv.appendChild(avatar);
  messageDiv.appendChild(content);
  messagesContainer.appendChild(messageDiv);
  
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return messageDiv;
}

function updateLastAssistantMessage(text) {
  const messagesContainer = document.getElementById('chat-messages');
  const messages = messagesContainer.querySelectorAll('.chat-message.assistant');
  if (messages.length === 0) return;
  
  const lastMessage = messages[messages.length - 1];
  const bubble = lastMessage.querySelector('.message-bubble');
  bubble.classList.remove('loading');
  bubble.innerHTML = renderMessageContent(text);
  
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function renderMessageContent(text) {
  const raw = String(text || '');
  if (window.marked) {
    const html = window.marked.parse(raw, { breaks: true });
    return window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
  }
  return renderMarkdownFallback(raw);
}

function appendThinkingSummary(container, summary) {
  if (!container || !summary) return;
  const existing = container.querySelector('.message-thinking');
  if (existing) {
    existing.remove();
  }
  const wrap = document.createElement('div');
  wrap.className = 'message-thinking';
  const title = document.createElement('div');
  title.className = 'thinking-title';
  title.textContent = '思考摘要';
  const body = document.createElement('div');
  body.className = 'thinking-body';
  body.innerHTML = renderMessageContent(summary);
  wrap.appendChild(title);
  wrap.appendChild(body);
  container.appendChild(wrap);
}

function addThinkingSummaryToLastAssistant(summary) {
  if (!summary) return;
  const messagesContainer = document.getElementById('chat-messages');
  const messages = messagesContainer.querySelectorAll('.chat-message.assistant');
  if (messages.length === 0) return;
  const lastMessage = messages[messages.length - 1];
  const content = lastMessage.querySelector('.message-content');
  appendThinkingSummary(content, summary);
}

function loadSessionToChat(session) {
  // 更新右侧的 Session ID 输入框
  if (session.session_id) {
    chatSessionInput.value = session.session_id;
  }
  if (session.user_id) {
    chatUserInput.value = session.user_id;
  }
  
  // 清空聊天区域
  const messagesContainer = document.getElementById('chat-messages');
  messagesContainer.innerHTML = '';
  
  const items = session.items || [];
  if (items.length === 0) {
    showToast('该会话没有记录', false);
    return;
  }
  
  // 遍历session中的所有对话
  for (const historyItem of items) {
    const request = historyItem?.request || {};
    const response = historyItem?.response || {};
    const query = request.query || '新建聊天';
    const answer = response.answer || historyItem?.error || '无回答';
    const results = response.results || [];
    // thinking_summary 可能在顶层(数据库字段)或在 response 中(新消息)
    const thinkingSummary = historyItem?.thinking_summary || response.thinking_summary || '';
    
    // 添加用户问题
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    
    const userAvatar = document.createElement('div');
    userAvatar.className = 'message-avatar';
    userAvatar.textContent = '我';
    
    const userContent = document.createElement('div');
    userContent.className = 'message-content';
    
    const userBubble = document.createElement('div');
    userBubble.className = 'message-bubble';
    userBubble.textContent = query;
    
    const userTime = document.createElement('div');
    userTime.className = 'message-time';
    userTime.textContent = formatHistoryTime(historyItem?.timestamp);
    
    userContent.appendChild(userBubble);
    userContent.appendChild(userTime);
    userMsg.appendChild(userAvatar);
    userMsg.appendChild(userContent);
    messagesContainer.appendChild(userMsg);
    
    // 添加AI回答
    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-message assistant';
    
    const aiAvatar = document.createElement('div');
    aiAvatar.className = 'message-avatar';
    aiAvatar.textContent = 'AI';
    
    const aiContent = document.createElement('div');
    aiContent.className = 'message-content';
    
    const aiBubble = document.createElement('div');
    aiBubble.className = 'message-bubble';
    aiBubble.innerHTML = renderMessageContent(answer);
    
    const aiTime = document.createElement('div');
    aiTime.className = 'message-time';
    aiTime.textContent = formatHistoryTime(historyItem?.timestamp);
    
    aiContent.appendChild(aiBubble);
    aiContent.appendChild(aiTime);
    
    // 添加操作栏（复制按钮和引用文档）
    if (results.length > 0) {
      const actionsBar = createActionsBar(aiBubble, results);
      aiContent.appendChild(actionsBar);
    }

    if (thinkingSummary) {
      appendThinkingSummary(aiContent, thinkingSummary);
    }
    
    aiMsg.appendChild(aiAvatar);
    aiMsg.appendChild(aiContent);
    messagesContainer.appendChild(aiMsg);
  }
  
  // 滚动到底部
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  const last = items[items.length - 1] || {};
  const lastResults = last?.response?.results || [];
  renderKnowledgeSources(lastResults);

  showToast(`已加载会话（${items.length}条对话）`);
}

function createActionsBar(aiBubble, results) {
  const actionsBar = document.createElement('div');
  actionsBar.className = 'message-actions';
  
  // 复制按钮
  const copyBtn = document.createElement('button');
  copyBtn.className = 'action-btn copy-btn';
  copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  copyBtn.title = '复制回答';
  copyBtn.addEventListener('click', () => {
    const text = aiBubble.innerText || aiBubble.textContent;
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
      setTimeout(() => {
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
      }, 1500);
    }).catch(() => {});
  });
  
  // 引用文档
  const refBtn = document.createElement('button');
  refBtn.className = 'action-btn ref-btn';
  const refCount = results.length;
  refBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg><span class="ref-count">${refCount}</span>`;
  
  // 创建引用列表
  const refList = document.createElement('div');
  refList.className = 'ref-tooltip';
  const refTitle = document.createElement('div');
  refTitle.className = 'ref-tooltip-title';
  refTitle.textContent = '引用文档';
  refList.appendChild(refTitle);
  
  results.forEach((item) => {
    const refItem = document.createElement('div');
    refItem.className = 'ref-item';
    const fileName = document.createElement('span');
    fileName.className = 'ref-filename';
    fileName.textContent = String(item.filename || 'unknown');
    const similarity = document.createElement('span');
    similarity.className = 'ref-similarity';
    const simValue = item.similarity != null ? (item.similarity * 100).toFixed(1) + '%' : '-';
    similarity.textContent = simValue;
    refItem.appendChild(fileName);
    refItem.appendChild(similarity);
    refList.appendChild(refItem);
  });
  
  const refContainer = document.createElement('div');
  refContainer.className = 'ref-container';
  refContainer.appendChild(refBtn);
  refContainer.appendChild(refList);
  
  actionsBar.appendChild(copyBtn);
  actionsBar.appendChild(refContainer);
  
  return actionsBar;
}

function loadSessionToChat(session) {
  // 更新右侧的 Session ID 输入框
  if (session.session_id) {
    chatSessionInput.value = session.session_id;
  }
  if (session.user_id) {
    chatUserInput.value = session.user_id;
  }
  
  // 清空聊天区域
  const messagesContainer = document.getElementById('chat-messages');
  messagesContainer.innerHTML = '';
  
  const items = session.items || [];
  if (items.length === 0) {
    showToast('该会话没有记录', false);
    return;
  }
  
  // 遍历session中的所有对话
  for (const historyItem of items) {
    const request = historyItem?.request || {};
    const response = historyItem?.response || {};
    const query = request.query || '新建聊天';
    const answer = response.answer || historyItem?.error || '无回答';
    const results = response.results || [];
    // thinking_summary 可能在顶层(数据库字段)或在 response 中(新消息)
    const thinkingSummary = historyItem?.thinking_summary || response.thinking_summary || '';
    
    // 添加用户问题
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user';
    
    const userAvatar = document.createElement('div');
    userAvatar.className = 'message-avatar';
    userAvatar.textContent = '我';
    
    const userContent = document.createElement('div');
    userContent.className = 'message-content';
    
    const userBubble = document.createElement('div');
    userBubble.className = 'message-bubble';
    userBubble.textContent = query;
    
    const userTime = document.createElement('div');
    userTime.className = 'message-time';
    userTime.textContent = formatHistoryTime(historyItem?.timestamp);
    
    userContent.appendChild(userBubble);
    userContent.appendChild(userTime);
    userMsg.appendChild(userAvatar);
    userMsg.appendChild(userContent);
    messagesContainer.appendChild(userMsg);
    
    // 添加AI回答
    const aiMsg = document.createElement('div');
    aiMsg.className = 'chat-message assistant';
    
    const aiAvatar = document.createElement('div');
    aiAvatar.className = 'message-avatar';
    aiAvatar.textContent = 'AI';
    
    const aiContent = document.createElement('div');
    aiContent.className = 'message-content';
    
    const aiBubble = document.createElement('div');
    aiBubble.className = 'message-bubble';
    aiBubble.innerHTML = renderMessageContent(answer);
    
    const aiTime = document.createElement('div');
    aiTime.className = 'message-time';
    aiTime.textContent = formatHistoryTime(historyItem?.timestamp);
    
    aiContent.appendChild(aiBubble);
    aiContent.appendChild(aiTime);
    
    // 添加操作栏（复制按钮和引用文档）
    if (results.length > 0) {
      const actionsBar = createActionsBar(aiBubble, results);
      aiContent.appendChild(actionsBar);
    }

    // 添加思考摘要
    if (thinkingSummary) {
      appendThinkingSummary(aiContent, thinkingSummary);
    }
    
    aiMsg.appendChild(aiAvatar);
    aiMsg.appendChild(aiContent);
    messagesContainer.appendChild(aiMsg);
  }
  
  // 滚动到底部
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  const last = items[items.length - 1] || {};
  const lastResults = last?.response?.results || [];
  renderKnowledgeSources(lastResults);
}

function loadHistoryToChat(historyItem) {
  // 清空聊天区域
  const messagesContainer = document.getElementById('chat-messages');
  messagesContainer.innerHTML = '';
  
  // 获取请求和响应数据
  const request = historyItem?.request || {};
  const response = historyItem?.response || {};
  const query = request.query || '新建聊天';
  const answer = response.answer || historyItem?.error || '无回答';
  const results = response.results || [];
  // thinking_summary 可能在顶层(数据库字段)或在 response 中(新消息)
  const thinkingSummary = historyItem?.thinking_summary || response.thinking_summary || '';
  
  // 添加用户问题
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-message user';
  
  const userAvatar = document.createElement('div');
  userAvatar.className = 'message-avatar';
  userAvatar.textContent = '我';
  
  const userContent = document.createElement('div');
  userContent.className = 'message-content';
  
  const userBubble = document.createElement('div');
  userBubble.className = 'message-bubble';
  userBubble.textContent = query;
  
  const userTime = document.createElement('div');
  userTime.className = 'message-time';
  userTime.textContent = formatHistoryTime(historyItem?.timestamp);
  
  userContent.appendChild(userBubble);
  userContent.appendChild(userTime);
  userMsg.appendChild(userAvatar);
  userMsg.appendChild(userContent);
  messagesContainer.appendChild(userMsg);
  
  // 添加AI回答
  const aiMsg = document.createElement('div');
  aiMsg.className = 'chat-message assistant';
  
  const aiAvatar = document.createElement('div');
  aiAvatar.className = 'message-avatar';
  aiAvatar.textContent = 'AI';
  
  const aiContent = document.createElement('div');
  aiContent.className = 'message-content';
  
  const aiBubble = document.createElement('div');
  aiBubble.className = 'message-bubble';
  aiBubble.innerHTML = renderMessageContent(answer);
  
  const aiTime = document.createElement('div');
  aiTime.className = 'message-time';
  aiTime.textContent = formatHistoryTime(historyItem?.timestamp);
  
  aiContent.appendChild(aiBubble);
  aiContent.appendChild(aiTime);
  
  // 添加操作栏（复制按钮和引用文档）
  if (results.length > 0) {
    const actionsBar = document.createElement('div');
    actionsBar.className = 'message-actions';
    
    // 复制按钮
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn copy-btn';
    copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    copyBtn.title = '复制回答';
    copyBtn.addEventListener('click', () => {
      const text = aiBubble.innerText || aiBubble.textContent;
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        setTimeout(() => {
          copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
        }, 1500);
      }).catch(() => {});
    });
    
    // 引用文档
    const refBtn = document.createElement('button');
    refBtn.className = 'action-btn ref-btn';
    const refCount = results.length;
    refBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg><span class="ref-count">${refCount}</span>`;
    
    // 创建引用列表
    const refList = document.createElement('div');
    refList.className = 'ref-tooltip';
    const refTitle = document.createElement('div');
    refTitle.className = 'ref-tooltip-title';
    refTitle.textContent = '引用文档';
    refList.appendChild(refTitle);
    
    results.forEach((item) => {
      const refItem = document.createElement('div');
      refItem.className = 'ref-item';
      const fileName = document.createElement('span');
      fileName.className = 'ref-filename';
      fileName.textContent = String(item.filename || 'unknown');
      const similarity = document.createElement('span');
      similarity.className = 'ref-similarity';
      const simValue = item.similarity != null ? (item.similarity * 100).toFixed(1) + '%' : '-';
      similarity.textContent = simValue;
      refItem.appendChild(fileName);
      refItem.appendChild(similarity);
      refList.appendChild(refItem);
    });
    
    const refContainer = document.createElement('div');
    refContainer.className = 'ref-container';
    refContainer.appendChild(refBtn);
    refContainer.appendChild(refList);
    
    actionsBar.appendChild(copyBtn);
    actionsBar.appendChild(refContainer);
    aiContent.appendChild(actionsBar);
  }

  if (thinkingSummary) {
    appendThinkingSummary(aiContent, thinkingSummary);
  }
  
  aiMsg.appendChild(aiAvatar);
  aiMsg.appendChild(aiContent);
  messagesContainer.appendChild(aiMsg);
  
  // 滚动到底部
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  renderKnowledgeSources(results);
}


function formatHistoryTime(raw) {
  if (!raw) return '未知时间';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return String(raw);
  return date.toLocaleString('zh-CN', { hour12: false });
}

function pickHistoryTitle(item) {
  const query = item?.request?.query;
  if (query) return String(query).slice(0, 120);
  if (item?.action) return `动作：${item.action}`;
  return '未命名记录';
}

function renderHistory(history) {
  const list = document.getElementById('history-list');
  list.innerHTML = '';
  if (!Array.isArray(history) || history.length === 0) {
    list.innerHTML = '<li class="history-item history-empty">暂无历史</li>';
    return;
  }
  
  // 只显示前20条
  const displayHistory = history.slice(0, 20);
  
  for (const session of displayHistory) {
    const li = document.createElement('li');
    li.className = 'history-item';
    
    // 显示第一个问题作为标题
    const firstQuery = session.first_query || pickHistoryTitle(session.items?.[0] || {});
    const displayTitle = String(firstQuery).trim();
    li.textContent = displayTitle;
    li.title = displayTitle; // 鼠标悬停显示完整文本
    
    // 添加点击事件，显示整个session的对话
    li.addEventListener('click', (e) => {
      loadSessionToChat(session);
    });
    
    list.appendChild(li);
  }
}

async function runChat(event) {
  event.preventDefault();
  const query = document.getElementById('chat-query').value.trim();
  if (!query) {
    showToast('问题不能为空', false);
    return;
  }

  const userId = chatUserInput.value.trim();
  if (!userId) {
    showToast('用户ID不能为空', false);
    return;
  }

  const k = Number(document.getElementById('chat-k').value || 2);
  const thresholdRaw = document.getElementById('chat-threshold').value.trim();
  const generateAnswer = document.getElementById('chat-generate').value === 'true';
  const deepThink = document.getElementById('chat-deep-think').checked;
  
  // 添加用户消息到聊天框
  addUserMessage(query);
  renderKnowledgeSources([], '正在检索知识来源...');

  // 立即显示AI等待消息
  addAssistantMessage('', true);
  
  // 清空输入框并重置高度
  const queryInput = document.getElementById('chat-query');
  queryInput.value = '';
  queryInput.style.height = 'auto';

  const body = {
    query,
    k: Number.isFinite(k) && k > 0 ? Math.floor(k) : 2,
    generate_answer: generateAnswer,
    deep_think: deepThink,
    user_id: userId,
  };
  const selectedModelConfigId = document.getElementById('chat-model-config')?.value?.trim() || '';
  const useDefaultModelConfig = document.getElementById('chat-use-default-model')?.value === 'true';
  if (useDefaultModelConfig) {
    body.use_default_model_config = true;
  } else if (selectedModelConfigId) {
    body.model_config_id = Number(selectedModelConfigId);
  }
  let sessionId = chatSessionInput.value.trim();
  if (!sessionId) {
    sessionId = await ensureSessionId(userId);
  }
  if (sessionId) {
    body.session_id = sessionId;
  }
  if (thresholdRaw) {
    const threshold = Number(thresholdRaw);
    if (!Number.isFinite(threshold)) {
      showToast('相关性阈值必须是数字', false);
      return;
    }
    if (threshold <= 0) {
      showToast('相关性阈值必须大于 0', false);
      return;
    }
    if (threshold < 0.5) {
      showToast('相关性阈值是距离阈值，建议 0.8-1.6；过小会过滤掉大部分结果', false);
      return;
    }
    body.relevance_threshold = threshold;
  }

  try {
    await runChatStream(body);
    refreshHistory().catch(() => {});
  } catch (error) {
    addAssistantMessage('抱歉，查询失败。请稍后重试。');
    showToast(error.message || '请求失败', false);
  }
}

function renderMarkdownFallback(input) {
  const escapeHtml = (val) => String(val)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const parseInline = (text) => {
    let out = escapeHtml(text);
    out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return out;
  };

  const lines = String(input || '').replace(/\r\n/g, '\n').split('\n');
  const html = [];
  let i = 0;

  const isTableSeparator = (line) => /^\s*\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$/.test(line);
  const splitTableRow = (line) => line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => parseInline(cell.trim()));

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('```')) {
      const lang = line.replace('```', '').trim();
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith('```')) {
        buf.push(lines[i]);
        i += 1;
      }
      html.push(`<pre><code class="language-${escapeHtml(lang)}">${escapeHtml(buf.join('\n'))}</code></pre>`);
      i += 1;
      continue;
    }

    if (line.includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      const headerCells = splitTableRow(line);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && lines[i].includes('|')) {
        const rowCells = splitTableRow(lines[i]);
        bodyRows.push(`<tr>${rowCells.map((cell) => `<td>${cell}</td>`).join('')}</tr>`);
        i += 1;
      }
      html.push(
        `<table><thead><tr>${headerCells.map((cell) => `<th>${cell}</th>`).join('')}</tr></thead>`
        + `<tbody>${bodyRows.join('')}</tbody></table>`
      );
      continue;
    }

    if (/^>\s+/.test(line)) {
      const block = [];
      while (i < lines.length && /^>\s+/.test(lines[i])) {
        block.push(lines[i].replace(/^>\s+/, ''));
        i += 1;
      }
      html.push(`<blockquote>${parseInline(block.join('<br>'))}</blockquote>`);
      continue;
    }

    if (/^\s*([-*])\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*([-*])\s+/.test(lines[i])) {
        items.push(`<li>${parseInline(lines[i].replace(/^\s*([-*])\s+/, ''))}</li>`);
        i += 1;
      }
      html.push(`<ul>${items.join('')}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(`<li>${parseInline(lines[i].replace(/^\s*\d+\.\s+/, ''))}</li>`);
        i += 1;
      }
      html.push(`<ol>${items.join('')}</ol>`);
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      const level = Math.min(6, line.match(/^#{1,6}/)[0].length);
      const content = line.replace(/^#{1,6}\s+/, '');
      html.push(`<h${level}>${parseInline(content)}</h${level}>`);
      i += 1;
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const para = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !/^#{1,6}\s+/.test(lines[i])) {
      if (
        lines[i].startsWith('```')
        || /^\s*([-*])\s+/.test(lines[i])
        || /^\s*\d+\.\s+/.test(lines[i])
        || /^>\s+/.test(lines[i])
      ) {
        break;
      }
      para.push(lines[i]);
      i += 1;
    }
    html.push(`<p>${parseInline(para.join(' '))}</p>`);
  }

  return html.join('');
}

async function refreshHistory() {
  const data = await apiRequest('/history?limit=20&action=query&group_by_session=true');
  renderHistory(data.sessions || []);
}

async function deleteHistory(id) {
  await apiRequest(`/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
  showToast('记录已删除');
  await refreshHistory();
}

async function runChatStream(body) {
  const resp = await fetch('/query?stream=1', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ ...body, stream: true }),
  });

  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => '');
    throw new Error(text || `Request failed (${resp.status})`);
  }

  let answer = '';
  const reader = resp.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const handleEvent = (eventType, dataText) => {
    if (!dataText) return;
    let payload;
    try {
      payload = JSON.parse(dataText);
    } catch (error) {
      return;
    }
    if (eventType === 'meta') {
      const refs = payload.results || [];
      addReferencesToMessage(refs);
      renderKnowledgeSources(refs);
      if (payload.session_id) {
        chatSessionInput.value = String(payload.session_id);
      }
      return;
    }
    if (eventType === 'delta') {
      const delta = String(payload.delta || '');
      if (!delta) return;
      
      answer += delta;
      updateLastAssistantMessage(answer);
      return;
    }
    if (eventType === 'done') {
      const summary = String(payload.thinking_summary || '').trim();
      if (summary) {
        addThinkingSummaryToLastAssistant(summary);
      }
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx = buffer.indexOf('\n\n');
    while (idx >= 0) {
      const raw = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (raw) {
        const lines = raw.split('\n');
        let eventType = 'message';
        const dataLines = [];
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trim());
          }
        }
        handleEvent(eventType, dataLines.join('\n'));
      }
      idx = buffer.indexOf('\n\n');
    }
  }
}

async function ensureSessionId(userId) {
  const data = await apiRequest(`/session?user_id=${encodeURIComponent(userId)}`);
  const sessionId = String(data.session_id || '');
  if (sessionId) {
    chatSessionInput.value = sessionId;
  }
  return sessionId;
}

function resetModelForm() {
  const form = document.getElementById('model-config-form');
  if (!form) return;
  form.reset();
  document.getElementById('model-config-id').value = '';
  document.getElementById('model-temperature').value = '0.7';
  document.getElementById('model-timeout').value = '30';
  document.getElementById('model-is-active').checked = true;
  document.getElementById('model-is-default').checked = false;
}

function openModelModal(isEdit = false) {
  const modal = document.getElementById('model-config-modal');
  const title = document.getElementById('modal-title');
  if (!modal) return;
  
  if (title) {
    title.textContent = isEdit ? '编辑模型配置' : '新增模型配置';
  }
  
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeModelModal() {
  const modal = document.getElementById('model-config-modal');
  if (!modal) return;
  
  modal.classList.remove('show');
  document.body.style.overflow = '';
}

function openRetrievalSettingsModal() {
  const modal = document.getElementById('retrieval-settings-modal');
  if (!modal) return;
  
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeRetrievalSettingsModal() {
  const modal = document.getElementById('retrieval-settings-modal');
  if (!modal) return;
  
  modal.classList.remove('show');
  document.body.style.overflow = '';
}

function openAddDocModal() {
  const modal = document.getElementById('add-doc-modal');
  if (!modal) return;
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeAddDocModal() {
  const modal = document.getElementById('add-doc-modal');
  if (!modal) return;
  modal.classList.remove('show');
  document.body.style.overflow = '';
}

function openUploadModal() {
  const modal = document.getElementById('upload-modal');
  if (!modal) return;
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeUploadModal() {
  const modal = document.getElementById('upload-modal');
  if (!modal) return;
  modal.classList.remove('show');
  document.body.style.overflow = '';
}

function openBatchUploadModal() {
  const modal = document.getElementById('batch-upload-modal');
  if (!modal) return;
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeBatchUploadModal() {
  const modal = document.getElementById('batch-upload-modal');
  if (!modal) return;
  modal.classList.remove('show');
  document.body.style.overflow = '';
}

function fillModelForm(config) {
  if (!config) return;
  document.getElementById('model-config-id').value = String(config.id ?? '');
  document.getElementById('model-name').value = String(config.name || '');
  document.getElementById('model-provider').value = String(config.provider || '');
  document.getElementById('model-base-url').value = String(config.base_url || '');
  document.getElementById('model-model-name').value = String(config.model_name || '');
  document.getElementById('model-api-key').value = '';
  document.getElementById('model-temperature').value = config.temperature != null ? String(config.temperature) : '0.7';
  document.getElementById('model-max-tokens').value = config.max_tokens != null ? String(config.max_tokens) : '';
  document.getElementById('model-timeout').value = config.timeout != null ? String(config.timeout) : '30';
  document.getElementById('model-description').value = String(config.description || '');
  document.getElementById('model-is-active').checked = Boolean(config.is_active);
  document.getElementById('model-is-default').checked = Boolean(config.is_default);
  openModelModal(true);
}

function renderProviderOptions(providers) {
  const providerSelect = document.getElementById('model-provider');
  if (!providerSelect) return;
  providerSelect.innerHTML = '';
  if (!Array.isArray(providers) || providers.length === 0) {
    providerSelect.innerHTML = '<option value="">-- 无可用 provider --</option>';
    return;
  }
  for (const item of providers) {
    const option = document.createElement('option');
    option.value = String(item.name || '');
    option.textContent = String(item.name || '');
    providerSelect.appendChild(option);
  }
}

function updateChatModelSelect(configs) {
  const select = document.getElementById('chat-model-config');
  if (!select) return;
  const prev = select.value;
  select.innerHTML = '<option value="">-- 自动/内置模型 --</option>';
  if (Array.isArray(configs)) {
    for (const cfg of configs) {
      const option = document.createElement('option');
      option.value = String(cfg.id ?? '');
      const defaultMark = cfg.is_default ? ' [默认]' : '';
      const activeMark = cfg.is_active ? '' : ' [停用]';
      option.textContent = `${String(cfg.name || '-')}${defaultMark}${activeMark}`;
      select.appendChild(option);
    }
  }
  if (prev && Array.from(select.options).some((opt) => opt.value === prev)) {
    select.value = prev;
  }
}

function renderModelConfigsTable(configs) {
  const tbody = document.getElementById('model-configs-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  if (!Array.isArray(configs) || configs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7">暂无模型配置</td></tr>';
    return;
  }

  for (const cfg of configs) {
    const tr = document.createElement('tr');
    const activeText = cfg.is_active ? '启用' : '停用';
    const defaultText = cfg.is_default ? '是' : '否';
    tr.innerHTML = `
      <td>${Number(cfg.id || 0)}</td>
      <td>${String(cfg.name || '-')}</td>
      <td>${String(cfg.provider || '-')}</td>
      <td>${String(cfg.model_name || '-')}</td>
      <td>${activeText}</td>
      <td>${defaultText}</td>
      <td></td>
    `;

    const actionCell = tr.lastElementChild;
    const editBtn = document.createElement('button');
    editBtn.className = 'chunks-action-btn';
    editBtn.textContent = '编辑';
    editBtn.addEventListener('click', () => {
      fillModelForm(cfg);
    });

    const testBtn = document.createElement('button');
    testBtn.className = 'chunks-action-btn';
    testBtn.textContent = '测试';
    testBtn.addEventListener('click', () => {
      testModelConfig(cfg.id).catch((err) => showToast(err.message, false));
    });

    const defaultBtn = document.createElement('button');
    defaultBtn.className = 'chunks-action-btn';
    defaultBtn.textContent = '设默认';
    defaultBtn.disabled = Boolean(cfg.is_default);
    defaultBtn.addEventListener('click', () => {
      setDefaultModelConfig(cfg.id).catch((err) => showToast(err.message, false));
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'chunks-action-btn danger';
    deleteBtn.textContent = '删除';
    deleteBtn.addEventListener('click', () => {
      const ok = window.confirm(`确定删除模型配置 ${cfg.name} 吗？`);
      if (!ok) return;
      deleteModelConfig(cfg.id).catch((err) => showToast(err.message, false));
    });

    actionCell.style.display = 'flex';
    actionCell.style.gap = '6px';
    actionCell.style.flexWrap = 'wrap';
    actionCell.appendChild(editBtn);
    actionCell.appendChild(testBtn);
    actionCell.appendChild(defaultBtn);
    actionCell.appendChild(deleteBtn);
    tbody.appendChild(tr);
  }
}

async function refreshModelProviders() {
  const data = await apiRequest('/model/providers');
  renderProviderOptions(data.providers || []);
}

async function refreshModelConfigs() {
  const data = await apiRequest('/model/configs');
  modelConfigsList = Array.isArray(data.configs) ? data.configs : [];
  renderModelConfigsTable(modelConfigsList);
  updateChatModelSelect(modelConfigsList);
  return modelConfigsList;
}

async function submitModelConfig(event) {
  event.preventDefault();
  const idRaw = document.getElementById('model-config-id').value.trim();
  const name = document.getElementById('model-name').value.trim();
  const provider = document.getElementById('model-provider').value.trim();
  const baseUrl = document.getElementById('model-base-url').value.trim();
  const modelName = document.getElementById('model-model-name').value.trim();
  const apiKey = document.getElementById('model-api-key').value.trim();
  const temperatureRaw = document.getElementById('model-temperature').value.trim();
  const maxTokensRaw = document.getElementById('model-max-tokens').value.trim();
  const timeoutRaw = document.getElementById('model-timeout').value.trim();
  const description = document.getElementById('model-description').value.trim();
  const isActive = document.getElementById('model-is-active').checked;
  const isDefault = document.getElementById('model-is-default').checked;

  if (!name || !provider || !baseUrl || !modelName) {
    showToast('名称/Provider/Base URL/Model Name 不能为空', false);
    return;
  }

  const body = {
    name,
    provider,
    base_url: baseUrl,
    model_name: modelName,
    temperature: temperatureRaw ? Number(temperatureRaw) : 0.7,
    timeout: timeoutRaw ? Number(timeoutRaw) : 30,
    is_active: isActive,
    is_default: isDefault,
    description: description || null,
  };
  if (apiKey) body.api_key = apiKey;
  if (maxTokensRaw) body.max_tokens = Number(maxTokensRaw);

  if (idRaw) {
    await apiRequest(`/model/config/${encodeURIComponent(idRaw)}`, {
      method: 'PUT',
      body,
    });
    showToast('模型配置已更新');
  } else {
    await apiRequest('/model/config', {
      method: 'POST',
      body,
    });
    showToast('模型配置已新增');
  }

  await refreshModelConfigs();
  closeModelModal();
  resetModelForm();
}

async function deleteModelConfig(id) {
  await apiRequest(`/model/config/${encodeURIComponent(id)}`, { method: 'DELETE' });
  showToast('模型配置已删除');
  await refreshModelConfigs();
}

async function setDefaultModelConfig(id) {
  await apiRequest(`/model/config/${encodeURIComponent(id)}/default`, { method: 'POST', body: {} });
  showToast('已设置默认模型配置');
  await refreshModelConfigs();
}

async function testModelConfig(id) {
  const data = await apiRequest('/model/config/test', {
    method: 'POST',
    body: { config_id: Number(id) },
  });
  if (data.ok) {
    showToast(`测试成功：${String(data.provider || '')}`);
  } else {
    showToast(String(data.error || '测试失败'), false);
  }
}

// 检索设置管理
function saveRetrievalSettings() {
  const kInput = document.getElementById('kb-k');
  const thresholdInput = document.getElementById('kb-threshold');
  
  const k = Number(kInput.value || 2);
  const threshold = thresholdInput.value.trim();
  
  if (!Number.isFinite(k) || k < 1 || k > 20) {
    showToast('返回条数必须在 1-20 之间', false);
    return;
  }
  
  // 保存到 localStorage
  localStorage.setItem('retrieval_k', String(k));
  localStorage.setItem('retrieval_threshold', threshold);
  
  // 同步到聊天页面的隐藏字段（如果存在）
  const chatKInput = document.getElementById('chat-k');
  const chatThresholdInput = document.getElementById('chat-threshold');
  if (chatKInput) chatKInput.value = k;
  if (chatThresholdInput) chatThresholdInput.value = threshold;
  
  closeRetrievalSettingsModal();
  showToast('检索设置已保存');
}

function loadRetrievalSettings() {
  const savedK = localStorage.getItem('retrieval_k') || '2';
  const savedThreshold = localStorage.getItem('retrieval_threshold') || '';
  
  // 设置知识库管理页面的值
  const kbKInput = document.getElementById('kb-k');
  const kbThresholdInput = document.getElementById('kb-threshold');
  if (kbKInput) kbKInput.value = savedK;
  if (kbThresholdInput) kbThresholdInput.value = savedThreshold;
  
  // 同步到聊天页面的隐藏字段（如果存在）
  const chatKInput = document.getElementById('chat-k');
  const chatThresholdInput = document.getElementById('chat-threshold');
  if (chatKInput) chatKInput.value = savedK;
  if (chatThresholdInput) chatThresholdInput.value = savedThreshold;
}

async function bootstrapModelConfigs() {
  const data = await apiRequest('/model/config/bootstrap', { method: 'POST', body: {} });
  const created = Number(data.count_created || 0);
  const skipped = Number(data.count_skipped || 0);
  showToast(`初始化完成：新增${created}，跳过${skipped}`);
  await refreshModelConfigs();
}

function renderDocsTable(documents) {
  const tbody = document.getElementById('docs-tbody');
  if (!tbody) return;
  
  tbody.innerHTML = '';
  if (!Array.isArray(documents) || documents.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4">暂无文档</td></tr>';
    documentsList = [];
  } else {
    for (const doc of documents) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${String(doc.filename || '')}</td>
        <td>${Number(doc.chunk_count || 0)}</td>
        <td>${Number(doc.char_count || 0)}</td>
        <td></td>
      `;
      
      const actionCell = tr.lastElementChild;
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'chunks-action-btn danger';
      deleteBtn.textContent = '删除';
      deleteBtn.addEventListener('click', () => {
        const ok = window.confirm(`确定删除文档 ${doc.filename} 吗？`);
        if (!ok) return;
        deleteDocument(doc.filename).catch((err) => showToast(err.message, false));
      });
      
      actionCell.appendChild(deleteBtn);
      tbody.appendChild(tr);
    }
    documentsList = documents;
  }
  
  // 更新分片筛选下拉列表
  updateChunkFilenameSelect();
}

function updateChunkFilenameSelect() {
  const select = document.getElementById('chunk-filename');
  const currentValue = select.value;
  
  // 保留"全部文档"选项
  select.innerHTML = '<option value="">-- 全部文档 --</option>';
  
  // 添加文档选项
  if (Array.isArray(documentsList) && documentsList.length > 0) {
    for (const doc of documentsList) {
      const option = document.createElement('option');
      option.value = String(doc.filename || '');
      option.textContent = String(doc.filename || '');
      select.appendChild(option);
    }
    
    // 如果之前没有选择或者选择的文件不存在了，默认选择第一个文档
    if (!currentValue || !documentsList.some(d => d.filename === currentValue)) {
      select.value = String(documentsList[0].filename || '');
      // 触发自动应用筛选
      chunkState.pageIndex = 1;
      refreshChunks().catch((err) => showToast(err.message, false));
    }
  }
}

function truncateText(text, maxLen = 120) {
  const raw = String(text || '').replace(/\s+/g, ' ').trim();
  if (raw.length <= maxLen) return raw || '-';
  return `${raw.slice(0, maxLen)}...`;
}

function renderChunksTable(chunks) {
  const tbody = document.getElementById('chunks-tbody');
  tbody.innerHTML = '';
  if (!Array.isArray(chunks) || chunks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4">暂无分片</td></tr>';
    return;
  }
  for (const item of chunks) {
    const tr = document.createElement('tr');
    const idCell = document.createElement('td');
    idCell.textContent = String(item.id ?? '');
    const nameCell = document.createElement('td');
    nameCell.textContent = String(item.filename || '');
    const textCell = document.createElement('td');
    textCell.textContent = truncateText(item.text, 140);
    const actionCell = document.createElement('td');

    const editBtn = document.createElement('button');
    editBtn.className = 'chunks-action-btn';
    editBtn.textContent = '编辑';
    editBtn.addEventListener('click', () => {
      openChunkDialog(item);
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'chunks-action-btn danger';
    deleteBtn.textContent = '删除';
    deleteBtn.addEventListener('click', () => {
      const ok = window.confirm('确定删除该分片吗？');
      if (!ok) return;
      deleteChunk(item.id).catch((err) => showToast(err.message, false));
    });

    actionCell.appendChild(editBtn);
    actionCell.appendChild(deleteBtn);
    actionCell.style.display = 'flex';
    actionCell.style.gap = '8px';

    tr.appendChild(idCell);
    tr.appendChild(nameCell);
    tr.appendChild(textCell);
    tr.appendChild(actionCell);
    tbody.appendChild(tr);
  }
}

function openChunkDialog(item) {
  chunkEditState.id = item?.id ?? null;
  chunkEditState.filename = String(item?.filename || '');
  chunkDialogTitle.textContent = `编辑分片 #${chunkEditState.id}`;
  chunkDialogText.value = String(item?.text || '');
  chunkDialog.classList.add('open');
  chunkDialog.setAttribute('aria-hidden', 'false');
  chunkDialogText.focus();
}

function closeChunkDialog() {
  chunkEditState.id = null;
  chunkEditState.filename = '';
  chunkDialog.classList.remove('open');
  chunkDialog.setAttribute('aria-hidden', 'true');
  chunkDialogText.value = '';
}

async function confirmChunkDialog() {
  if (chunkEditState.id === null) {
    closeChunkDialog();
    return;
  }
  const nextText = chunkDialogText.value;
  await updateChunk(chunkEditState.id, nextText);
  closeChunkDialog();
}

function getChunkFilters() {
  const filename = document.getElementById('chunk-filename').value.trim();
  const query = document.getElementById('chunk-query').value.trim();
  const pageSizeRaw = Number(document.getElementById('chunk-page-size').value || 8);
  const pageSize = Number.isFinite(pageSizeRaw) && pageSizeRaw > 0 ? Math.floor(pageSizeRaw) : 8;
  chunkState.pageSize = pageSize;
  return { filename, query };
}

async function refreshChunks() {
  const { filename, query } = getChunkFilters();
  const params = new URLSearchParams();
  params.set('pageIndex', String(chunkState.pageIndex));
  params.set('pageSize', String(chunkState.pageSize));
  if (filename) params.set('filename', filename);
  if (query) params.set('q', query);
  const data = await apiRequest(`/kb/chunks?${params.toString()}`);
  const chunks = data.chunks || [];
  chunkState.total = Number(data.count || 0);
  renderChunksTable(chunks);

  const pageCount = Math.max(1, Math.ceil(chunkState.total / chunkState.pageSize));
  if (chunkState.pageIndex > pageCount) {
    chunkState.pageIndex = pageCount;
  }
  document.getElementById('chunk-page-info').textContent = `第 ${chunkState.pageIndex} / ${pageCount} 页`;
}

async function updateChunk(id, text) {
  await apiRequest(`/kb/chunk/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: { text },
  });
  showToast('分片已更新');
  await refreshChunks();
}

async function deleteChunk(id) {
  await apiRequest(`/kb/chunk/${encodeURIComponent(id)}`, { method: 'DELETE' });
  showToast('分片已删除');
  await refreshChunks();
  await refreshStats();
}

async function rebuildChunks() {
  const filename = document.getElementById('chunk-rebuild-filename').value.trim();
  if (!filename) {
    showToast('请输入文件名', false);
    return;
  }
  const ok = window.confirm('将按当前分片规则重建该文件的分片，是否继续？');
  if (!ok) return;
  const data = await apiRequest('/kb/chunks/rebuild', {
    method: 'POST',
    body: { filename },
  });
  showToast(`重建完成，chunks=${Number(data.chunks_added || 0)}`);
  await refreshChunks();
  await refreshDocuments();
  await refreshStats();
}

async function refreshDocuments() {
  const data = await apiRequest('/kb/documents');
  const documents = data.documents || [];
    // 保存原始数据用于筛选
    window.allDocuments = documents;
  applyDocumentFilters(documents);
function applyDocumentFilters(documents) {
  if (!Array.isArray(documents)) {
    renderDocsTable([]);
    return;
  }
  
  let filtered = [...documents];
  
  // 文件名搜索
  const searchQuery = document.getElementById('doc-search-query')?.value?.trim().toLowerCase();
  if (searchQuery) {
    filtered = filtered.filter(doc => 
      String(doc.filename || '').toLowerCase().includes(searchQuery)
    );
  }
  
  // 排序
  const sortBy = document.getElementById('doc-sort-by')?.value || 'filename';
  filtered.sort((a, b) => {
    switch (sortBy) {
      case 'filename':
        return String(a.filename || '').localeCompare(String(b.filename || ''));
      case 'chunks_desc':
        return Number(b.chunk_count || 0) - Number(a.chunk_count || 0);
      case 'chunks_asc':
        return Number(a.chunk_count || 0) - Number(b.chunk_count || 0);
      case 'chars_desc':
        return Number(b.char_count || 0) - Number(a.char_count || 0);
      case 'chars_asc':
        return Number(a.char_count || 0) - Number(b.char_count || 0);
      default:
        return 0;
    }
  });
  
  renderDocsTable(filtered);
}

}

async function refreshStats() {
  const data = await apiRequest('/stats');
  document.getElementById('stats-output').textContent = JSON.stringify(data.stats || {}, null, 2);
}

async function addDocument(event) {
  event.preventDefault();
  const filename = document.getElementById('doc-filename').value.trim();
  const text = document.getElementById('doc-text').value;
  if (!filename || !text.trim()) {
    showToast('文件名和内容都不能为空', false);
    return;
  }
  const data = await apiRequest('/kb/document', {
    method: 'POST',
    body: { filename, text },
  });
  showToast(`新增成功，chunks=${Number(data.chunks_added || 0)}`);
  event.target.reset();
  closeAddDocModal();
  await refreshDocuments();
  await refreshStats();
}

async function uploadFile(event) {
  event.preventDefault();
  const fileInput = document.getElementById('upload-file');
  const file = fileInput.files?.[0];
  if (!file) {
    showToast('请选择文件', false);
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  const filename = document.getElementById('upload-filename').value.trim();
  const encoding = document.getElementById('upload-encoding').value.trim();
  if (filename) formData.append('filename', filename);
  if (encoding) formData.append('encoding', encoding);

  const data = await apiRequest('/kb/file', { method: 'POST', body: formData });
  showToast(`上传成功，chunks=${Number(data.chunks_added || 0)}`);
  event.target.reset();
  closeUploadModal();
  await refreshDocuments();
  await refreshStats();
}

async function uploadBatchFiles(event) {
  event.preventDefault();
  const fileInput = document.getElementById('batch-files');
  const files = Array.from(fileInput.files || []);
  if (files.length === 0) {
    showToast('请选择要上传的文件', false);
    return;
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file, file.name);
  }

  const encoding = document.getElementById('batch-encoding').value.trim();
  if (encoding) formData.append('encoding', encoding);

  const data = await apiRequest('/kb/files', { method: 'POST', body: formData });
  showToast(`批量上传完成，chunks=${Number(data.chunks_added || 0)}`);
  event.target.reset();
  closeBatchUploadModal();
  await refreshDocuments();
  await refreshStats();
}

async function deleteDocument(filename) {
  if (!filename) {
    showToast('文件名不能为空', false);
    return;
  }

  const data = await apiRequest(`/kb/document/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
  showToast(`删除完成，removed=${Number(data.chunks_removed || 0)}`);
  await refreshDocuments();
  await refreshStats();
}

async function clearKnowledgeBase() {
  const ok = window.confirm('确定清空整个知识库吗？该操作不可撤销。');
  if (!ok) return;
  await apiRequest('/kb', { method: 'DELETE' });
  showToast('知识库已清空');
  await refreshDocuments();
  await refreshStats();
}

function bindEvents() {
  // 聊天页面事件
  const chatForm = document.getElementById('chat-form');
  if (chatForm) chatForm.addEventListener('submit', runChat);
  
  if (newSessionBtn) {
    newSessionBtn.addEventListener('click', () => {
      const userId = chatUserInput.value.trim();
      if (!userId) {
        chatSessionInput.value = '';
        showToast('用户ID不能为空', false);
        return;
      }
      ensureSessionId(userId)
        .then(() => {
          const messagesContainer = document.getElementById('chat-messages');
          messagesContainer.innerHTML = '<div class="chat-welcome"><p>开始提问吧！基于知识库的智能问答系统已就绪。</p></div>';
          renderKnowledgeSources([]);
        })
        .catch((err) => showToast(err.message, false));
    });
  }
  
  if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', async () => {
      if (!confirm('确定要清空所有历史记录吗？此操作不可恢复。')) {
        return;
      }
      try {
        const userId = chatUserInput.value.trim();
        if (!userId) {
          showToast('用户ID不能为空', false);
          return;
        }
        await refreshHistory();
        showToast('历史记录已清空');
      } catch (err) {
        showToast(err.message || '清空失败', false);
      }
    });
  }
  
  if (chatUserInput) {
    chatUserInput.addEventListener('change', () => {
      chatSessionInput.value = '';
    });
  }

  // 知识库管理页面事件
  const btnOpenAddDoc = document.getElementById('btn-open-add-doc');
  if (btnOpenAddDoc) {
    btnOpenAddDoc.addEventListener('click', openAddDocModal);
  }
  
  const addDocModalCloseBtn = document.getElementById('add-doc-modal-close-btn');
  if (addDocModalCloseBtn) {
    addDocModalCloseBtn.addEventListener('click', closeAddDocModal);
  }
  
  const btnCancelAddDoc = document.getElementById('btn-cancel-add-doc');
  if (btnCancelAddDoc) {
    btnCancelAddDoc.addEventListener('click', closeAddDocModal);
  }
  
  const addDocModal = document.getElementById('add-doc-modal');
  if (addDocModal) {
    addDocModal.addEventListener('click', (event) => {
      if (event.target === addDocModal) {
        closeAddDocModal();
      }
    });
  }
  
  const btnOpenUpload = document.getElementById('btn-open-upload');
  if (btnOpenUpload) {
    btnOpenUpload.addEventListener('click', openUploadModal);
  }
  
  const uploadModalCloseBtn = document.getElementById('upload-modal-close-btn');
  if (uploadModalCloseBtn) {
    uploadModalCloseBtn.addEventListener('click', closeUploadModal);
  }
  
  const btnCancelUpload = document.getElementById('btn-cancel-upload');
  if (btnCancelUpload) {
    btnCancelUpload.addEventListener('click', closeUploadModal);
  }
  
  const uploadModal = document.getElementById('upload-modal');
  if (uploadModal) {
    uploadModal.addEventListener('click', (event) => {
      if (event.target === uploadModal) {
        closeUploadModal();
      }
    });
  }
  
  const btnOpenBatchUpload = document.getElementById('btn-open-batch-upload');
  if (btnOpenBatchUpload) {
    btnOpenBatchUpload.addEventListener('click', openBatchUploadModal);
  }
  
  const batchUploadModalCloseBtn = document.getElementById('batch-upload-modal-close-btn');
  if (batchUploadModalCloseBtn) {
    batchUploadModalCloseBtn.addEventListener('click', closeBatchUploadModal);
  }
  
  const btnCancelBatchUpload = document.getElementById('btn-cancel-batch-upload');
  if (btnCancelBatchUpload) {
    btnCancelBatchUpload.addEventListener('click', closeBatchUploadModal);
  }
  
  const batchUploadModal = document.getElementById('batch-upload-modal');
  if (batchUploadModal) {
    batchUploadModal.addEventListener('click', (event) => {
      if (event.target === batchUploadModal) {
        closeBatchUploadModal();
      }
    });
  }
  
  const docForm = document.getElementById('doc-form');
  if (docForm) docForm.addEventListener('submit', (e) => addDocument(e).catch((err) => showToast(err.message, false)));
  
  const uploadForm = document.getElementById('upload-form');
  if (uploadForm) uploadForm.addEventListener('submit', (e) => uploadFile(e).catch((err) => showToast(err.message, false)));
  
  const batchUploadForm = document.getElementById('batch-upload-form');
  if (batchUploadForm) batchUploadForm.addEventListener('submit', (e) => uploadBatchFiles(e).catch((err) => showToast(err.message, false)));

  const btnRefreshDocs = document.getElementById('btn-refresh-docs');
  if (btnRefreshDocs) {
    btnRefreshDocs.addEventListener('click', async () => {
      try {
        await refreshDocuments();
        showToast('文档列表已刷新');
      } catch (err) {
        showToast(err.message, false);
      }
    });
  }

  const btnApplyDocFilter = document.getElementById('btn-apply-doc-filter');
  if (btnApplyDocFilter) {
    btnApplyDocFilter.addEventListener('click', () => {
      if (window.allDocuments) {
        applyDocumentFilters(window.allDocuments);
      }
    });
  }

  const btnClearDocFilter = document.getElementById('btn-clear-doc-filter');
  if (btnClearDocFilter) {
    btnClearDocFilter.addEventListener('click', () => {
      const searchInput = document.getElementById('doc-search-query');
      const sortSelect = document.getElementById('doc-sort-by');
      if (searchInput) searchInput.value = '';
      if (sortSelect) sortSelect.value = 'filename';
      if (window.allDocuments) {
        applyDocumentFilters(window.allDocuments);
      }
    });
  }

  const docSearchQuery = document.getElementById('doc-search-query');
  if (docSearchQuery) {
    docSearchQuery.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && window.allDocuments) {
        applyDocumentFilters(window.allDocuments);
      }
    });
  }
  
  const btnRefreshStats = document.getElementById('btn-refresh-stats');
  if (btnRefreshStats) {
    btnRefreshStats.addEventListener('click', async (event) => {
      event.stopPropagation();
      try {
        await refreshStats();
        showToast('统计信息已刷新');
      } catch (err) {
        showToast(err.message, false);
      }
    });
  }
  
  const btnClearKb = document.getElementById('btn-clear-kb');
  if (btnClearKb) {
    btnClearKb.addEventListener('click', () => {
      clearKnowledgeBase().catch((err) => showToast(err.message, false));
    });
  }
  
  const btnRefreshChunks = document.getElementById('btn-refresh-chunks');
  if (btnRefreshChunks) {
    btnRefreshChunks.addEventListener('click', async () => {
      try {
        await refreshChunks();
        showToast('分片列表已刷新');
      } catch (err) {
        showToast(err.message, false);
      }
    });
  }
  
  const chunkFilename = document.getElementById('chunk-filename');
  if (chunkFilename) {
    chunkFilename.addEventListener('change', () => {
      chunkState.pageIndex = 1;
      refreshChunks().catch((err) => showToast(err.message, false));
    });
  }
  
  const btnApplyChunkFilter = document.getElementById('btn-apply-chunk-filter');
  if (btnApplyChunkFilter) {
    btnApplyChunkFilter.addEventListener('click', () => {
      chunkState.pageIndex = 1;
      refreshChunks().catch((err) => showToast(err.message, false));
    });
  }
  
  const btnChunkPrev = document.getElementById('btn-chunk-prev');
  if (btnChunkPrev) {
    btnChunkPrev.addEventListener('click', () => {
      if (chunkState.pageIndex > 1) {
        chunkState.pageIndex -= 1;
        refreshChunks().catch((err) => showToast(err.message, false));
      }
    });
  }
  
  const btnChunkNext = document.getElementById('btn-chunk-next');
  if (btnChunkNext) {
    btnChunkNext.addEventListener('click', () => {
      const pageCount = Math.max(1, Math.ceil(chunkState.total / chunkState.pageSize));
      if (chunkState.pageIndex < pageCount) {
        chunkState.pageIndex += 1;
        refreshChunks().catch((err) => showToast(err.message, false));
      }
    });
  }
  
  const btnRebuildChunks = document.getElementById('btn-rebuild-chunks');
  if (btnRebuildChunks) {
    btnRebuildChunks.addEventListener('click', () => {
      rebuildChunks().catch((err) => showToast(err.message, false));
    });
  }
  
  const btnSaveRetrievalSettings = document.getElementById('btn-save-retrieval-settings');
  if (btnSaveRetrievalSettings) {
    btnSaveRetrievalSettings.addEventListener('click', () => {
      saveRetrievalSettings();
    });
  }
  
  const btnOpenRetrievalSettings = document.getElementById('btn-open-retrieval-settings');
  if (btnOpenRetrievalSettings) {
    btnOpenRetrievalSettings.addEventListener('click', openRetrievalSettingsModal);
  }
  
  const retrievalModalCloseBtn = document.getElementById('retrieval-modal-close-btn');
  if (retrievalModalCloseBtn) {
    retrievalModalCloseBtn.addEventListener('click', closeRetrievalSettingsModal);
  }
  
  const btnCancelRetrievalModal = document.getElementById('btn-cancel-retrieval-modal');
  if (btnCancelRetrievalModal) {
    btnCancelRetrievalModal.addEventListener('click', closeRetrievalSettingsModal);
  }
  
  const retrievalSettingsModal = document.getElementById('retrieval-settings-modal');
  if (retrievalSettingsModal) {
    retrievalSettingsModal.addEventListener('click', (event) => {
      if (event.target === retrievalSettingsModal) {
        closeRetrievalSettingsModal();
      }
    });
  }

  // 模型管理页面事件
  const modelConfigForm = document.getElementById('model-config-form');
  if (modelConfigForm) {
    modelConfigForm.addEventListener('submit', (e) => {
      submitModelConfig(e).catch((err) => showToast(err.message, false));
    });
  }
  
  const btnAddModel = document.getElementById('btn-add-model');
  if (btnAddModel) {
    btnAddModel.addEventListener('click', () => {
      resetModelForm();
      openModelModal(false);
    });
  }
  
  const modalCloseBtn = document.getElementById('modal-close-btn');
  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeModelModal);
  }
  
  const btnCancelModal = document.getElementById('btn-cancel-modal');
  if (btnCancelModal) {
    btnCancelModal.addEventListener('click', closeModelModal);
  }
  
  const modelConfigModal = document.getElementById('model-config-modal');
  if (modelConfigModal) {
    modelConfigModal.addEventListener('click', (event) => {
      if (event.target === modelConfigModal) {
        closeModelModal();
      }
    });
  }
  
  const btnRefreshModelConfigs = document.getElementById('btn-refresh-model-configs');
  if (btnRefreshModelConfigs) {
    btnRefreshModelConfigs.addEventListener('click', () => {
      refreshModelConfigs().catch((err) => showToast(err.message, false));
    });
  }
  
  const btnBootstrapModelConfigs = document.getElementById('btn-bootstrap-model-configs');
  if (btnBootstrapModelConfigs) {
    btnBootstrapModelConfigs.addEventListener('click', () => {
      bootstrapModelConfigs().catch((err) => showToast(err.message, false));
    });
  }

  // 分片对话框事件
  if (chunkDialogClose) chunkDialogClose.addEventListener('click', closeChunkDialog);
  if (chunkDialogCancel) chunkDialogCancel.addEventListener('click', closeChunkDialog);
  if (chunkDialogSave) {
    chunkDialogSave.addEventListener('click', () => {
      confirmChunkDialog().catch((err) => showToast(err.message, false));
    });
  }
  if (chunkDialog) {
    chunkDialog.addEventListener('click', (event) => {
      if (event.target === chunkDialog) {
        closeChunkDialog();
      }
    });
  }
  
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && chunkDialog && chunkDialog.classList.contains('open')) {
      closeChunkDialog();
    }
  });
}

async function bootstrap() {
  bindEvents();
  
  // 聊天页面初始化
  const chatInput = document.getElementById('chat-query');
  if (chatInput) {
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    });
    
    // 支持 Shift+Enter 换行，Enter 发送
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const form = document.getElementById('chat-form');
        if (form && chatInput.value.trim()) {
          form.requestSubmit();
        }
      }
    });
  }
  
  try {
    // 初始化各页面数据
    const initTasks = [];
    
    // 聊天页面
    if (document.getElementById('chat-messages')) {
      renderKnowledgeSources([]);
      loadRetrievalSettings();
      if (chatUserInput && chatUserInput.value.trim() && chatSessionInput && !chatSessionInput.value.trim()) {
        initTasks.push(ensureSessionId(chatUserInput.value.trim()));
      }
      initTasks.push(refreshHistory().catch(() => {}));
    }
    
    // 知识库管理页面
    if (document.getElementById('docs-table')) {
      loadRetrievalSettings();
      initTasks.push(refreshDocuments().catch(() => {}));
      initTasks.push(refreshChunks().catch(() => {}));
      
      // 统计信息折叠/展开功能
      const statsHeader = document.getElementById('stats-header');
      const statsContent = document.getElementById('stats-content');
      const statsToggleIcon = document.getElementById('stats-toggle-icon');
      if (statsHeader && statsContent && statsToggleIcon) {
        statsHeader.addEventListener('click', () => {
          const isHidden = statsContent.style.display === 'none';
          statsContent.style.display = isHidden ? 'block' : 'none';
          statsToggleIcon.textContent = isHidden ? '▲' : '▼';
        });
      }
    }
    
    // 模型管理页面
    if (document.getElementById('model-configs-table')) {
      initTasks.push(refreshModelProviders().catch(() => {}));
      initTasks.push(refreshModelConfigs().catch(() => {}));
      const resetBtn = document.getElementById('btn-reset-model-form');
      if (resetBtn) resetModelForm();
    }
    
    await Promise.all(initTasks);
  } catch (error) {
    console.error('初始化错误:', error);
    showToast(error.message || '初始化失败', false);
  }
}

bootstrap();