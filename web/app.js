const menuItems = Array.from(document.querySelectorAll('.menu-item'));
const panels = {
  chat: document.getElementById('panel-chat'),
  kb: document.getElementById('panel-kb'),
};
const toast = document.getElementById('toast');
const chunkState = {
  pageIndex: 1,
  pageSize: 8,
  total: 0,
};
let documentsList = [];
const chatUserInput = document.getElementById('chat-user-id');
const chatSessionInput = document.getElementById('chat-session-id');
const resetSessionBtn = document.getElementById('btn-reset-session');
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

function showToast(message, ok = true) {
  toast.textContent = message;
  toast.className = `toast show ${ok ? 'ok' : 'err'}`;
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => {
    toast.className = 'toast';
  }, 3200);
}

function switchTab(tab) {
  for (const item of menuItems) {
    item.classList.toggle('active', item.dataset.tab === tab);
  }
  Object.entries(panels).forEach(([name, panel]) => {
    panel.classList.toggle('active', name === tab);
  });
}

menuItems.forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

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
  
  showToast(`已加载会话（${items.length}条对话）`);
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
  
  showToast('已加载历史对话');
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
  for (const session of history) {
    const li = document.createElement('li');
    li.className = 'history-item';
    
    // 添加点击事件，显示整个session的对话
    li.addEventListener('click', (e) => {
      // 如果点击的是删除按钮，不触发查看功能
      if (e.target.classList.contains('history-delete')) {
        return;
      }
      loadSessionToChat(session);
    });
    
    const head = document.createElement('div');
    head.className = 'history-row';
    const title = document.createElement('div');
    title.className = 'history-title';
    // 显示第一个问题作为标题
    const firstQuery = session.first_query || pickHistoryTitle(session.items?.[0] || {});
    const displayTitle = String(firstQuery).slice(0, 40);
    title.textContent = displayTitle + (session.count > 1 ? ` (共${session.count}条)` : '');
    head.appendChild(title);

    // 删除按钮 - 删除整个session的所有记录
    if (session.session_id) {
      const delBtn = document.createElement('button');
      delBtn.className = 'history-delete';
      delBtn.type = 'button';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', async (e) => {
        e.stopPropagation(); // 阻止事件冒泡
        const ok = window.confirm(`确定删除该会话的所有${session.count}条记录吗？`);
        if (!ok) return;
        try {
          // 使用新的 DELETE /session/{session_id} API
          await apiRequest(`/session/${encodeURIComponent(session.session_id)}`, { method: 'DELETE' });
          showToast('会话记录已删除');
          await refreshHistory();
        } catch (err) {
          showToast(err.message || '删除失败', false);
        }
      });
      head.appendChild(delBtn);
    }
    const meta = document.createElement('div');
    meta.className = 'history-meta';
    meta.textContent = `${formatHistoryTime(session?.timestamp)} · ${session?.user_id || 'unknown'}`;
    li.appendChild(head);
    li.appendChild(meta);
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
  const generateAnswer = document.getElementById('chat-generate').checked;
  const deepThink = document.getElementById('chat-deep-think').checked;
  
  // 添加用户消息到聊天框
  addUserMessage(query);
  
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
    body.relevance_threshold = threshold;
  }

  try {
    await runChatStream(body);
    refreshHistory().catch(() => {});
    showToast('查询完成');
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
      addReferencesToMessage(payload.results || []);
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

function renderDocsTable(documents) {
  const tbody = document.getElementById('docs-tbody');
  tbody.innerHTML = '';
  if (!Array.isArray(documents) || documents.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3">暂无文档</td></tr>';
    documentsList = [];
  } else {
    for (const doc of documents) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${String(doc.filename || '')}</td><td>${Number(doc.chunk_count || 0)}</td><td>${Number(doc.char_count || 0)}</td>`;
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
  renderDocsTable(data.documents || []);
  showToast(`已加载 ${Number(data.count || 0)} 个文档`);
}

async function refreshStats() {
  const data = await apiRequest('/stats');
  document.getElementById('stats-output').textContent = JSON.stringify(data.stats || {}, null, 2);
  showToast('统计已刷新');
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
  await refreshDocuments();
  await refreshStats();
}

async function deleteDocument(event) {
  event.preventDefault();
  const filename = document.getElementById('delete-filename').value.trim();
  if (!filename) {
    showToast('文件名不能为空', false);
    return;
  }

  const data = await apiRequest(`/kb/document/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  });
  showToast(`删除完成，removed=${Number(data.chunks_removed || 0)}`);
  event.target.reset();
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
  document.getElementById('chat-form').addEventListener('submit', runChat);
  document.getElementById('doc-form').addEventListener('submit', (e) => addDocument(e).catch((err) => showToast(err.message, false)));
  document.getElementById('upload-form').addEventListener('submit', (e) => uploadFile(e).catch((err) => showToast(err.message, false)));
  document.getElementById('batch-upload-form').addEventListener('submit', (e) => uploadBatchFiles(e).catch((err) => showToast(err.message, false)));
  document.getElementById('delete-form').addEventListener('submit', (e) => deleteDocument(e).catch((err) => showToast(err.message, false)));

  document.getElementById('btn-refresh-docs').addEventListener('click', () => {
    refreshDocuments().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-refresh-stats').addEventListener('click', () => {
    refreshStats().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-clear-kb').addEventListener('click', () => {
    clearKnowledgeBase().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-refresh-history').addEventListener('click', () => {
    refreshHistory().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-refresh-chunks').addEventListener('click', () => {
    refreshChunks().catch((err) => showToast(err.message, false));
  });
  document.getElementById('chunk-filename').addEventListener('change', () => {
    chunkState.pageIndex = 1;
    refreshChunks().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-apply-chunk-filter').addEventListener('click', () => {
    chunkState.pageIndex = 1;
    refreshChunks().catch((err) => showToast(err.message, false));
  });
  document.getElementById('btn-chunk-prev').addEventListener('click', () => {
    if (chunkState.pageIndex > 1) {
      chunkState.pageIndex -= 1;
      refreshChunks().catch((err) => showToast(err.message, false));
    }
  });
  document.getElementById('btn-chunk-next').addEventListener('click', () => {
    const pageCount = Math.max(1, Math.ceil(chunkState.total / chunkState.pageSize));
    if (chunkState.pageIndex < pageCount) {
      chunkState.pageIndex += 1;
      refreshChunks().catch((err) => showToast(err.message, false));
    }
  });
  document.getElementById('btn-rebuild-chunks').addEventListener('click', () => {
    rebuildChunks().catch((err) => showToast(err.message, false));
  });

  resetSessionBtn.addEventListener('click', () => {
    const userId = chatUserInput.value.trim();
    if (!userId) {
      chatSessionInput.value = '';
      showToast('用户ID不能为空', false);
      return;
    }
    ensureSessionId(userId)
      .then(() => {
        // 清空聊天消息内容
        const messagesContainer = document.getElementById('chat-messages');
        messagesContainer.innerHTML = '<div class="chat-welcome"><p>开始提问吧！基于知识库的智能问答系统已就绪。</p></div>';
        showToast('已创建新会话');
      })
      .catch((err) => showToast(err.message, false));
  });
  chatUserInput.addEventListener('change', () => {
    chatSessionInput.value = '';
  });

  chunkDialogClose.addEventListener('click', closeChunkDialog);
  chunkDialogCancel.addEventListener('click', closeChunkDialog);
  chunkDialogSave.addEventListener('click', () => {
    confirmChunkDialog().catch((err) => showToast(err.message, false));
  });
  chunkDialog.addEventListener('click', (event) => {
    if (event.target === chunkDialog) {
      closeChunkDialog();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && chunkDialog.classList.contains('open')) {
      closeChunkDialog();
    }
  });
}

async function bootstrap() {
  bindEvents();
  switchTab('chat');
  
  // 输入框自动调整高度
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
    const userId = chatUserInput.value.trim();
    if (userId && !chatSessionInput.value.trim()) {
      await ensureSessionId(userId);
    }
    await Promise.all([refreshDocuments(), refreshStats(), refreshHistory(), refreshChunks()]);
  } catch (error) {
    showToast(error.message || '初始化失败', false);
  }
}

bootstrap();
