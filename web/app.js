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

function renderResults(results) {
  const list = document.getElementById('chat-results');
  list.innerHTML = '';
  if (!Array.isArray(results) || results.length === 0) {
    list.innerHTML = '<li class="result-item">无检索结果</li>';
    return;
  }
  for (const item of results) {
    const li = document.createElement('li');
    li.className = 'result-item';
    const title = document.createElement('div');
    title.className = 'result-title';
    title.textContent = String(item.filename || 'unknown');
    const meta = document.createElement('div');
    meta.textContent = `similarity=${item.similarity ?? '-'} | distance=${item.distance ?? '-'}`;
    li.appendChild(title);
    li.appendChild(meta);
    list.appendChild(li);
  }
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
  for (const item of history) {
    const li = document.createElement('li');
    li.className = 'history-item';
    const head = document.createElement('div');
    head.className = 'history-row';
    const title = document.createElement('div');
    title.className = 'history-title';
    title.textContent = pickHistoryTitle(item);
    head.appendChild(title);

    if (item?.id != null) {
      const delBtn = document.createElement('button');
      delBtn.className = 'history-delete';
      delBtn.type = 'button';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', () => {
        const ok = window.confirm('确定删除该记录吗？');
        if (!ok) return;
        deleteHistory(item.id).catch((err) => showToast(err.message, false));
      });
      head.appendChild(delBtn);
    }
    const meta = document.createElement('div');
    meta.className = 'history-meta';
    meta.textContent = `${formatHistoryTime(item?.timestamp)} · ${item?.action || 'unknown'}`;
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
  const answerBox = document.getElementById('chat-answer');
  renderAnswer(answerBox, '请求中...');

  const body = {
    query,
    k: Number.isFinite(k) && k > 0 ? Math.floor(k) : 2,
    generate_answer: generateAnswer,
    user_id: userId,
  };
  const sessionId = chatSessionInput.value.trim();
  if (sessionId) {
    body.session_id = sessionId;
  }
  if (thresholdRaw) {
    const threshold = Number(thresholdRaw);
    if (!Number.isFinite(threshold)) {
      showToast('相关性阈值必须是数字', false);
      renderAnswer(answerBox, '等待提问...');
      return;
    }
    body.relevance_threshold = threshold;
  }

  try {
    await runChatStream(body, answerBox);
    refreshHistory().catch(() => {});
    showToast('查询完成');
  } catch (error) {
    renderAnswer(answerBox, '查询失败');
    renderResults([]);
    showToast(error.message || '请求失败', false);
  }
}

function renderAnswer(container, text) {
  const raw = String(text || '');
  if (window.marked) {
    const html = window.marked.parse(raw, { breaks: true });
    container.innerHTML = window.DOMPurify ? window.DOMPurify.sanitize(html) : html;
    return;
  }
  container.innerHTML = renderMarkdownFallback(raw);
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
  const data = await apiRequest('/history?limit=20&action=query');
  renderHistory(data.history || []);
}

async function deleteHistory(id) {
  await apiRequest(`/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
  showToast('记录已删除');
  await refreshHistory();
}

async function runChatStream(body, answerBox) {
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

  renderAnswer(answerBox, '');
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
      renderResults(payload.results || []);
      if (payload.session_id) {
        chatSessionInput.value = String(payload.session_id);
      }
      return;
    }
    if (eventType === 'delta') {
      const delta = String(payload.delta || '');
      if (!delta) return;
      answer += delta;
      renderAnswer(answerBox, answer);
      return;
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

function renderDocsTable(documents) {
  const tbody = document.getElementById('docs-tbody');
  tbody.innerHTML = '';
  if (!Array.isArray(documents) || documents.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3">暂无文档</td></tr>';
    return;
  }

  for (const doc of documents) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${String(doc.filename || '')}</td><td>${Number(doc.chunk_count || 0)}</td><td>${Number(doc.char_count || 0)}</td>`;
    tbody.appendChild(tr);
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
    chatSessionInput.value = '';
    showToast('已创建新会话');
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
  try {
    await Promise.all([refreshDocuments(), refreshStats(), refreshHistory(), refreshChunks()]);
  } catch (error) {
    showToast(error.message || '初始化失败', false);
  }
}

bootstrap();
