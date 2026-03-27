const menuItems = Array.from(document.querySelectorAll('.menu-item'));
const toast = document.getElementById('toast');
const chunkState = {
  pageIndex: 1,
  pageSize: 8,
  total: 0,
};
let documentsList = [];
let modelConfigsList = [];
let historyRefreshTimer = null;
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
const sourceDialog = document.getElementById('source-dialog');
const sourceDialogTitle = document.getElementById('source-dialog-title');
const sourceDialogSubtitle = document.getElementById('source-dialog-subtitle');
const sourceDialogContent = document.getElementById('source-dialog-content');
const sourceDialogCloseBtn = document.getElementById('source-dialog-close');
const sourceDialogCancelBtn = document.getElementById('source-dialog-cancel');
const chunkEditState = {
  id: null,
  filename: '',
};
const chunkManagerState = {
  selectedFilename: '',
};

function openSourceDialog(item, index = 0) {
  if (!sourceDialog || !sourceDialogTitle || !sourceDialogContent) return;

  const filename = String(item?.filename || '未知文件');
  const sim = item?.similarity != null ? Number(item.similarity) : null;
  const scoreLabel = sim == null || Number.isNaN(sim) ? '' : ` | 相似度 ${(sim * 100).toFixed(1)}%`;
  const fullText = String(item?.text || item?.chunk || item?.content || item?.preview_text || '').trim() || '（无内容）';

  sourceDialogTitle.textContent = `知识来源 #${Number(index) + 1}`;
  if (sourceDialogSubtitle) {
    sourceDialogSubtitle.textContent = `${filename}${scoreLabel}`;
  }
  sourceDialogContent.textContent = fullText;
  sourceDialog.classList.add('open');
  sourceDialog.setAttribute('aria-hidden', 'false');
}

function closeSourceDialog() {
  if (!sourceDialog || !sourceDialogContent) return;
  sourceDialog.classList.remove('open');
  sourceDialog.setAttribute('aria-hidden', 'true');
  sourceDialogContent.textContent = '';
}

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
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `查看来源 ${idx + 1} 详情`);

    const header = document.createElement('div');
    header.className = 'source-header';

    const name = document.createElement('div');
    name.className = 'source-name';
    name.textContent = `${idx + 1}. ${String(item.filename || '未知文件')}`;

    const score = document.createElement('div');
    score.className = 'source-score';
    const sim = item.similarity != null ? Number(item.similarity) : null;
    score.textContent = sim == null || Number.isNaN(sim) ? '-' : `${(sim * 100).toFixed(1)}%`;

    const text = document.createElement('div');
    text.className = 'source-text';
    text.textContent = String(
      item.preview_text || item.text || item.chunk || item.content || ''
    ).slice(0, 180) || '（无内容预览）';

    header.appendChild(name);
    header.appendChild(score);
    card.appendChild(header);
    card.appendChild(text);
    card.addEventListener('click', () => openSourceDialog(item, idx));
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openSourceDialog(item, idx);
      }
    });
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

let kbLoadingCount = 0;

function ensureKbLoadingOverlay() {
  let overlay = document.getElementById('kb-loading-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.id = 'kb-loading-overlay';
  overlay.className = 'kb-loading-overlay';
  overlay.innerHTML = `
    <div class="kb-loading-dialog" role="status" aria-live="polite" aria-busy="true">
      <div class="kb-loading-spinner"></div>
      <div class="kb-loading-text">处理中，请稍候...</div>
    </div>
  `;
  document.body.appendChild(overlay);
  return overlay;
}

function setKbLoadingVisible(visible, message = '处理中，请稍候...') {
  const overlay = ensureKbLoadingOverlay();
  const textEl = overlay.querySelector('.kb-loading-text');
  if (textEl) textEl.textContent = String(message || '处理中，请稍候...');
  overlay.classList.toggle('show', Boolean(visible));
  document.body.classList.toggle('kb-loading-active', Boolean(visible));
}

function showKbLoading(message = '处理中，请稍候...') {
  if (!document.getElementById('docs-table')) return;
  kbLoadingCount += 1;
  setKbLoadingVisible(true, message);
}

function hideKbLoading() {
  if (!document.getElementById('docs-table')) return;
  kbLoadingCount = Math.max(0, kbLoadingCount - 1);
  if (kbLoadingCount === 0) {
    setKbLoadingVisible(false);
  }
}

async function withKbLoading(message, runner) {
  showKbLoading(message);
  try {
    return await runner();
  } finally {
    hideKbLoading();
  }
}

async function copyTextToClipboard(text) {
  const plain = String(text || '');
  if (!plain.trim()) return false;

  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(plain);
      return true;
    }
  } catch (error) {
    // Fall back to legacy copy approach below.
  }

  try {
    const textarea = document.createElement('textarea');
    textarea.value = plain;
    textarea.setAttribute('readonly', 'readonly');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    return Boolean(ok);
  } catch (error) {
    return false;
  }
}

function extractAssistantAnswerText(aiBubble) {
  if (!aiBubble) return '';
  const answerHost = aiBubble.querySelector('.message-bubble-answer');
  if (answerHost) {
    return answerHost.innerText || answerHost.textContent || '';
  }
  return aiBubble.innerText || aiBubble.textContent || '';
}

function createMessageCopyButton(targetOrGetter, title = '复制内容') {
  const copyBtn = document.createElement('button');
  copyBtn.className = 'action-btn copy-btn';
  const copyIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  const okIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';

  copyBtn.innerHTML = copyIcon;
  copyBtn.title = title;
  copyBtn.addEventListener('click', async () => {
    const text = typeof targetOrGetter === 'function'
      ? String(targetOrGetter() || '')
      : (targetOrGetter?.innerText || targetOrGetter?.textContent || '');
    if (!text.trim()) return;
    const ok = await copyTextToClipboard(text);
    if (ok) {
      copyBtn.innerHTML = okIcon;
      setTimeout(() => {
        copyBtn.innerHTML = copyIcon;
      }, 1500);
    }
  });
  return copyBtn;
}

function appendUserCopyAction(content, userBubble) {
  if (!content || !userBubble) return;
  const actionsBar = document.createElement('div');
  actionsBar.className = 'message-actions';
  actionsBar.appendChild(createMessageCopyButton(userBubble, '复制问题'));
  content.appendChild(actionsBar);
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
    const msg = data?.error || payload?.error || `请求失败（${wrappedCode}）`;
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
  
  const copyBtn = createMessageCopyButton(() => {
    const bubble = lastMessage.querySelector('.message-bubble');
    return extractAssistantAnswerText(bubble);
  }, '复制回答');
  
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
    fileName.textContent = String(item.filename || '未知文件');
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
  appendUserCopyAction(content, bubble);
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
  content.appendChild(bubble);
  if (isLoading) {
    setAssistantBubbleAnswer(content, '');
  } else {
    setAssistantBubbleAnswer(content, text);
  }
  
  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  
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
  const content = lastMessage.querySelector('.message-content');
  setAssistantBubbleAnswer(content, text);
  
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

function sanitizeThinkingDisplayText(text) {
  let cleaned = String(text || '');
  if (!cleaned) return '';
  cleaned = cleaned
    .replace(/<\/?think>/gi, '')
    .replace(/<\/?thinking_summary>/gi, '')
    .replace(/```/g, '');
  cleaned = cleaned.replace(
    /^\s*(?:tags?,?\s*final\s*answer\s*after\s*thinking|summary\s+in|wait,?\s+looking\s+at\s+the\s+instruction|let'?s\s+check\s+the\s+instruction|actually,\s+looking\s+at\s+similar\s+tasks|wait,?\s+is\s+there\s+a\s+risk\s+of\s+confusion|also,\s+the\s+summary\s+tag\s+is|this\s+should\s+be\s+inside\s+the\s+thinking\s+block).*$/gim,
    ''
  );
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  return cleaned.trim();
}

function findAssistantBubble(container) {
  return container ? container.querySelector('.message-bubble') : null;
}

function ensureAssistantBubbleSections(container) {
  const bubble = findAssistantBubble(container);
  if (!bubble) {
    return { bubble: null, thoughtsHost: null, answerHost: null };
  }

  let thoughtsHost = bubble.querySelector('.message-bubble-thoughts');
  let answerHost = bubble.querySelector('.message-bubble-answer');
  if (!thoughtsHost || !answerHost) {
    const existingNodes = Array.from(bubble.childNodes);
    bubble.innerHTML = '';

    thoughtsHost = document.createElement('div');
    thoughtsHost.className = 'message-bubble-thoughts';

    answerHost = document.createElement('div');
    answerHost.className = 'message-bubble-answer';

    bubble.appendChild(thoughtsHost);
    bubble.appendChild(answerHost);

    if (existingNodes.length > 0) {
      answerHost.replaceChildren(...existingNodes);
    }
  }

  return { bubble, thoughtsHost, answerHost };
}

function setAssistantBubbleAnswer(container, text) {
  const { bubble, thoughtsHost, answerHost } = ensureAssistantBubbleSections(container);
  if (!bubble || !answerHost) return;

  const content = String(text || '');
  const isLoading = !content.trim();
  const hasThinkingPanel = Boolean(thoughtsHost && thoughtsHost.textContent && thoughtsHost.textContent.trim());
  if (isLoading) {
    answerHost.innerHTML = hasThinkingPanel
      ? ''
      : '<span class="loading-dots" aria-live="polite">正在思考</span>';
  } else {
    answerHost.innerHTML = renderMessageContent(content);
  }
  bubble.classList.toggle('loading', isLoading);
}

function splitMixedAnswerAndThinking(answerText, thinkingText) {
  let answer = String(answerText || '').trim();
  let thinking = String(thinkingText || '').trim();

  if (!answer) {
    return { answer: '', thinking };
  }

  const thinkBlock = answer.match(/<think>([\s\S]*?)<\/think>/i);
  if (thinkBlock) {
    const block = String(thinkBlock[1] || '').trim();
    if (block) {
      thinking = thinking ? `${thinking}\n\n${block}` : block;
    }
    answer = answer.replace(/<think>[\s\S]*?<\/think>/ig, '').trim();
  }

  const headingMatch = answer.match(/(?:^|\n)\s*(thinking process|思考过程|reasoning|analysis)\s*[:：]/i);
  if (headingMatch) {
    const finalMatch = answer.match(/(?:^|\n)\s*(final answer|最终答案|答案)\s*[:：]/i);
    if (finalMatch && finalMatch.index != null && headingMatch.index != null && finalMatch.index > headingMatch.index) {
      const thinkingPart = answer.slice(headingMatch.index, finalMatch.index).trim();
      const answerPart = answer.slice(finalMatch.index).trim();
      if (thinkingPart) {
        thinking = thinking ? `${thinking}\n\n${thinkingPart}` : thinkingPart;
      }
      answer = answerPart;
    } else if (!thinking) {
      thinking = answer;
      answer = '';
    }
  }

  const planningCueRegex = /(?:provide a summary at the end of thinking|thinking summary at the end of thought process|thinking process|goal\s*:|scan knowledge base|synthesize the information|synthesize\s*the\s*answer|draft the response|refine based on constraints|analyze the request|analyze the knowledge base context|question\s*:|intent\s*:|task\s*:|output\s*format\s*:|document\s*\[[0-9]+\]\s*:)/i;
  const compact = answer.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '');
  const compactPlanningTokens = [
    'analyzetheuserquestion',
    'analyzetheknowledgebasecontext',
    'synthesizetheanswer',
    'drafttheresponse',
    'refinebasedonconstraints',
    'thinkingsummaryattheendofthoughtprocess',
    'contentrelatedtoprojects',
    'projectrelatedsections',
  ];
  const hasCompactPlanningToken = compactPlanningTokens.some((token) => compact.includes(token));
  const finalStartRegexList = [
    /根据提供的知识库上下文/,
    /根据(?:提供|以上|上述).{0,30}(?:上下文|内容|文档)/,
    /与.{0,30}相关的内容主要包含以下/,
    /主要包含以下几个方面/,
    /结合(?:提供|上述).{0,20}(?:文档|内容)/,
    /可归纳为以下(?:几点|方面)/,
  ];
  let finalStartIndex = -1;
  for (const regex of finalStartRegexList) {
    const m = answer.match(regex);
    if (m && m.index != null && (finalStartIndex < 0 || m.index < finalStartIndex)) {
      finalStartIndex = m.index;
    }
  }
  if (finalStartIndex > 0) {
    const prefix = answer.slice(0, finalStartIndex).trim();
    if (prefix && (planningCueRegex.test(prefix) || hasCompactPlanningToken)) {
      thinking = thinking ? `${thinking}\n\n${prefix}` : prefix;
      answer = answer.slice(finalStartIndex).trim();
    }
  }

  const leadingLeakRegex = /^\s*(?:\)\.\s*)?(?:provide a summary at the end of thinking|thinking summary at the end of thought process|thinking process\s*:|\*\s*goal\s*:|scan knowledge base(?:\s*for)?|synthesize the information|synthesizetheanswer\s*:|analyzetheuserquestion\s*:|analyzetheknowledgebasecontext\s*:|draft the response|refine based on constraints|analyze the request|question\s*:|intent\s*:|task\s*:|output\s*format\s*:|document\s*\[[0-9]+\]\s*:)\s*[^\n]*(?:\n|$)/i;
  while (leadingLeakRegex.test(answer)) {
    const matched = answer.match(leadingLeakRegex);
    if (!matched) break;
    const chunk = String(matched[0] || '').trim();
    if (chunk) {
      thinking = thinking ? `${thinking}\n${chunk}` : chunk;
    }
    answer = answer.slice(matched[0].length).trim();
  }

  if ((planningCueRegex.test(answer) || hasCompactPlanningToken) && !/根据|主要包含|可归纳|项目介绍|项目风险|假设与限制/.test(answer)) {
    thinking = thinking ? `${thinking}\n\n${answer}` : answer;
    answer = '';
  }

  answer = answer.replace(/^(?:final\s*answer|最终答案|答案)\s*[:：\-]*\s*/i, '').trim();
  return { answer, thinking };
}

function appendThinkingSummary(container, summary) {
  if (!container || !summary) return;
  const { thoughtsHost } = ensureAssistantBubbleSections(container);
  if (!thoughtsHost) return;

  const existing = thoughtsHost.querySelector('.message-thinking');
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
  thoughtsHost.prepend(wrap);
}

function upsertThinkingContent(container, thinking, collapsed = false) {
  if (!container) return;
  const text = sanitizeThinkingDisplayText(thinking);
  const { thoughtsHost } = ensureAssistantBubbleSections(container);
  if (!thoughtsHost) return;

  const existing = thoughtsHost.querySelector('.message-thinking-panel');
  if (!text) {
    if (existing) existing.remove();
    return;
  }

  let panel = existing;
  let summaryEl;
  let bodyEl;
  if (!panel) {
    panel = document.createElement('details');
    panel.className = 'message-thinking-panel';
    summaryEl = document.createElement('summary');
    summaryEl.className = 'thinking-panel-summary';
    summaryEl.textContent = '思考过程';
    bodyEl = document.createElement('div');
    bodyEl.className = 'thinking-panel-body';
    panel.appendChild(summaryEl);
    panel.appendChild(bodyEl);
    thoughtsHost.appendChild(panel);
  } else {
    summaryEl = panel.querySelector('.thinking-panel-summary');
    bodyEl = panel.querySelector('.thinking-panel-body');
  }
  bodyEl.innerHTML = renderMessageContent(text);
  panel.open = !collapsed;
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

function updateLastAssistantThinking(thinking, collapsed = false) {
  const messagesContainer = document.getElementById('chat-messages');
  const messages = messagesContainer.querySelectorAll('.chat-message.assistant');
  if (messages.length === 0) return;
  const lastMessage = messages[messages.length - 1];
  const content = lastMessage.querySelector('.message-content');
  upsertThinkingContent(content, thinking, collapsed);
}

function renderAssistantThoughtBlocks(container, thinkingSummary, thinking, collapsed = true) {
  if (thinkingSummary) {
    appendThinkingSummary(container, thinkingSummary);
  }
  if (thinking) {
    upsertThinkingContent(container, thinking, collapsed);
  }
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
    const thinking = response.thinking || '';
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
    
    const aiTime = document.createElement('div');
    aiTime.className = 'message-time';
    aiTime.textContent = formatHistoryTime(historyItem?.timestamp);
    
    aiContent.appendChild(aiBubble);
    setAssistantBubbleAnswer(aiContent, answer);
    renderAssistantThoughtBlocks(aiContent, thinkingSummary, thinking, true);
    aiContent.appendChild(aiTime);
    
    // 添加操作栏（复制按钮和引用文档）
    if (results.length > 0) {
      const actionsBar = createActionsBar(aiBubble, results);
      aiContent.appendChild(actionsBar);
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
  
  const copyBtn = createMessageCopyButton(() => extractAssistantAnswerText(aiBubble), '复制回答');
  
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
    fileName.textContent = String(item.filename || '未知文件');
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
    appendUserCopyAction(userContent, userBubble);
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
  const thinking = response.thinking || '';
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
  appendUserCopyAction(userContent, userBubble);
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
  
  const aiTime = document.createElement('div');
  aiTime.className = 'message-time';
  aiTime.textContent = formatHistoryTime(historyItem?.timestamp);
  
  aiContent.appendChild(aiBubble);
  setAssistantBubbleAnswer(aiContent, answer);
  renderAssistantThoughtBlocks(aiContent, thinkingSummary, thinking, true);
  aiContent.appendChild(aiTime);
  
  // 添加操作栏（复制按钮和引用文档）
  if (results.length > 0) {
    aiContent.appendChild(createActionsBar(aiBubble, results));
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

function scheduleAutoRefreshHistory(delay = 250) {
  if (historyRefreshTimer) {
    window.clearTimeout(historyRefreshTimer);
  }
  historyRefreshTimer = window.setTimeout(() => {
    refreshHistory().catch(() => {});
    historyRefreshTimer = null;
  }, Math.max(0, Number(delay) || 0));
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
    throw new Error(text || `请求失败（${resp.status}）`);
  }

  let answer = '';
  let thinking = '';
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
      const split = splitMixedAnswerAndThinking(answer, thinking);
      answer = split.answer;
      thinking = split.thinking;
      updateLastAssistantMessage(answer);
      if (thinking) {
        updateLastAssistantThinking(thinking, false);
      }
      return;
    }
    if (eventType === 'thinking_delta') {
      const delta = String(payload.delta || '');
      if (!delta) return;
      thinking += delta;
      updateLastAssistantThinking(thinking, false);
      setAssistantBubbleAnswer(
        document.querySelector('#chat-messages .chat-message.assistant:last-child .message-content'),
        ''
      );
      return;
    }
    if (eventType === 'done') {
      const finalAnswer = String(payload.answer || '').trim();
      if (finalAnswer) {
        answer = finalAnswer;
      }
      const summary = String(payload.thinking_summary || '').trim();
      const finalThinking = String(payload.thinking || '').trim() || thinking;
      const split = splitMixedAnswerAndThinking(answer, finalThinking);
      answer = split.answer;
      thinking = split.thinking;

      updateLastAssistantMessage(answer);
      if (thinking) {
        updateLastAssistantThinking(thinking, true);
      }
      if (summary) {
        addThinkingSummaryToLastAssistant(summary);
      }
      scheduleAutoRefreshHistory(120);
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

  // Fallback refresh in case stream closes without explicit done event.
  if (thinking) {
    updateLastAssistantThinking(thinking, true);
  }
  scheduleAutoRefreshHistory(200);
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

function openStatsModal() {
  const modal = document.getElementById('stats-modal');
  if (!modal) return;
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  refreshStats().catch((err) => showToast(err.message || '统计信息加载失败', false));
}

function closeStatsModal() {
  const modal = document.getElementById('stats-modal');
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

function openChunkManagerModal(filename = '') {
  const modal = document.getElementById('chunk-manager-modal');
  if (!modal) return;
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  chunkManagerState.selectedFilename = String(filename || '').trim();
  const selectedInput = document.getElementById('chunk-selected-filename');
  if (selectedInput) selectedInput.value = chunkManagerState.selectedFilename;

  const queryInput = document.getElementById('chunk-query');
  if (queryInput) queryInput.value = '';
  chunkState.pageIndex = 1;
  refreshChunks().catch((err) => showToast(err.message, false));
}

function closeChunkManagerModal() {
  const modal = document.getElementById('chunk-manager-modal');
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
    providerSelect.innerHTML = '<option value="">-- 无可用服务商 --</option>';
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
  select.innerHTML = '<option value="">-- 使用默认模型配置 --</option>';
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

    const actionsWrap = document.createElement('div');
    actionsWrap.className = 'table-actions-wrap';
    actionsWrap.appendChild(editBtn);
    actionsWrap.appendChild(testBtn);
    actionsWrap.appendChild(defaultBtn);
    actionsWrap.appendChild(deleteBtn);
    actionCell.appendChild(actionsWrap);
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
    showToast('名称、服务商、接口地址、模型名称不能为空', false);
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
      const chunkManageBtn = document.createElement('button');
      chunkManageBtn.className = 'chunks-action-btn';
      chunkManageBtn.textContent = '分片管理';
      chunkManageBtn.addEventListener('click', () => {
        const filename = String(doc.filename || '').trim();
        if (!filename) {
          showToast('文件名无效', false);
          return;
        }
        openChunkManagerModal(filename);
      });

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'chunks-action-btn danger';
      deleteBtn.textContent = '删除';
      deleteBtn.addEventListener('click', () => {
        const ok = window.confirm(`确定删除文档 ${doc.filename} 吗？`);
        if (!ok) return;
        deleteDocument(doc.filename).catch((err) => showToast(err.message, false));
      });

      actionCell.style.display = 'flex';
      actionCell.style.gap = '8px';
      actionCell.style.flexWrap = 'wrap';
      actionCell.appendChild(chunkManageBtn);
      actionCell.appendChild(deleteBtn);
      tbody.appendChild(tr);
    }
    documentsList = documents;
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

    const actionsWrap = document.createElement('div');
    actionsWrap.className = 'table-actions-wrap';
    actionsWrap.appendChild(editBtn);
    actionsWrap.appendChild(deleteBtn);
    actionCell.appendChild(actionsWrap);

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
  const filename = String(chunkManagerState.selectedFilename || '').trim();
  const query = document.getElementById('chunk-query').value.trim();
  const pageSizeRaw = Number(document.getElementById('chunk-page-size').value || 8);
  const pageSize = Number.isFinite(pageSizeRaw) && pageSizeRaw > 0 ? Math.floor(pageSizeRaw) : 8;
  chunkState.pageSize = pageSize;
  return { filename, query };
}

async function refreshChunks() {
  return withKbLoading('正在加载分片...', async () => {
    const { filename, query } = getChunkFilters();
    if (!filename) {
      renderChunksTable([]);
      chunkState.total = 0;
      document.getElementById('chunk-page-info').textContent = '第 1 / 1 页';
      return;
    }
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
  });
}

async function updateChunk(id, text) {
  return withKbLoading('正在保存分片...', async () => {
    await apiRequest(`/kb/chunk/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: { text },
    });
    showToast('分片已更新');
    await refreshChunks();
  });
}

async function deleteChunk(id) {
  return withKbLoading('正在删除分片...', async () => {
    await apiRequest(`/kb/chunk/${encodeURIComponent(id)}`, { method: 'DELETE' });
    showToast('分片已删除');
    await refreshChunks();
    await refreshStats();
  });
}

async function rebuildChunks() {
  return withKbLoading('正在重建分片...', async () => {
    const filename = String(chunkManagerState.selectedFilename || '').trim();
    if (!filename) {
      showToast('请先在文档列表中选择“分片管理”文档', false);
      return;
    }
    const ok = window.confirm(`将按当前分片规则重建文档 ${filename} 的分片，是否继续？`);
    if (!ok) return;
    const data = await apiRequest('/kb/chunks/rebuild', {
      method: 'POST',
      body: { filename },
    });
    showToast(`重建完成，chunks=${Number(data.chunks_added || 0)}`);
    await refreshChunks();
    await refreshDocuments();
    await refreshStats();
  });
}

async function refreshDocuments() {
  return withKbLoading('正在加载文档列表...', async () => {
    const data = await apiRequest('/kb/documents');
    const documents = data.documents || [];
    // 保存原始数据用于筛选
    window.allDocuments = documents;
    applyDocumentFilters(documents);
  });
}

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

async function refreshStats() {
  return withKbLoading('正在加载统计信息...', async () => {
    const data = await apiRequest('/stats');
    renderStatsTable(data.stats || {});
  });
}

function formatBytes(bytes) {
  const num = Number(bytes);
  if (!Number.isFinite(num) || num < 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let val = num;
  let idx = 0;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  return `${val.toFixed(2)} ${units[idx]}`;
}

function formatBytesPair(humanValue, bytesValue) {
  const bytesNum = Number(bytesValue);
  if (humanValue && Number.isFinite(bytesNum)) {
    return `${humanValue} (${bytesNum} B)`;
  }
  if (humanValue) return String(humanValue);
  if (Number.isFinite(bytesNum)) return `${formatBytes(bytesNum)} (${bytesNum} B)`;
  return '-';
}

function formatSimpleValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function formatDeviceMap(humanMap, bytesMap) {
  const map = humanMap && typeof humanMap === 'object' ? humanMap : bytesMap;
  if (!map || typeof map !== 'object') return '-';
  const entries = Object.entries(map);
  if (entries.length === 0) return '-';
  if (map === humanMap) {
    return entries.map(([k, v]) => `${k}: ${v}`).join(', ');
  }
  return entries.map(([k, v]) => `${k}: ${formatBytes(v)} (${Number(v)} B)`).join(', ');
}

function createTable(headers, rows) {
  const table = document.createElement('table');
  table.className = 'stats-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  headers.forEach((h) => {
    const th = document.createElement('th');
    th.textContent = h;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  if (!rows || rows.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = headers.length;
    td.textContent = '暂无数据';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      row.forEach((cell) => {
        const td = document.createElement('td');
        td.textContent = formatSimpleValue(cell);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }
  table.appendChild(tbody);
  return table;
}

function createPairTable(rows, leftHeader = '项目', rightHeader = '项目') {
  const pairRows = [];
  for (let i = 0; i < rows.length; i += 2) {
    const left = rows[i] || ['-', '-'];
    const right = rows[i + 1] || ['-', '-'];
    pairRows.push([left[0], left[1], right[0] || '-', right[1] || '-']);
  }
  return createTable([leftHeader, '值', rightHeader, '值'], pairRows);
}

function renderStatsTable(stats) {
  const container = document.getElementById('stats-output');
  if (!container) return;
  container.innerHTML = '';
  if (!stats || Object.keys(stats).length === 0) {
    container.textContent = '暂无数据';
    return;
  }

  const addSection = (title, table, target = container) => {
    const section = document.createElement('div');
    section.className = 'stats-section';
    const header = document.createElement('h4');
    header.textContent = title;
    section.appendChild(header);
    section.appendChild(table);
    target.appendChild(section);
  };

  const statsGrid = document.createElement('div');
  statsGrid.className = 'stats-grid';
  container.appendChild(statsGrid);

  const baseRows = [
    ['存储目录', stats.persist_dir],
    ['模型缓存目录', stats.model_cache_dir],
    ['文档数', stats.document_count],
    ['分片数', stats.chunk_count],
    ['向量维度', stats.dimension],
    ['索引向量数', stats.index_total],
    ['Embedding 模型', stats.embedding_model],
    ['Reranker 模型', stats.reranker_model],
    ['Chat 模型', stats.chat_model],
    ['LM Studio 聊天', stats.use_lm_studio_chat],
  ];
  const baseSection = createPairTable(baseRows, '项目', '项目');
  baseSection.classList.add('stats-table-full');
  addSection('基础统计', baseSection, statsGrid);

  const modelTotal = stats.models_memory_total || {};
  const modelTotalRows = [
    ['总计', formatBytesPair(modelTotal.human_total, modelTotal.bytes_total)],
    ['按设备', formatDeviceMap(modelTotal.human_by_device, modelTotal.bytes_by_device)],
  ];
  addSection('模型内存汇总', createTable(['项目', '值'], modelTotalRows));

  const loadedModels = stats.loaded_models || {};
  const modelOrder = ['embedding', 'reranker', 'chat'];
  const modelRows = [];
  const backendLabel = (val) => {
    if (val === 'local') return '本地';
    if (val === 'lm_studio') return 'LM Studio';
    return val || '-';
  };
  modelOrder.forEach((key) => {
    const info = loadedModels[key];
    if (!info) return;
    const mem = info.memory || {};
    modelRows.push([
      key,
      info.name,
      backendLabel(info.backend),
      info.loaded,
      info.device || '-',
      formatBytesPair(mem.human_total, mem.bytes_total),
      formatDeviceMap(mem.human_by_device, mem.bytes_by_device),
    ]);
  });
  addSection(
    '已加载模型',
    createTable(['类型', '模型', '后端', '已加载', '设备', '内存总计', '按设备'], modelRows)
  );

  const process = stats.process_memory || null;
  const processMemoryRows = [];
  if (process) {
    const fields = [
      ['RSS', 'human_rss', 'rss_bytes'],
      ['VMS', 'human_vms', 'vms_bytes'],
      ['USS', null, 'uss_bytes'],
      ['PSS', null, 'pss_bytes'],
      ['Shared', null, 'shared_bytes'],
      ['Text', null, 'text_bytes'],
      ['Data', null, 'data_bytes'],
      ['Dirty', null, 'dirty_bytes'],
      ['Working Set', 'human_working_set', 'working_set_bytes'],
      ['Private', 'human_private', 'private_bytes'],
      ['Peak Working Set', null, 'peak_working_set_bytes'],
      ['Pagefile', null, 'pagefile_bytes'],
      ['Peak Pagefile', null, 'peak_pagefile_bytes'],
      ['Max RSS', 'human_max_rss', 'max_rss_bytes'],
    ];
    fields.forEach(([label, humanKey, bytesKey]) => {
      const humanVal = humanKey ? process[humanKey] : null;
      const bytesVal = bytesKey ? process[bytesKey] : null;
      if (humanVal !== undefined && humanVal !== null) {
        processMemoryRows.push([label, formatBytesPair(humanVal, bytesVal)]);
        return;
      }
      if (bytesVal !== undefined && bytesVal !== null) {
        processMemoryRows.push([label, formatBytesPair(null, bytesVal)]);
      }
    });
  }
  const processMemSection = createPairTable(processMemoryRows, '指标', '指标');
  processMemSection.classList.add('stats-table-full');
  addSection('进程内存', processMemSection, statsGrid);

  const system = stats.system_usage || null;
  const systemRows = [];
  if (system) {
    systemRows.push(['CPU 使用率', system.cpu_percent != null ? `${system.cpu_percent}%` : '-']);
    systemRows.push(['CPU 核心数', system.cpu_count != null ? system.cpu_count : '-']);
    if (Array.isArray(system.load_avg)) {
      systemRows.push(['负载', system.load_avg.map((x) => Number(x).toFixed(2)).join(', ')]);
    }
    const mem = system.memory || null;
    if (mem) {
      systemRows.push(['内存总量', formatBytesPair(mem.human_total, mem.total_bytes)]);
      systemRows.push(['内存已用', formatBytesPair(mem.human_used, mem.used_bytes)]);
      systemRows.push(['内存可用', formatBytesPair(mem.human_available, mem.available_bytes)]);
      systemRows.push(['内存使用率', mem.percent != null ? `${mem.percent}%` : '-']);
    }
    const swap = system.swap || null;
    if (swap) {
      systemRows.push(['交换分区总量', formatBytesPair(swap.human_total, swap.total_bytes)]);
      systemRows.push(['交换分区已用', formatBytesPair(swap.human_used, swap.used_bytes)]);
      systemRows.push(['交换分区使用率', swap.percent != null ? `${swap.percent}%` : '-']);
    }
  }
  const systemSection = createPairTable(systemRows, '指标', '指标');
  systemSection.classList.add('stats-table-full');
  addSection('系统使用率', systemSection, statsGrid);

  const gpuUsage = stats.gpu_usage || null;
  const gpuUsageRows = [];
  if (gpuUsage && Array.isArray(gpuUsage.devices)) {
    gpuUsage.devices.forEach((dev) => {
      gpuUsageRows.push([
        dev.index,
        dev.name || '-',
        dev.utilization_gpu_percent != null ? `${dev.utilization_gpu_percent}%` : '-',
        dev.utilization_memory_percent != null ? `${dev.utilization_memory_percent}%` : '-',
        formatBytesPair(dev.human_memory_total, dev.memory_total_bytes),
        formatBytesPair(dev.human_memory_used, dev.memory_used_bytes),
        formatBytesPair(dev.human_memory_free, dev.memory_free_bytes),
      ]);
    });
  }
  addSection(
    'GPU 使用率',
    createTable(
      ['编号', '名称', 'GPU 使用率', '显存使用率', '总显存', '已用显存', '空闲显存'],
      gpuUsageRows
    )
  );

  const gpu = stats.gpu_memory || null;
  const gpuRows = [];
  if (gpu && Array.isArray(gpu.devices)) {
    gpu.devices.forEach((dev) => {
      gpuRows.push([
        dev.index,
        dev.name || '-',
        formatBytesPair(dev.human_total, dev.total_bytes),
        formatBytesPair(dev.human_free, dev.free_bytes),
        formatBytesPair(dev.human_allocated, dev.allocated_bytes),
        formatBytesPair(dev.human_reserved, dev.reserved_bytes),
        formatBytesPair(null, dev.max_allocated_bytes),
        formatBytesPair(null, dev.max_reserved_bytes),
      ]);
    });
  }
  addSection(
    'GPU 内存',
    createTable(
      ['编号', '名称', '总显存', '可用', '已分配', '已保留', '最大分配', '最大保留'],
      gpuRows
    )
  );

  const processes = Array.isArray(stats.processes) ? stats.processes : [];
  const processRows = processes.map((proc) => [
    proc.pid,
    proc.name,
    proc.cpu_percent != null ? `${proc.cpu_percent}%` : '-',
    proc.gpu_util_percent != null ? `${proc.gpu_util_percent}%` : '-',
    proc.memory_percent != null ? `${proc.memory_percent.toFixed(2)}%` : '-',
    formatBytesPair(proc.human_memory_rss, proc.memory_rss_bytes),
    formatBytesPair(proc.human_memory_vms, proc.memory_vms_bytes),
    proc.gpu_mem_util_percent != null ? `${proc.gpu_mem_util_percent}%` : '-',
    formatBytesPair(proc.human_gpu_memory, proc.gpu_memory_bytes),
    proc.gpu_memory_percent != null ? `${proc.gpu_memory_percent.toFixed(4)}%` : '-',
  ]);
  addSection(
    '进程资源占用',
    createTable(
      ['PID', '进程', 'CPU', 'GPU', '内存%', 'RSS', 'VMS', '显存使用率', '显存', '显存%'],
      processRows
    )
  );
}

async function addDocument(event) {
  event.preventDefault();
  return withKbLoading('正在新增文档...', async () => {
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
  });
}

async function uploadFile(event) {
  event.preventDefault();
  return withKbLoading('正在上传文件...', async () => {
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
  });
}

async function uploadBatchFiles(event) {
  event.preventDefault();
  return withKbLoading('正在批量上传...', async () => {
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
  });
}

async function deleteDocument(filename) {
  return withKbLoading('正在删除文档...', async () => {
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
  });
}

async function clearKnowledgeBase() {
  return withKbLoading('正在清空知识库...', async () => {
    const ok = window.confirm('确定清空整个知识库吗？该操作不可撤销。');
    if (!ok) return;
    await apiRequest('/kb', { method: 'DELETE' });
    showToast('知识库已清空');
    await refreshDocuments();
    await refreshStats();
  });
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
  
  const chunkQuery = document.getElementById('chunk-query');
  if (chunkQuery) {
    chunkQuery.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        chunkState.pageIndex = 1;
        refreshChunks().catch((err) => showToast(err.message, false));
      }
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

  const btnDeleteSelectedDocument = document.getElementById('btn-delete-selected-document');
  if (btnDeleteSelectedDocument) {
    btnDeleteSelectedDocument.addEventListener('click', () => {
      const selected = String(chunkManagerState.selectedFilename || '').trim();
      if (!selected) {
        showToast('请先在文档列表中选择“分片管理”文档', false);
        return;
      }
      const ok = window.confirm(`确定删除所选文档 ${selected} 吗？`);
      if (!ok) return;
      deleteDocument(selected)
        .then(async () => {
          chunkManagerState.selectedFilename = '';
          await refreshDocuments();
          await refreshChunks();
        })
        .catch((err) => showToast(err.message, false));
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

  const btnOpenStats = document.getElementById('btn-open-stats');
  if (btnOpenStats) {
    btnOpenStats.addEventListener('click', openStatsModal);
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

  const statsModalCloseBtn = document.getElementById('stats-modal-close-btn');
  if (statsModalCloseBtn) {
    statsModalCloseBtn.addEventListener('click', closeStatsModal);
  }
  const statsModal = document.getElementById('stats-modal');
  if (statsModal) {
    statsModal.addEventListener('click', (event) => {
      if (event.target === statsModal) {
        closeStatsModal();
      }
    });
  }

  const chunkManagerModalCloseBtn = document.getElementById('chunk-manager-modal-close-btn');
  if (chunkManagerModalCloseBtn) {
    chunkManagerModalCloseBtn.addEventListener('click', closeChunkManagerModal);
  }

  const chunkManagerModal = document.getElementById('chunk-manager-modal');
  if (chunkManagerModal) {
    chunkManagerModal.addEventListener('click', (event) => {
      if (event.target === chunkManagerModal) {
        closeChunkManagerModal();
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

  if (sourceDialogCloseBtn) {
    sourceDialogCloseBtn.addEventListener('click', closeSourceDialog);
  }
  if (sourceDialogCancelBtn) {
    sourceDialogCancelBtn.addEventListener('click', closeSourceDialog);
  }
  if (sourceDialog) {
    sourceDialog.addEventListener('click', (event) => {
      if (event.target === sourceDialog) {
        closeSourceDialog();
      }
    });
  }
  
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && chunkDialog && chunkDialog.classList.contains('open')) {
      closeChunkDialog();
    }
    if (event.key === 'Escape' && sourceDialog && sourceDialog.classList.contains('open')) {
      closeSourceDialog();
    }
    const chunkManagerModal = document.getElementById('chunk-manager-modal');
    if (event.key === 'Escape' && chunkManagerModal && chunkManagerModal.classList.contains('show')) {
      closeChunkManagerModal();
    }
    const statsModal = document.getElementById('stats-modal');
    if (event.key === 'Escape' && statsModal && statsModal.classList.contains('show')) {
      closeStatsModal();
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
      
      // 统计信息改为弹窗显示
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
