// Elements
const el = {
    btnOpenSource: document.getElementById('btn-open-source'),
    btnLogin: document.getElementById('btn-login'),
    btnAuthLogin: document.getElementById('btn-auth-login'),
    btnStart: document.getElementById('btn-start'),
    btnOpenLogModal: document.getElementById('btn-open-log-modal'),
    btnClearLogModal: document.getElementById('btn-clear-log-modal'),
    btnCloseLogModal: document.getElementById('btn-close-log-modal'),
    btnSyncLocal: document.getElementById('btn-sync-local'),
    btnSyncRemote: document.getElementById('btn-sync-remote'),
    btnSyncCatalog: document.getElementById('btn-sync-catalog'),
    btnSelectUploadable: document.getElementById('btn-select-uploadable'),
    btnClearSelection: document.getElementById('btn-clear-selection'),
    btnSelectLatest: document.getElementById('btn-select-latest'),
    btnViewAll: document.getElementById('btn-view-all'),
    btnViewPending: document.getElementById('btn-view-pending'),
    btnViewConflicts: document.getElementById('btn-view-conflicts'),
    btnViewMatched: document.getElementById('btn-view-matched'),
    btnChooseSourceDir: document.getElementById('btn-choose-source-dir'),
    sourceDirInput: document.getElementById('source-dir-input'),
    localBookSelect: document.getElementById('local-book-select'),
    remoteBookSelect: document.getElementById('remote-book-select'),
    remoteVolumeSelect: document.getElementById('remote-volume-select'),
    localVolumeSelect: document.getElementById('local-volume-select'),
    chapterDiffTableBody: document.getElementById('chapter-diff-table-body'),
    selectionSummary: document.getElementById('selection-summary'),
    targetSummary: document.getElementById('target-summary'),
    latestCountInput: document.getElementById('latest-count-input'),
    logContainer: document.getElementById('log-container'),
    statusBadge: document.getElementById('status-badge'),
    
    progressWrapper: document.getElementById('progress-wrapper'),
    progressBar: document.getElementById('progress-bar'),
    progressText: document.getElementById('progress-text'),

    modalBackdrop: document.getElementById('modal-backdrop'),
    modalBox: document.getElementById('modal-box'),
    modalTitle: document.getElementById('modal-title'),
    modalMsg: document.getElementById('modal-msg'),
    modalBtnOk: document.getElementById('modal-btn-ok'),
    modalBtnCancel: document.getElementById('modal-btn-cancel'),
    logModalBackdrop: document.getElementById('log-modal-backdrop'),
    logModalBox: document.getElementById('log-modal-box'),
    authGate: document.getElementById('auth-gate'),
    workspaceShell: document.getElementById('workspace-shell'),
};

let currentBooks = [];
let currentRemoteBooks = [];
let currentRemoteCatalogs = {};
let currentChapterMatchSummary = null;
let currentChapterDiffRows = [];
let currentLocalVolumes = [];
let selectedChapterRowIds = new Set();
let chapterTableView = 'all';
let isPublishing = false;
let selectedLocalBookName = '';
let loginPollTimer = null;

function getCurrentLocalBook() {
    if (!selectedLocalBookName) {
        return currentBooks.length > 0 ? currentBooks[0] : null;
    }
    return currentBooks.find(book => book.name === selectedLocalBookName) || null;
}

async function getApiOrThrow(options = {}) {
    if (typeof window.getPywebviewApi !== 'function') {
        throw new Error('PyWebView bridge helper is missing');
    }
    return await window.getPywebviewApi(options);
}

window.addEventListener('pywebviewready', async function() {
    appendLog(">>> UI 框架加载成功，已连接 Python 内核 🚀", "text-accent-400 font-bold");

    try {
        await loadPersistedConfig();
        const loggedIn = await checkState();
        if (loggedIn) {
            await refreshBooks();
        }
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 初始化 PyWebView 失败: ${e}`, "text-rose-500");
    }
});

window.appendLog = function(msg, colorClass = "text-[#94a3b8]") {
    const div = document.createElement('div');
    div.className = `fade-in break-words ${colorClass}`;
    div.textContent = msg;
    el.logContainer.appendChild(div);
    el.logContainer.scrollTop = el.logContainer.scrollHeight;
};

window.updateProgress = function(current, total) {
    if (total <= 0) return;
    const percent = Math.min(100, Math.round((current / total) * 100));
    el.progressWrapper.classList.remove('hidden');
    el.progressText.classList.remove('hidden');
    el.progressBar.style.width = percent + '%';
    el.progressText.textContent = `${current} / ${total}`;
};

window.showModal = function(title, message, isError = false, showCancel = true) {
    return new Promise((resolve) => {
        el.modalTitle.innerHTML = isError 
            ? `<div class="w-7 h-7 rounded-full bg-rose-100 text-rose-500 flex items-center justify-center text-sm"><i class="fa-solid fa-triangle-exclamation"></i></div> ${title}`
            : `<div class="w-7 h-7 rounded-full bg-accent-100 text-accent-500 flex items-center justify-center text-sm"><i class="fa-solid fa-circle-question"></i></div> ${title}`;
        
        el.modalMsg.textContent = message;
        
        if (!showCancel) {
            el.modalBtnCancel.style.display = 'none';
        } else {
            el.modalBtnCancel.style.display = 'block';
        }

        el.modalBackdrop.classList.remove('opacity-0', 'pointer-events-none');
        el.modalBox.classList.remove('scale-95');
        el.modalBox.classList.add('scale-100');

        const cleanup = () => {
            el.modalBtnOk.onclick = null;
            el.modalBtnCancel.onclick = null;
            el.modalBackdrop.classList.add('opacity-0', 'pointer-events-none');
            el.modalBox.classList.remove('scale-100');
            el.modalBox.classList.add('scale-95');
        };

        el.modalBtnOk.onclick = () => { cleanup(); resolve(true); };
        el.modalBtnCancel.onclick = () => { cleanup(); resolve(false); };
    });
};

function toggleUI(disabled) {
    isPublishing = disabled;
    el.btnStart.disabled = disabled;
    el.btnLogin.disabled = disabled;
    el.btnOpenSource.disabled = disabled;
    el.btnSyncLocal.disabled = disabled;
    el.btnSyncRemote.disabled = disabled;
    el.btnSyncCatalog.disabled = disabled;
    el.btnChooseSourceDir.disabled = disabled;
    el.btnSelectLatest.disabled = disabled;
    el.remoteBookSelect.disabled = disabled;
    el.remoteVolumeSelect.disabled = disabled;
    el.localVolumeSelect.disabled = disabled;
    el.latestCountInput.disabled = disabled;
    
    if (disabled) {
        el.btnStart.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> 正在上传章节...`;
        el.btnStart.classList.add('opacity-50', 'cursor-not-allowed', 'shadow-none');
        el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 运行中`;
        el.statusBadge.className = "px-3 py-1.5 rounded-lg text-[11px] font-bold tracking-widest bg-amber-50 text-amber-600 border border-amber-200 flex items-center gap-2 shadow-sm mr-2";
    } else {
        el.btnStart.innerHTML = `<i class="fa-solid fa-rocket"></i> 上传选定章节`;
        el.btnStart.classList.remove('opacity-50', 'cursor-not-allowed', 'shadow-none');
        el.progressWrapper.classList.add('hidden');
        el.progressText.classList.add('hidden');
        el.progressBar.style.width = '0%';
        checkState();
    }
}

function applyAuthState(loggedIn) {
    if (el.authGate) {
        el.authGate.classList.toggle('hidden', loggedIn);
        el.authGate.classList.toggle('flex', !loggedIn);
    }
    if (el.workspaceShell) {
        el.workspaceShell.classList.toggle('hidden', !loggedIn);
        el.workspaceShell.classList.toggle('flex', loggedIn);
    }
}

function updateStatusBadge(loggedIn) {
    if (!el.statusBadge) return;
    if (loggedIn) {
        el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 就绪`;
        el.statusBadge.className = "px-3 py-1.5 rounded-lg text-[11px] font-bold tracking-widest bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center gap-2 shadow-sm mr-2";
    } else {
        el.statusBadge.innerHTML = `<div class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse shadow-[0_0_3px_currentColor]"></div> 未登录`;
        el.statusBadge.className = "px-3 py-1.5 rounded-lg text-[11px] font-bold tracking-widest bg-rose-50 text-rose-600 border border-rose-200 flex items-center gap-2 shadow-sm mr-2";
    }
}

function setLoginLoading(loading) {
    const loadingHtml = `<i class="fa-solid fa-circle-notch fa-spin"></i> 登录中...`;
    const idleHeaderHtml = `<i class="fa-solid fa-fingerprint shadow-sm"></i> 重置授权`;
    const idleGateHtml = `<i class="fa-solid fa-fingerprint"></i> 登录`;

    if (el.btnLogin) {
        el.btnLogin.disabled = loading;
        el.btnLogin.innerHTML = loading ? loadingHtml : idleHeaderHtml;
    }
    if (el.btnAuthLogin) {
        el.btnAuthLogin.disabled = loading;
        el.btnAuthLogin.innerHTML = loading ? loadingHtml : idleGateHtml;
        el.btnAuthLogin.classList.toggle('opacity-70', loading);
        el.btnAuthLogin.classList.toggle('cursor-not-allowed', loading);
    }
}

function stopLoginPolling() {
    if (loginPollTimer) {
        clearInterval(loginPollTimer);
        loginPollTimer = null;
    }
}

async function startLoginPolling() {
    stopLoginPolling();
    loginPollTimer = setInterval(async () => {
        try {
            const api = await getApiOrThrow({ wait: false });
            const status = await api.get_login_status();
            const loggedIn = await api.check_login_state();

            if (loggedIn) {
                stopLoginPolling();
                setLoginLoading(false);
                await checkState();
                await loadPersistedConfig();
                await refreshBooks();
                appendLog(`[SYSTEM] 登录凭证已更新`, "text-emerald-400");
                return;
            }

            if (status?.state === 'failed' || status?.state === 'cancelled') {
                stopLoginPolling();
                setLoginLoading(false);
                await checkState();
                const message = status?.message || '登录未完成，请重试。';
                await showModal('登录未完成', message, true, false);
            }
        } catch (e) {
            stopLoginPolling();
            setLoginLoading(false);
            console.error(e);
            appendLog(`[GUI错误] 登录状态轮询失败: ${e}`, "text-rose-500");
        }
    }, 1000);
}

async function loadPersistedConfig() {
    const api = await getApiOrThrow({ timeoutMs: 5000, intervalMs: 50 });
    const config = await api.get_config();
    if (config && config.source_dir) {
        el.sourceDirInput.value = config.source_dir;
        el.sourceDirInput.classList.remove('text-slate-600', 'placeholder-slate-400');
        el.sourceDirInput.classList.add('text-accent-600');
    }
    currentRemoteBooks = Array.isArray(config?.remote_books) ? config.remote_books : [];
    currentRemoteCatalogs = config?.remote_catalogs && typeof config.remote_catalogs === 'object'
        ? config.remote_catalogs
        : {};
    refreshRemoteBookSelect();
    refreshRemoteVolumeSelect();
    updateTargetSummary();
}

function getSelectedRemoteBookName() {
    return el.remoteBookSelect?.value?.trim() || '';
}

function getSelectedRemoteCatalog() {
    const remoteBookName = getSelectedRemoteBookName();
    return remoteBookName ? currentRemoteCatalogs?.[remoteBookName] : null;
}

function getSelectedLocalVolumeName() {
    return el.localVolumeSelect?.value?.trim() || '默认卷';
}

function statusLabel(diffStatus) {
    if (diffStatus === 'matched') return '已上传且匹配';
    if (diffStatus === 'title_conflict') return '已上传但标题不一致';
    return '可上传';
}

function statusBadgeClass(diffStatus) {
    if (diffStatus === 'matched') {
        return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    }
    if (diffStatus === 'title_conflict') {
        return 'bg-amber-50 text-amber-700 border border-amber-200';
    }
    return 'bg-sky-50 text-sky-700 border border-sky-200';
}

function isRowSelectable(row) {
    return row.diff_status === 'uploadable';
}

function updateSelectionSummary() {
    if (!el.selectionSummary) return;
    el.selectionSummary.textContent = `已选 ${selectedChapterRowIds.size} 章`;
}

function updateTargetSummary() {
    if (!el.targetSummary) return;
    const localBook = getCurrentLocalBook()?.name || '未识别本地书';
    const localVolume = getSelectedLocalVolumeName() || '默认卷';
    const remoteBook = getSelectedRemoteBookName() || '未选择后台书';
    const remoteVolume = el.remoteVolumeSelect?.value?.trim() || '后台默认卷';
    el.targetSummary.textContent = `目标：${localBook} / ${localVolume} -> ${remoteBook} / ${remoteVolume}`;
}

function setButtonLoading(button, loading, idleHtml, loadingHtml) {
    if (!button) return;
    if (loading) {
        button.innerHTML = loadingHtml;
        button.disabled = true;
        button.classList.add('opacity-70', 'cursor-not-allowed');
    } else {
        button.innerHTML = idleHtml;
        button.disabled = false;
        button.classList.remove('opacity-70', 'cursor-not-allowed');
    }
}

function markRowsUploaded(rowIds) {
    const uploadedSet = new Set(rowIds);
    currentChapterDiffRows = currentChapterDiffRows.map(row => {
        if (!uploadedSet.has(row.row_id)) {
            return row;
        }
        return {
            ...row,
            diff_status: 'matched',
            remote_status: '已发布',
            remote_title: row.local_title || row.remote_title,
            default_selected: false,
        };
    });
    selectedChapterRowIds = new Set();
    renderChapterDiffTable();
}

function openLogModal() {
    if (!el.logModalBackdrop || !el.logModalBox) return;
    el.logModalBackdrop.classList.remove('opacity-0', 'pointer-events-none');
    el.logModalBox.classList.remove('scale-95');
    el.logModalBox.classList.add('scale-100');
}

function closeLogModal() {
    if (!el.logModalBackdrop || !el.logModalBox) return;
    el.logModalBackdrop.classList.add('opacity-0', 'pointer-events-none');
    el.logModalBox.classList.remove('scale-100');
    el.logModalBox.classList.add('scale-95');
}

function renderChapterDiffTable() {
    if (!el.chapterDiffTableBody) return;

    let visibleRows = currentChapterDiffRows;
    if (chapterTableView === 'pending') {
        visibleRows = currentChapterDiffRows.filter(row => row.diff_status === 'uploadable');
    } else if (chapterTableView === 'conflicts') {
        visibleRows = currentChapterDiffRows.filter(row => row.diff_status === 'title_conflict');
    } else if (chapterTableView === 'matched') {
        visibleRows = currentChapterDiffRows.filter(row => row.diff_status === 'matched');
    }

    if (!Array.isArray(visibleRows) || visibleRows.length === 0) {
        el.chapterDiffTableBody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-slate-400 text-center font-semibold">请先同步后台书库并同步卷和章节</td></tr>';
        updateSelectionSummary();
        return;
    }

    const rowsHtml = visibleRows.map(row => {
        const selectable = isRowSelectable(row);
        const checked = selectedChapterRowIds.has(row.row_id) ? 'checked' : '';
        const disabled = selectable ? '' : 'disabled';
        const badgeClass = statusBadgeClass(row.diff_status);
        const localTitle = row.local_title || row.filename || '';
        const remoteTitle = row.remote_title || '-';

        return `
            <tr class="align-top">
              <td class="px-4 py-2.5">
                ${selectable
                    ? `<input type="checkbox" data-row-id="${row.row_id}" ${checked} ${disabled} class="chapter-row-checkbox" />`
                    : `<span class="text-slate-300 font-bold">--</span>`}
              </td>
              <td class="px-4 py-2.5 font-semibold text-slate-700 whitespace-nowrap">第${row.chapter_num || '?'}章</td>
              <td class="px-4 py-2.5 text-slate-700 leading-relaxed max-w-[340px] truncate" title="${localTitle}">${localTitle}</td>
              <td class="px-4 py-2.5 text-slate-500 leading-relaxed max-w-[340px] truncate" title="${remoteTitle}">${remoteTitle}</td>
              <td class="px-4 py-2.5 text-slate-500 whitespace-nowrap">${row.remote_status || '-'}</td>
              <td class="px-4 py-2.5"><span class="inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold whitespace-nowrap ${badgeClass}">${statusLabel(row.diff_status)}</span></td>
            </tr>
        `;
    }).join('');

    el.chapterDiffTableBody.innerHTML = rowsHtml;
    el.chapterDiffTableBody.querySelectorAll('.chapter-row-checkbox').forEach(input => {
        input.addEventListener('change', (event) => {
            const rowId = event.target.getAttribute('data-row-id');
            if (event.target.checked) {
                selectedChapterRowIds.add(rowId);
            } else {
                selectedChapterRowIds.delete(rowId);
            }
            updateSelectionSummary();
        });
    });
    updateSelectionSummary();
}

function applySelectionFilter(predicate) {
    selectedChapterRowIds = new Set(
        currentChapterDiffRows.filter(predicate).map(row => row.row_id)
    );
    renderChapterDiffTable();
}

function normalizeChapterNum(value) {
    const text = String(value ?? '').trim();
    const match = text.match(/\d+/);
    return match ? String(parseInt(match[0], 10)) : text;
}

function selectLatestRows(count) {
    const parsedCount = parseInt(count, 10);
    if (!Number.isFinite(parsedCount) || parsedCount <= 0) {
        selectedChapterRowIds = new Set();
        renderChapterDiffTable();
        return;
    }

    const rowIds = currentChapterDiffRows
        .filter(row => row.diff_status === 'uploadable')
        .map(row => ({
            rowId: row.row_id,
            chapterNum: parseInt(normalizeChapterNum(row.chapter_num) || '0', 10),
        }))
        .sort((a, b) => a.chapterNum - b.chapterNum)
        .slice(0, parsedCount)
        .map(item => item.rowId);

    selectedChapterRowIds = new Set(rowIds);
    renderChapterDiffTable();
}

function buildPublishConfirmationMessage(localBookName, remoteBookName, remoteVolumeName, summary) {
    const lines = [
        `本地稿件：${localBookName}`,
        `后台目标小说：${remoteBookName}`,
        `后台目标分卷：${remoteVolumeName || '沿用后台当前默认卷'}`,
    ];

    if (summary) {
        lines.push(
            '',
            `章节匹配摘要：`,
            `- 本地 ${summary.local_total} 章`,
            `- 后台 ${summary.remote_total} 章`,
            `- 命中 ${summary.matched_total} 章（将优先接管已有章节/草稿）`,
            `- 待新增 ${summary.pending_total} 章`,
        );

        if (Array.isArray(summary.title_conflicts) && summary.title_conflicts.length > 0) {
            lines.push('', '标题不一致预警：');
            summary.title_conflicts.slice(0, 10).forEach(item => {
                lines.push(`- 第${item.chapter_num}章：本地《${item.local_title}》 / 后台《${item.remote_title}》`);
            });
        }

        if (Array.isArray(summary.matched_preview) && summary.matched_preview.length > 0) {
            lines.push('', '将接管的章节预览：');
            summary.matched_preview.slice(0, 10).forEach(item => {
                lines.push(`- 第${item.chapter_num}章 ${item.local_title || ''} [${item.remote_status || 'unknown'}]`);
            });
        }

        if (Array.isArray(summary.pending_preview) && summary.pending_preview.length > 0) {
            lines.push('', '将新建的章节预览：');
            summary.pending_preview.slice(0, 10).forEach(item => {
                lines.push(`- 第${item.chapter_num}章 ${item.local_title || item.filename || ''}`);
            });
        }
    }

    lines.push('', '确认后开始自动发布。');
    return lines.join('\n');
}

function refreshRemoteBookSelect() {
    if (!el.remoteBookSelect) return;
    const previousValue = el.remoteBookSelect.value;
    el.remoteBookSelect.innerHTML = '';

    if (!Array.isArray(currentRemoteBooks) || currentRemoteBooks.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '请先同步后台书库';
        el.remoteBookSelect.appendChild(opt);
        return;
    }

    currentRemoteBooks.forEach((book, index) => {
        const opt = document.createElement('option');
        opt.value = book.name;
        opt.textContent = book.name;
        if (index === 0) {
            opt.selected = true;
        }
        el.remoteBookSelect.appendChild(opt);
    });

    if (previousValue && currentRemoteBooks.some(book => book.name === previousValue)) {
        el.remoteBookSelect.value = previousValue;
        return;
    }

    const localBook = getCurrentLocalBook();
    if (localBook) {
        const matched = currentRemoteBooks.find(book => book.name === localBook.name);
        if (matched) {
            el.remoteBookSelect.value = matched.name;
            return;
        }
    }
}

function refreshLocalBookSelect() {
    if (!el.localBookSelect) return;
    const previousValue = selectedLocalBookName || el.localBookSelect.value;
    el.localBookSelect.innerHTML = '';

    if (!Array.isArray(currentBooks) || currentBooks.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '当前目录未识别到本地书';
        el.localBookSelect.appendChild(opt);
        selectedLocalBookName = '';
        return;
    }

    currentBooks.forEach((book, index) => {
        const opt = document.createElement('option');
        opt.value = book.name;
        opt.textContent = `${book.name} (${book.count}章)`;
        if (index === 0) {
            opt.selected = true;
        }
        el.localBookSelect.appendChild(opt);
    });

    const options = Array.from(el.localBookSelect.options).map(opt => opt.value);
    if (previousValue && options.includes(previousValue)) {
        el.localBookSelect.value = previousValue;
        selectedLocalBookName = previousValue;
    } else {
        selectedLocalBookName = el.localBookSelect.value;
    }
}

function refreshRemoteVolumeSelect() {
    if (!el.remoteVolumeSelect) return;
    const previousValue = el.remoteVolumeSelect.value;
    el.remoteVolumeSelect.innerHTML = '';

    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = '不切换，沿用后台当前默认卷';
    el.remoteVolumeSelect.appendChild(emptyOption);

    const catalog = getSelectedRemoteCatalog();
    const volumes = Array.isArray(catalog?.volumes) ? catalog.volumes : [];
    volumes.forEach(volumeName => {
        const opt = document.createElement('option');
        opt.value = volumeName;
        opt.textContent = volumeName;
        el.remoteVolumeSelect.appendChild(opt);
    });

    if (previousValue) {
        const options = Array.from(el.remoteVolumeSelect.options).map(opt => opt.value);
        if (options.includes(previousValue)) {
            el.remoteVolumeSelect.value = previousValue;
        }
    }
}

function refreshLocalVolumeSelect() {
    if (!el.localVolumeSelect) return;
    const previousValue = el.localVolumeSelect.value;
    el.localVolumeSelect.innerHTML = '';

    const volumes = Array.isArray(currentLocalVolumes) && currentLocalVolumes.length > 0
        ? currentLocalVolumes
        : [{ name: '默认卷' }];

    volumes.forEach((volume, index) => {
        const opt = document.createElement('option');
        opt.value = volume.name;
        opt.textContent = volume.name;
        if (index === 0) {
            opt.selected = true;
        }
        el.localVolumeSelect.appendChild(opt);
    });

    if (previousValue) {
        const options = Array.from(el.localVolumeSelect.options).map(opt => opt.value);
        if (options.includes(previousValue)) {
            el.localVolumeSelect.value = previousValue;
        }
    }

    if (!el.localVolumeSelect.value && el.localVolumeSelect.options.length > 0) {
        el.localVolumeSelect.value = el.localVolumeSelect.options[0].value;
    }
}

async function refreshLocalVolumes() {
    currentLocalVolumes = [];
    const localBook = getCurrentLocalBook();
    if (!localBook) {
        refreshLocalVolumeSelect();
        return;
    }

    try {
        const api = await getApiOrThrow({ wait: false });
        currentLocalVolumes = await api.get_local_volumes(localBook.name);
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 本地卷列表读取失败: ${e}`, "text-rose-500");
    }
    refreshLocalVolumeSelect();
    updateTargetSummary();
}

async function refreshChapterMatchSummary() {
    currentChapterMatchSummary = null;
    currentChapterDiffRows = [];
    selectedChapterRowIds = new Set();
    renderChapterDiffTable();

    const remoteBookName = getSelectedRemoteBookName();
    const localVolumeName = getSelectedLocalVolumeName();
    const localBook = getCurrentLocalBook();
    if (!localBook || !remoteBookName) {
        return;
    }
    if (!currentRemoteCatalogs?.[remoteBookName]) {
        return;
    }

    try {
        const api = await getApiOrThrow({ wait: false });
        const diffData = await api.get_chapter_diff_data(localBook.name, remoteBookName, localVolumeName);
        currentChapterMatchSummary = diffData.summary;
        currentChapterDiffRows = Array.isArray(diffData.rows) ? diffData.rows : [];
        selectedChapterRowIds = new Set(
            currentChapterDiffRows.filter(row => row.default_selected && isRowSelectable(row)).map(row => row.row_id)
        );
        renderChapterDiffTable();
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 章节匹配摘要失败: ${e}`, "text-rose-500");
    }
}

async function checkState() {
    let ok = false;
    try {
        const api = await getApiOrThrow({ wait: false });
        ok = await api.check_login_state();
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 检查登录状态失败: ${e}`, "text-rose-500");
        applyAuthState(false);
        updateStatusBadge(false);
        return false;
    }
    applyAuthState(ok);
    updateStatusBadge(ok);
    return ok;
}

async function refreshBooks() {
    try {
        const api = await getApiOrThrow({ wait: false });
        currentBooks = await api.get_books();
        if (currentBooks.length > 0) {
            refreshLocalBookSelect();
            await refreshLocalVolumes();
            refreshRemoteBookSelect();
            refreshRemoteVolumeSelect();
            await refreshChapterMatchSummary();
            updateTargetSummary();
        }
    } catch (e) {
        console.error(e);
        currentBooks = [];
        appendLog(`[GUI错误] 刷新小说列表失败: ${e}`, "text-rose-500");
    }
}

el.localVolumeSelect.addEventListener('change', () => {
    refreshChapterMatchSummary();
    updateTargetSummary();
});
if (el.btnOpenLogModal) el.btnOpenLogModal.addEventListener('click', () => {
    openLogModal();
});

if (el.btnSyncLocal) el.btnSyncLocal.addEventListener('click', async () => {
    if (isPublishing) return;
    setButtonLoading(
        el.btnSyncLocal,
        true,
        '同步本地书库',
        '<i class="fa-solid fa-circle-notch fa-spin"></i> 同步中...'
    );
    try {
        await refreshBooks();
        appendLog(`[SYSTEM] 本地书库同步完成，共 ${currentBooks.length} 本`, "text-indigo-400");
    } finally {
        setButtonLoading(el.btnSyncLocal, false, '同步本地书库', '');
    }
});

if (el.btnClearLogModal) el.btnClearLogModal.addEventListener('click', () => {
    el.logContainer.innerHTML = '<div class="text-[#64748b] fade-in font-semibold">> 运行日志已被清空。</div>';
});

if (el.btnCloseLogModal) el.btnCloseLogModal.addEventListener('click', () => {
    closeLogModal();
});

if (el.logModalBackdrop) el.logModalBackdrop.addEventListener('click', (e) => {
    if (e.target === el.logModalBackdrop) {
        closeLogModal();
    }
});

if (el.btnSelectUploadable) el.btnSelectUploadable.addEventListener('click', () => {
    applySelectionFilter(row => row.diff_status === 'uploadable');
});

if (el.btnClearSelection) el.btnClearSelection.addEventListener('click', () => {
    selectedChapterRowIds = new Set();
    renderChapterDiffTable();
});

if (el.btnSelectLatest) el.btnSelectLatest.addEventListener('click', () => {
    selectLatestRows(el.latestCountInput.value);
});

if (el.btnViewAll) el.btnViewAll.addEventListener('click', () => {
    chapterTableView = 'all';
    el.btnViewAll.className = 'px-3 py-1.5 text-[11px] font-bold bg-accent-50 text-accent-700';
    if (el.btnViewPending) el.btnViewPending.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewConflicts) el.btnViewConflicts.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewMatched) el.btnViewMatched.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    renderChapterDiffTable();
});

if (el.btnViewPending) el.btnViewPending.addEventListener('click', () => {
    chapterTableView = 'pending';
    if (el.btnViewAll) el.btnViewAll.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    el.btnViewPending.className = 'px-3 py-1.5 text-[11px] font-bold bg-accent-50 text-accent-700';
    if (el.btnViewConflicts) el.btnViewConflicts.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewMatched) el.btnViewMatched.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    renderChapterDiffTable();
});

if (el.btnViewConflicts) el.btnViewConflicts.addEventListener('click', () => {
    chapterTableView = 'conflicts';
    if (el.btnViewAll) el.btnViewAll.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewPending) el.btnViewPending.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    el.btnViewConflicts.className = 'px-3 py-1.5 text-[11px] font-bold bg-accent-50 text-accent-700';
    if (el.btnViewMatched) el.btnViewMatched.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    renderChapterDiffTable();
});

if (el.btnViewMatched) el.btnViewMatched.addEventListener('click', () => {
    chapterTableView = 'matched';
    if (el.btnViewAll) el.btnViewAll.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewPending) el.btnViewPending.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    if (el.btnViewConflicts) el.btnViewConflicts.className = 'px-3 py-1.5 text-[11px] font-bold bg-white text-slate-500';
    el.btnViewMatched.className = 'px-3 py-1.5 text-[11px] font-bold bg-accent-50 text-accent-700';
    renderChapterDiffTable();
});

if (el.btnSyncRemote) el.btnSyncRemote.addEventListener('click', async () => {
    if (isPublishing) return;
    setButtonLoading(
        el.btnSyncRemote,
        true,
        '同步后台书库',
        '<i class="fa-solid fa-circle-notch fa-spin"></i> 同步中...'
    );
    toggleUI(true);
    try {
        const api = await getApiOrThrow({ wait: false });
        currentRemoteBooks = await api.fetch_remote_books();
        refreshRemoteBookSelect();
        refreshRemoteVolumeSelect();
        await refreshChapterMatchSummary();
        updateTargetSummary();
        appendLog(`[SYSTEM] 后台书库同步完成，共 ${currentRemoteBooks.length} 本`, "text-emerald-400");
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 同步后台书库失败: ${e}`, "text-rose-500");
    } finally {
        toggleUI(false);
        setButtonLoading(el.btnSyncRemote, false, '同步后台书库', '');
    }
});

if (el.btnSyncCatalog) el.btnSyncCatalog.addEventListener('click', async () => {
    if (isPublishing) return;
    const remoteBookName = getSelectedRemoteBookName();
    if (!remoteBookName) {
        showModal('目标缺失', '请先同步后台书库，并选择一本后台目标小说。', true, false);
        return;
    }

    setButtonLoading(
        el.btnSyncCatalog,
        true,
        '同步卷和章节',
        '<i class="fa-solid fa-circle-notch fa-spin"></i> 同步中...'
    );
    toggleUI(true);
    try {
        const api = await getApiOrThrow({ wait: false });
        const catalog = await api.fetch_remote_catalog(remoteBookName);
        currentRemoteCatalogs[remoteBookName] = catalog;
        refreshRemoteVolumeSelect();
        await refreshChapterMatchSummary();
        updateTargetSummary();
        appendLog(`[SYSTEM] 已同步《${remoteBookName}》后台目录：${catalog.volumes.length} 卷，${catalog.chapters.length} 章`, "text-cyan-400");
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 同步后台卷和章节失败: ${e}`, "text-rose-500");
    } finally {
        toggleUI(false);
        setButtonLoading(el.btnSyncCatalog, false, '同步卷和章节', '');
    }
});

async function handleLoginClick() {
    if (isPublishing) return;
    setLoginLoading(true);
    try {
        const api = await getApiOrThrow({ wait: false });
        const loginStarted = await api.do_login();
        if (loginStarted) {
            appendLog(`[SYSTEM] 登录浏览器已启动，请在弹出的浏览器中完成登录`, "text-sky-400");
            await startLoginPolling();
        } else {
            setLoginLoading(false);
            await showModal('登录未启动', '登录流程未能启动，请重试。', true, false);
        }
    } catch (e) {
        console.error(e);
        setLoginLoading(false);
        appendLog(`[GUI错误] 登录入口尚未就绪: ${e}`, "text-rose-500");
    }
}

if (el.btnLogin) el.btnLogin.addEventListener('click', handleLoginClick);
if (el.btnAuthLogin) el.btnAuthLogin.addEventListener('click', handleLoginClick);

if (el.btnOpenSource) el.btnOpenSource.addEventListener('click', async () => {
    appendLog('[DEBUG] 点击了 打开草稿来源目录', 'text-sky-400');
    if (isPublishing) return;
    if (!el.sourceDirInput.value) {
        showModal('核心路径校验提示', '尚未设置发文前的数据源目录！\n请先点击上方的“更改”选择含有TXT章节集的文件夹。', true, false);
        return;
    }
    try {
        const api = await getApiOrThrow({ wait: false });
        await api.open_source_folder();
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 打开草稿目录失败: ${e}`, "text-rose-500");
    }
});

if (el.btnChooseSourceDir) el.btnChooseSourceDir.addEventListener('click', async () => {
    appendLog('[DEBUG] 点击了 选择草稿目录', 'text-sky-400');
    if (isPublishing) return;
    try {
        const api = await getApiOrThrow({ wait: false });
        const dir = await api.choose_dir('source_dir');
        if (dir) {
            el.sourceDirInput.value = dir;
            el.sourceDirInput.classList.remove('text-slate-600', 'placeholder-slate-400');
            el.sourceDirInput.classList.add('text-accent-600');
            appendLog(`[SYSTEM] 草稿核心库挂载成功: ${dir}`, "text-emerald-400");
            refreshBooks();
        }
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 选择草稿目录失败: ${e}`, "text-rose-500");
    }
});

if (el.btnStart) el.btnStart.addEventListener('click', async () => {
    appendLog('[DEBUG] 点击了 上传选定章节', 'text-sky-400');
    if (isPublishing) return;
    
    if (!el.sourceDirInput.value) {
        showModal('应用预检未通过', '草稿来源目录不能为空。\n请先在页面顶部选择草稿目录。', true, false);
        return;
    }

    if (currentBooks.length === 0) {
        showModal('任务栈中止', '在指定的目录下没有找到任何可发布章节文件。\n\n请确保发文草稿源目录或其子目录中包含标准的 TXT / Markdown 章节文件（名称建议为“第X章...”），然后再点击“刷新”。', true, false);
        return;
    }
    
    const book = getCurrentLocalBook();
    const remoteBookName = el.remoteBookSelect?.value?.trim();
    const remoteVolumeName = el.remoteVolumeSelect?.value?.trim() || null;
    const localVolumeName = getSelectedLocalVolumeName();
    const selectedRows = currentChapterDiffRows.filter(row => selectedChapterRowIds.has(row.row_id));
    const selectedFilenames = selectedRows.map(row => row.filename).filter(Boolean);

    if (!remoteBookName) {
        showModal('目标缺失', '请先同步后台书库，并明确选择要发布到哪一本后台小说。', true, false);
        return;
    }
    if (selectedFilenames.length === 0) {
        showModal('未选择章节', '请先在章节对比表中勾选要上传的章节。', true, false);
        return;
    }
    
    let pCount = null;
    let vNum = null;

    const confirmationMessage = buildPublishConfirmationMessage(
        book?.name || '',
        remoteBookName,
        remoteVolumeName,
        currentChapterMatchSummary
    ) + `\n\n本次实际勾选上传：${selectedFilenames.length} 章`;
    const confirmed = await showModal('发布前确认', confirmationMessage, false, true);
    if (!confirmed) {
        return;
    }
    
    toggleUI(true);
    
    try {
        const api = await getApiOrThrow({ wait: false });
        await api.start_publish(book?.name || '', remoteBookName, pCount, vNum, remoteVolumeName, selectedFilenames, localVolumeName);
        markRowsUploaded(selectedRows.map(row => row.row_id));
    } catch (e) {
        console.error(e);
        appendLog(`[GUI错误] 启动发布失败: ${e}`, "text-rose-500");
    } finally {
        toggleUI(false);
        updateTargetSummary();
    }
});

if (el.remoteBookSelect) el.remoteBookSelect.addEventListener('change', () => {
    refreshRemoteVolumeSelect();
    refreshChapterMatchSummary();
    updateTargetSummary();
});

if (el.localBookSelect) el.localBookSelect.addEventListener('change', () => {
    selectedLocalBookName = el.localBookSelect.value;
    refreshLocalVolumes().then(() => {
        refreshRemoteBookSelect();
        refreshRemoteVolumeSelect();
        refreshChapterMatchSummary();
        updateTargetSummary();
    });
});
