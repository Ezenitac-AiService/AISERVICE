// vLLM Control Center & AI Playground SPA JavaScript Controller (037-dashboard-enhancement)

document.addEventListener('DOMContentLoaded', () => {
    // --- Global Application State ---
    const state = {
        adminSecret: sessionStorage.getItem('adminSecret') || '',
        activeTab: 'monitoring',
        currentCapabilities: null,
        chart: null,
        sseSource: null,
        metricsHistory: {
            timestamps: [],
            vramUsed: [],
            gpuUtil: []
        }
    };

    // --- DOM Elements ---
    const elements = {
        tabs: document.querySelectorAll('.tab-btn'),
        tabPanels: document.querySelectorAll('.tab-panel'),
        statusBadge: document.getElementById('status-badge'),
        platformProfileSub: document.getElementById('platform-profile-subtitle'),
        // Stat Cards
        statModel: document.getElementById('stat-model'),
        statProfile: document.getElementById('stat-profile'),
        statVram: document.getElementById('stat-vram'),
        vramFill: document.getElementById('vram-fill'),
        vramWarningBadge: document.getElementById('vram-warning-badge'),
        statCtx: document.getElementById('stat-ctx'),
        statCtxLimit: document.getElementById('stat-ctx-limit'),
        statSpeed: document.getElementById('stat-speed'),
        statTtft: document.getElementById('stat-ttft'),
        // Control Tab
        presetsGrid: document.getElementById('presets-grid'),
        modelSelect: document.getElementById('model-select'),
        ctxSlider: document.getElementById('ctx-slider'),
        ctxInput: document.getElementById('ctx-input'),
        oomWarning: document.getElementById('oom-warning'),
        manualForm: document.getElementById('manual-form'),
        unloadBtn: document.getElementById('unload-btn'),
        // Admin Auth Modal
        adminLoginBtn: document.getElementById('admin-login-btn'),
        adminModal: document.getElementById('admin-modal'),
        adminSecretInput: document.getElementById('admin-secret-input'),
        modalLoginBtn: document.getElementById('modal-login-btn'),
        modalCloseBtn: document.getElementById('modal-close-btn'),
        pgModelSelect: document.getElementById('pg-model-select'),
        pgApiKey: document.getElementById('pg-api-key'),
        pgApiKeyBadge: document.getElementById('pg-api-key-badge'),
        pgSystemPrompt: document.getElementById('pg-system-prompt'),
        pgTemp: document.getElementById('pg-temp'),
        pgTempVal: document.getElementById('pg-temp-val'),
        pgTopP: document.getElementById('pg-top-p'),
        pgTopPVal: document.getElementById('pg-top-p-val'),
        pgMaxTokens: document.getElementById('pg-max-tokens'),
        pgPromptInput: document.getElementById('pg-prompt-input'),
        pgSubmitBtn: document.getElementById('pg-submit-btn'),
        pgActiveModel: document.getElementById('pg-active-model'),
        pgOutputText: document.getElementById('pg-output-text'),
        pgMetricTtft: document.getElementById('pg-metric-ttft'),
        pgMetricSpeed: document.getElementById('pg-metric-speed'),
        pgMetricLatency: document.getElementById('pg-metric-latency'),
        pgMetricTokens: document.getElementById('pg-metric-tokens'),
        codeExportBtn: document.getElementById('code-export-btn'),
        // Code Modal
        codeModal: document.getElementById('code-modal'),
        codeSnippet: document.getElementById('code-snippet'),
        copyCodeBtn: document.getElementById('copy-code-btn'),
        closeCodeBtn: document.getElementById('close-code-btn'),
        codeTabs: document.querySelectorAll('.code-tab'),
        // Audit
        auditListBody: document.getElementById('audit-list-body'),
        refreshAuditBtn: document.getElementById('refresh-audit-btn'),
        // Loading Overlay
        loadingOverlay: document.getElementById('loading-overlay')
    };

    // --- 1. SPA Navigation Tab Switcher ---
    elements.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.getAttribute('data-tab');
            elements.tabs.forEach(t => t.classList.remove('active'));
            elements.tabPanels.forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${target}`).classList.add('active');
            state.activeTab = target;

            if (target === 'audit') {
                loadAuditLogs();
            }
            if (target === 'control' || target === 'playground') {
                loadCapabilities();
            }
        });
    });

    // --- 2. Chart.js Time-Series Canvas Graph Initialization (FR-001) ---
    function initMetricsChart() {
        if (typeof Chart === 'undefined') {
            console.warn('[Dashboard] Chart.js CDN not loaded or offline. Graph rendering will fallback.');
            return;
        }
        try {
            const ctx = document.getElementById('metricsChart').getContext('2d');
            state.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: state.metricsHistory.timestamps,
                    datasets: [
                        {
                            label: 'VRAM Used (MB)',
                            data: state.metricsHistory.vramUsed,
                            borderColor: '#06b6d4',
                            backgroundColor: 'rgba(6, 182, 212, 0.15)',
                            fill: true,
                            tension: 0.3,
                            yAxisID: 'y'
                        },
                        {
                            label: 'GPU Utilization (%)',
                            data: state.metricsHistory.gpuUtil,
                            borderColor: '#3b82f6',
                            backgroundColor: 'transparent',
                            borderDash: [5, 5],
                            tension: 0.3,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    scales: {
                        x: {
                            ticks: { color: '#9ca3af', maxTicksLimit: 10 },
                            grid: { color: 'rgba(255, 255, 255, 0.05)' }
                        },
                        y: {
                            position: 'left',
                            ticks: { color: '#06b6d4' },
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            title: { display: true, text: 'VRAM (MB)', color: '#06b6d4' }
                        },
                        y1: {
                            position: 'right',
                            min: 0,
                            max: 100,
                            ticks: { color: '#3b82f6' },
                            grid: { drawOnChartArea: false },
                            title: { display: true, text: 'GPU %', color: '#3b82f6' }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: '#f3f4f6' } }
                    }
                }
            });
        } catch (err) {
            console.error('[Dashboard] Error initializing Chart.js:', err);
        }
    }


    // --- 3. Real-Time SSE Resource Metric Listener (FR-001, FR-003) ---
    function setupMetricSSE() {
        if (state.sseSource) {
            state.sseSource.close();
        }

        try {
            state.sseSource = new EventSource('/dashboard/api/stream');
            state.sseSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateDashboardState(data);
            };
            state.sseSource.onerror = () => {
                elements.statusBadge.textContent = 'Polling Metric...';
                elements.statusBadge.className = 'status-badge loading';
                // Fallback polling
                fetchStatusFallback();
            };
        } catch (e) {
            fetchStatusFallback();
        }
    }

    async function fetchStatusFallback() {
        try {
            const res = await fetch('/dashboard/api/status');
            if (res.ok) {
                const data = await res.json();
                updateDashboardState(data);
            }
        } catch (e) {
            elements.statusBadge.textContent = 'Disconnected';
            elements.statusBadge.className = 'status-badge error';
        }
    }

    function updateDashboardState(data) {
        // Status Badge
        const statusStr = (data.state || 'UNKNOWN').toUpperCase();
        elements.statusBadge.textContent = statusStr;
        if (statusStr === 'READY') {
            elements.statusBadge.className = 'status-badge ready';
        } else if (statusStr === 'LOADING' || statusStr === 'DOWNLOADING') {
            elements.statusBadge.className = 'status-badge loading';
        } else {
            elements.statusBadge.className = 'status-badge error';
        }

        // Active Model & Context
        const modelName = data.current_model || 'Unloaded';
        elements.statModel.textContent = modelName;
        elements.pgActiveModel.textContent = `Model: ${modelName}`;
        elements.statCtx.textContent = data.current_n_ctx ? `${data.current_n_ctx}` : '--';

        // VRAM Calculations & 90% Warning Badge (FR-003)
        const vramTotal = data.vram_total || 8192;
        const vramUsed = data.vram_used || 0;
        const vramPct = (vramUsed / vramTotal) * 100;

        elements.statVram.textContent = `${vramUsed} / ${vramTotal} MB (${vramPct.toFixed(1)}%)`;
        elements.vramFill.style.width = `${Math.min(vramPct, 100)}%`;

        if (vramPct >= 90) {
            elements.vramWarningBadge.classList.remove('hidden');
        } else {
            elements.vramWarningBadge.classList.add('hidden');
        }

        // Push to Chart
        const timeStr = new Date().toLocaleTimeString();
        if (state.metricsHistory.timestamps.length > 20) {
            state.metricsHistory.timestamps.shift();
            state.metricsHistory.vramUsed.shift();
            state.metricsHistory.gpuUtil.shift();
        }
        state.metricsHistory.timestamps.push(timeStr);
        state.metricsHistory.vramUsed.push(vramUsed);
        state.metricsHistory.gpuUtil.push(Math.round(vramPct * 0.9)); // GPU estimate

        if (state.chart) {
            state.chart.update();
        }
    }

    // --- 4. Dynamic Platform Capabilities & Model Preset Loader (FR-002) ---
    async function loadCapabilities() {
        try {
            const res = await fetch('/dashboard/api/capabilities');
            if (!res.ok) return;
            const caps = await res.json();
            state.currentCapabilities = caps;

            elements.platformProfileSub.textContent = `Platform Profile: ${caps.platform_profile} (${caps.vram_total}MB VRAM)`;
            elements.statProfile.textContent = `Profile: ${caps.platform_profile}`;

            // Populate Model Dropdown (Control Tab)
            elements.modelSelect.innerHTML = '';
            caps.available_models.forEach(model => {
                const opt = document.createElement('option');
                opt.value = model;
                opt.textContent = model;
                if (model === caps.current_model) opt.selected = true;
                elements.modelSelect.appendChild(opt);
            });

            // Populate Playground Model Dropdown (#pg-model-select)
            if (elements.pgModelSelect) {
                elements.pgModelSelect.innerHTML = '';
                caps.available_models.forEach(model => {
                    const opt = document.createElement('option');
                    opt.value = model;
                    opt.textContent = model;
                    if (model === caps.current_model) opt.selected = true;
                    elements.pgModelSelect.appendChild(opt);
                });
                if (caps.current_model && elements.pgActiveModel) {
                    elements.pgActiveModel.textContent = `Model: ${caps.current_model}`;
                }
            }

            if (elements.pgApiKeyBadge && caps.api_key_enabled !== undefined) {
                elements.pgApiKeyBadge.textContent = caps.api_key_enabled ? '(Required in Security Mode)' : '(Optional)';
                elements.pgApiKeyBadge.style.color = caps.api_key_enabled ? '#f87171' : '#9ca3af';
            }

            // Populate Presets Grid
            elements.presetsGrid.innerHTML = '';
            caps.available_models.forEach(model => {
                const card = document.createElement('div');
                card.className = 'preset-card';
                card.innerHTML = `
                    <h4>🤖 ${model}</h4>
                    <p>Context Scaling Preset: 4096 / 8192</p>
                `;
                card.addEventListener('click', () => {
                    elements.modelSelect.value = model;
                    applyPreset(model, 4096);
                });
                elements.presetsGrid.appendChild(card);
            });
        } catch (e) {
            console.error('Failed to load capabilities:', e);
        }
    }

    // Context Slider Sync
    elements.ctxSlider.addEventListener('input', (e) => {
        elements.ctxInput.value = e.target.value;
        checkOomWarning();
    });
    elements.ctxInput.addEventListener('input', (e) => {
        elements.ctxSlider.value = e.target.value;
        checkOomWarning();
    });

    function checkOomWarning() {
        const val = parseInt(elements.ctxInput.value, 10);
        if (val > 8192) {
            elements.oomWarning.classList.remove('hidden');
        } else {
            elements.oomWarning.classList.add('hidden');
        }
    }

    // --- 5. Admin Authentication & State-Mutating Actions (FR-006) ---
    elements.adminLoginBtn?.addEventListener('click', () => {
        elements.adminModal?.classList.remove('hidden');
    });
    elements.modalCloseBtn?.addEventListener('click', () => {
        elements.adminModal?.classList.add('hidden');
    });
    elements.modalLoginBtn?.addEventListener('click', () => {
        const secret = elements.adminSecretInput?.value?.trim();
        if (secret) {
            state.adminSecret = secret;
            sessionStorage.setItem('adminSecret', secret);
            elements.adminModal?.classList.add('hidden');
            if (elements.adminLoginBtn) {
                elements.adminLoginBtn.textContent = '✅ Authenticated';
                elements.adminLoginBtn.className = 'secondary-btn ready';
            }
        }
    });

    async function applyPreset(modelId, nCtx) {
        if (!state.adminSecret) {
            elements.adminModal?.classList.remove('hidden');
            return;
        }

        elements.loadingOverlay?.classList.remove('hidden');
        try {
            const res = await fetch('/dashboard/api/apply', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Secret': state.adminSecret
                },
                body: JSON.stringify({ model_id: modelId, n_ctx: nCtx })
            });

            if (res.status === 401) {
                alert('401 Unauthorized: Invalid Admin Secret password!');
                state.adminSecret = '';
                sessionStorage.removeItem('adminSecret');
                elements.adminModal?.classList.remove('hidden');
            } else if (res.ok) {
                const data = await res.json();
                console.log('Apply success:', data);
            }
        } catch (e) {
            alert('Failed to apply configuration: ' + e);
        } finally {
            setTimeout(() => elements.loadingOverlay?.classList.add('hidden'), 1000);
        }
    }

    elements.manualForm?.addEventListener('submit', (e) => {
        e.preventDefault();
        applyPreset(elements.modelSelect?.value, parseInt(elements.ctxInput?.value, 10));
    });

    elements.unloadBtn?.addEventListener('click', async () => {
        if (!state.adminSecret) {
            elements.adminModal?.classList.remove('hidden');
            return;
        }
        elements.loadingOverlay?.classList.remove('hidden');
        try {
            await fetch('/dashboard/api/unload', {
                method: 'POST',
                headers: { 'X-Admin-Secret': state.adminSecret }
            });
        } finally {
            setTimeout(() => elements.loadingOverlay?.classList.add('hidden'), 1000);
        }
    });

    // --- 6. AI Playground & Real-time Benchmark (FR-007, FR-008, FR-009) ---
    elements.pgTemp?.addEventListener('input', (e) => {
        if (elements.pgTempVal) elements.pgTempVal.textContent = e.target.value;
    });
    elements.pgTopP?.addEventListener('input', (e) => {
        if (elements.pgTopPVal) elements.pgTopPVal.textContent = e.target.value;
    });

    const chatThreadContainer = document.getElementById('chat-thread-container');
    const clearChatBtn = document.getElementById('clear-chat-btn');

    if (clearChatBtn && chatThreadContainer) {
        clearChatBtn.addEventListener('click', () => {
            chatThreadContainer.innerHTML = `
                <div class="chat-bubble assistant-bubble" style="background: rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%;">
                    <strong>🤖 Assistant:</strong> Chat history cleared. How can I help you next?
                </div>
            `;
        });
    }

    // --- 048-think-tag-ui-markdown: State & Helper Functions ---
    let currentThinkMode = 'collapse'; // 'collapse' | 'show' | 'off'
    let currentSessionId = null;

    function renderMarkdownText(text) {
        if (!text) return '';
        if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            const rawHtml = marked.parse(text);
            return DOMPurify.sanitize(rawHtml);
        }
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
    }

    function renderThinkContainer(thinkingProcess, mode) {
        if (!thinkingProcess || mode === 'off') return '';
        const cleanProcess = thinkingProcess.replace(/</g, "&lt;").replace(/>/g, "&gt;");
        if (mode === 'show') {
            return `<details class="think-accordion" open>
                <summary class="think-summary">🧠 Thinking Process (Visible - Click to toggle)</summary>
                <div class="think-accordion-content">${cleanProcess}</div>
            </details>`;
        } else {
            // mode === 'collapse'
            return `<details class="think-accordion">
                <summary class="think-summary">🧠 Thinking Process (Collapsed - Click to expand)</summary>
                <div class="think-accordion-content">${cleanProcess}</div>
            </details>`;
        }
    }

    // 3-Way Toggle Button Group Handler
    const thinkModeBtns = document.querySelectorAll('#think-mode-group .toggle-btn');
    thinkModeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            thinkModeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentThinkMode = btn.getAttribute('data-mode');

            // FR-006: Real-time dynamic mode update for all existing messages in chat thread
            document.querySelectorAll('.chat-bubble.assistant-bubble').forEach(bubble => {
                const thinkContainer = bubble.querySelector('.think-container');
                const thinkingText = bubble.getAttribute('data-thinking');
                if (thinkContainer && thinkingText) {
                    thinkContainer.innerHTML = renderThinkContainer(thinkingText, currentThinkMode);
                }
            });
        });
    });

    // Chat Sessions Management Functions
    async function loadPlaygroundSessions() {
        const container = document.getElementById('session-list-container');
        if (!container) return;
        try {
            const res = await fetch('/dashboard/api/playground/sessions');
            if (res.ok) {
                const sessions = await res.json();
                container.innerHTML = '';
                if (sessions.length === 0) {
                    container.innerHTML = '<div style="font-size:12px; color:var(--text-secondary); padding:8px;">No chat history.</div>';
                    return;
                }
                sessions.forEach(sess => {
                    const item = document.createElement('div');
                    item.className = `session-item ${sess.id === currentSessionId ? 'active' : ''}`;
                    item.setAttribute('data-id', sess.id);
                    item.innerHTML = `
                        <span class="session-title" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:150px;">${sess.title.replace(/</g, "&lt;")}</span>
                        <span class="session-delete-btn" title="Delete Session">🗑️</span>
                    `;
                    item.addEventListener('click', (e) => {
                        if (e.target.classList.contains('session-delete-btn')) {
                            e.stopPropagation();
                            deleteSession(sess.id);
                        } else {
                            switchSession(sess.id);
                        }
                    });
                    container.appendChild(item);
                });
            }
        } catch (e) {
            console.error('Failed loading sessions:', e);
        }
    }

    function startNewChat() {
        currentSessionId = null;
        document.querySelectorAll('#session-list-container .session-item').forEach(i => i.classList.remove('active'));
        const chatThreadContainer = document.getElementById('chat-thread-container');
        if (chatThreadContainer) {
            chatThreadContainer.innerHTML = `
                <div class="chat-bubble assistant-bubble" style="background: rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%;">
                    <strong>🤖 Assistant:</strong> Hello! How can I assist you with LLM inference today?
                </div>
            `;
        }
    }

    async function switchSession(sessionId) {
        currentSessionId = sessionId;
        document.querySelectorAll('#session-list-container .session-item').forEach(i => {
            i.classList.toggle('active', i.getAttribute('data-id') === sessionId);
        });
        const chatThreadContainer = document.getElementById('chat-thread-container');
        try {
            const res = await fetch(`/dashboard/api/playground/sessions/${sessionId}/messages`);
            if (res.ok) {
                const msgs = await res.json();
                chatThreadContainer.innerHTML = '';
                msgs.forEach(m => {
                    if (m.role === 'user') {
                        const uBubble = document.createElement('div');
                        uBubble.className = 'chat-bubble user-bubble';
                        uBubble.style.cssText = 'background: rgba(59, 130, 246, 0.25); border: 1px solid rgba(59, 130, 246, 0.4); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%; margin-left: auto; text-align: right;';
                        uBubble.innerHTML = `<strong>👤 User:</strong> ${m.content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}`;
                        chatThreadContainer.appendChild(uBubble);
                    } else {
                        const aBubble = document.createElement('div');
                        aBubble.className = 'chat-bubble assistant-bubble';
                        aBubble.style.cssText = 'background: rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%;';
                        if (m.thinking_process) {
                            aBubble.setAttribute('data-thinking', m.thinking_process);
                        }
                        aBubble.innerHTML = `
                            <strong>🤖 Assistant:</strong>
                            <div class="think-container">${renderThinkContainer(m.thinking_process, currentThinkMode)}</div>
                            <div class="assistant-content markdown-body">${renderMarkdownText(m.content)}</div>
                        `;
                        chatThreadContainer.appendChild(aBubble);
                    }
                });
                if (typeof hljs !== 'undefined') hljs.highlightAll();
                chatThreadContainer.scrollTop = chatThreadContainer.scrollHeight;
            }
        } catch (e) {
            console.error('Failed switching session:', e);
        }
    }

    async function deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this conversation?')) return;
        try {
            const res = await fetch(`/dashboard/api/playground/sessions/${sessionId}`, { method: 'DELETE' });
            if (res.ok) {
                if (currentSessionId === sessionId) {
                    startNewChat();
                }
                loadPlaygroundSessions();
            }
        } catch (e) {
            console.error('Failed deleting session:', e);
        }
    }

    if (elements.pgModelSelect) {
        elements.pgModelSelect.addEventListener('change', (e) => {
            if (elements.pgActiveModel) {
                elements.pgActiveModel.textContent = `Model: ${e.target.value}`;
            }
        });
    }

    const newChatBtn = document.getElementById('new-chat-btn');
    if (newChatBtn) newChatBtn.addEventListener('click', startNewChat);

    // Initial session load
    loadPlaygroundSessions();

    // --- 6. Playground Test Handler (Real-Time SSE Streaming) ---
    elements.pgSubmitBtn.addEventListener('click', async () => {
        const prompt = elements.pgPromptInput.value.trim();
        if (!prompt) return;

        const chatThreadContainer = document.getElementById('chat-thread-container');

        // Create new session if none active
        if (!currentSessionId) {
            try {
                const title = prompt.length > 25 ? prompt.substring(0, 25) + '...' : prompt;
                const sRes = await fetch('/dashboard/api/playground/sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: title })
                });
                if (sRes.ok) {
                    const sData = await sRes.json();
                    currentSessionId = sData.id;
                }
            } catch (err) {
                console.error('Failed creating session:', err);
            }
        }

        // Append User Bubble
        const userBubble = document.createElement('div');
        userBubble.className = 'chat-bubble user-bubble';
        userBubble.style.cssText = 'background: rgba(59, 130, 246, 0.25); border: 1px solid rgba(59, 130, 246, 0.4); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%; margin-left: auto; text-align: right;';
        userBubble.innerHTML = `<strong>👤 User:</strong> ${prompt.replace(/</g, "&lt;").replace(/>/g, "&gt;")}`;
        chatThreadContainer.appendChild(userBubble);

        // Append Assistant Bubble Placeholder
        const assistantBubble = document.createElement('div');
        assistantBubble.className = 'chat-bubble assistant-bubble';
        assistantBubble.style.cssText = 'background: rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 12px; margin-bottom: 10px; max-width: 85%;';
        assistantBubble.innerHTML = `
            <strong>🤖 Assistant:</strong>
            <div class="think-container"></div>
            <div class="assistant-content markdown-body">Streaming response...</div>
        `;
        chatThreadContainer.appendChild(assistantBubble);
        chatThreadContainer.scrollTop = chatThreadContainer.scrollHeight;

        elements.pgPromptInput.value = '';
        elements.pgSubmitBtn.disabled = true;

        const thinkContainer = assistantBubble.querySelector('.think-container');
        const contentDiv = assistantBubble.querySelector('.assistant-content');
        contentDiv.innerHTML = '';

        let accumulatedThink = '';
        let accumulatedText = '';
        let thinkDetailsElem = null;
        let thinkContentElem = null;

        const apiKeyVal = elements.pgApiKey ? elements.pgApiKey.value.trim() : '';

        try {
            const res = await fetch('/dashboard/api/playground/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(apiKeyVal ? { 'X-API-Key': apiKeyVal } : {})
                },
                body: JSON.stringify({
                    api_key: apiKeyVal || undefined,
                    model: (elements.pgModelSelect && elements.pgModelSelect.value) || elements.modelSelect.value || 'qwen3.5-4b',
                    system_prompt: elements.pgSystemPrompt.value,
                    prompt: prompt,
                    temperature: parseFloat(elements.pgTemp.value),
                    top_p: parseFloat(elements.pgTopP.value),
                    max_tokens: parseInt(elements.pgMaxTokens.value, 10),
                    session_id: currentSessionId
                })
            });

            if (!res.ok) {
                if (res.status === 401) {
                    contentDiv.innerHTML = '<span style="color: #f87171;">🔑 <strong>401 Unauthorized:</strong> API Key is required because Security Mode is enabled. Please enter a valid API Key in the settings panel.</span>';
                    return;
                }
                contentDiv.textContent = `[HTTP Error ${res.status}] Failed to start stream.`;
                return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            const collapseThinkBlock = () => {
                if (thinkDetailsElem && currentThinkMode === 'collapse') {
                    thinkDetailsElem.removeAttribute('open');
                }
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep last incomplete line

                let currentEventType = 'message';
                for (let line of lines) {
                    line = line.trim();
                    if (!line) continue;

                    if (line.startsWith('event:')) {
                        currentEventType = line.substring(6).trim();
                        if (currentEventType === 'think_end') {
                            collapseThinkBlock();
                        }
                        continue;
                    }

                    if (line.startsWith('data:')) {
                        const dataStr = line.substring(5).trim();
                        if (dataStr === '[DONE]') break;

                        try {
                            const parsed = JSON.parse(dataStr);
                            
                            // 1. Thinking Delta Streaming
                            if (parsed.think) {
                                accumulatedThink += parsed.think;
                                assistantBubble.setAttribute('data-thinking', accumulatedThink);

                                if (currentThinkMode !== 'off') {
                                    if (!thinkDetailsElem) {
                                        thinkContainer.innerHTML = `
                                            <details class="think-accordion" open>
                                                <summary class="think-summary">🧠 Thinking Process (Streaming...)</summary>
                                                <div class="think-accordion-content"></div>
                                            </details>
                                        `;
                                        thinkDetailsElem = thinkContainer.querySelector('.think-accordion');
                                        thinkContentElem = thinkContainer.querySelector('.think-accordion-content');
                                    }
                                    if (thinkContentElem) {
                                        thinkContentElem.textContent = accumulatedThink;
                                    }
                                }
                            }

                            // 2. Text Delta Streaming
                            if (parsed.text) {
                                // Auto-collapse thinking block when answer text starts
                                collapseThinkBlock();

                                accumulatedText += parsed.text;
                                contentDiv.innerHTML = renderMarkdownText(accumulatedText);
                                if (typeof hljs !== 'undefined') hljs.highlightAll();
                            }

                            // 3. Metrics Event
                            if (parsed.ttft_ms !== undefined) {
                                elements.pgMetricTtft.textContent = `${parsed.ttft_ms} ms`;
                                elements.pgMetricSpeed.textContent = `${parsed.token_speed_tok_s} tok/s`;
                                elements.pgMetricLatency.textContent = `${parsed.total_latency_s} s`;
                                elements.pgMetricTokens.textContent = `${parsed.prompt_tokens} in / ${parsed.completion_tokens} out`;

                                elements.statSpeed.textContent = `${parsed.token_speed_tok_s} tok/s`;
                                elements.statTtft.textContent = `TTFT: ${parsed.ttft_ms} ms`;
                            }
                        } catch (e) {
                            // Raw text chunk fallback
                        }
                    }
                }
                chatThreadContainer.scrollTop = chatThreadContainer.scrollHeight;
            }

            // Ensure summary title is updated after completion
            if (thinkDetailsElem) {
                const summaryElem = thinkDetailsElem.querySelector('.think-summary');
                if (summaryElem) {
                    summaryElem.textContent = currentThinkMode === 'show' 
                        ? '🧠 Thinking Process (Visible - Click to toggle)'
                        : '🧠 Thinking Process (Collapsed - Click to expand)';
                }
            }

            loadPlaygroundSessions();

        } catch (e) {
            contentDiv.textContent = `[Stream Error] ${e}`;
        } finally {
            elements.pgSubmitBtn.disabled = false;
            chatThreadContainer.scrollTop = chatThreadContainer.scrollHeight;
        }
    });

    // Code Export Generator
    elements.codeExportBtn.addEventListener('click', () => {
        generateCodeSnippet('curl');
        elements.codeModal.classList.remove('hidden');
    });
    elements.closeCodeBtn.addEventListener('click', () => elements.codeModal.classList.add('hidden'));

    elements.codeTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            elements.codeTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            generateCodeSnippet(tab.getAttribute('data-lang'));
        });
    });

    function generateCodeSnippet(lang) {
        const model = elements.modelSelect.value || 'qwen3.5-4b';
        const prompt = elements.pgPromptInput.value || 'Hello AI';
        const sys = elements.pgSystemPrompt.value || 'You are helpful';

        if (lang === 'curl') {
            elements.codeSnippet.textContent = `curl http://10.0.0.41:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer sk-vllm-key" \\
  -d '{
    "model": "${model}",
    "messages": [
      {"role": "system", "content": "${sys}"},
      {"role": "user", "content": "${prompt}"}
    ],
    "temperature": ${elements.pgTemp.value},
    "top_p": ${elements.pgTopP.value}
  }'`;
        } else {
            elements.codeSnippet.textContent = `from openai import OpenAI

client = OpenAI(
    base_url="http://10.0.0.41:8000/v1",
    api_key="sk-vllm-key"
)

response = client.chat.completions.create(
    model="${model}",
    messages=[
        {"role": "system", "content": "${sys}"},
        {"role": "user", "content": "${prompt}"}
    ],
    temperature=${elements.pgTemp.value},
    top_p=${elements.pgTopP.value}
)

print(response.choices[0].message.content)`;
        }
    }

    elements.copyCodeBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(elements.codeSnippet.textContent);
        elements.copyCodeBtn.textContent = '✅ Copied!';
        setTimeout(() => elements.copyCodeBtn.textContent = '📋 Copy Code', 2000);
    });

    // --- 7. Audit Log Timeline Loader & Payload Inspector (FR-004, 044-llm-response-payload-viewer) ---
    async function loadAuditLogs() {
        try {
            const res = await fetch('/dashboard/api/audit');
            if (!res.ok) return;
            const data = await res.json();

            elements.auditListBody.innerHTML = '';
            if (data.logs.length === 0) {
                elements.auditListBody.innerHTML = '<tr><td colspan="6" class="table-placeholder">No client access logs recorded yet.</td></tr>';
                return;
            }

            data.logs.forEach((log, index) => {
                const logId = index + 1;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>#${logId}</td>
                    <td>${log.timestamp}</td>
                    <td><code>${log.client_ip}</code></td>
                    <td><code>${log.endpoint}</code></td>
                    <td><span class="badge ${log.status_code < 400 ? 'badge-info' : 'warning-badge'}">${log.status_code}</span></td>
                    <td>
                        <button class="primary-btn view-payload-btn" data-id="${logId}" style="padding: 2px 8px; font-size: 0.8em;">👁️ View Payload</button>
                    </td>
                `;
                elements.auditListBody.appendChild(tr);
            });

            // Bind Payload Inspector Modal
            document.querySelectorAll('.view-payload-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.target.getAttribute('data-id');
                    const payloadModal = document.getElementById('payload-modal');
                    const promptView = document.getElementById('payload-prompt-view');
                    const respView = document.getElementById('payload-response-view');
                    
                    promptView.textContent = 'Loading prompt payload...';
                    respView.textContent = 'Loading LLM response completion payload...';
                    payloadModal.classList.remove('hidden');

                    try {
                        const pRes = await fetch(`/dashboard/api/audit/payload/${id}`);
                        if (pRes.ok) {
                            const pData = await pRes.json();
                            const p = pData.payload;
                            promptView.textContent = p.prompt_text || '(No prompt text recorded)';
                            respView.textContent = p.completion_text || '(No completion text recorded)';
                        } else {
                            promptView.textContent = 'Payload log entry not found in metrics DB.';
                            respView.textContent = 'N/A';
                        }
                    } catch (err) {
                        promptView.textContent = `Failed loading payload: ${err}`;
                        respView.textContent = 'N/A';
                    }
                });
            });
        } catch (e) {
            elements.auditListBody.innerHTML = '<tr><td colspan="6" class="table-placeholder">Error loading audit logs.</td></tr>';
        }
    }

    const closePayloadModalBtn = document.getElementById('close-payload-modal-btn');
    if (closePayloadModalBtn) {
        closePayloadModalBtn.addEventListener('click', () => {
            document.getElementById('payload-modal').classList.add('hidden');
        });
    }

    elements.refreshAuditBtn.addEventListener('click', loadAuditLogs);

    // --- Feature 043: API Security & Metrics Handlers ---
    async function loadKeyMetrics() {
        const apiKeyBody = document.getElementById('apikey-list-body');
        const top5Container = document.getElementById('top5-ranking-container');
        const toggleText = document.getElementById('toggle-status-text');
        if (!apiKeyBody) return;

        try {
            const res = await fetch('/dashboard/api/keys/metrics');
            if (res.ok) {
                const data = await res.json();
                
                // Render Top 5 Card
                if (data.top_5 && data.top_5.length > 0) {
                    top5Container.innerHTML = data.top_5.map((item, idx) => `
                        <div style="display: inline-block; background: rgba(255,255,255,0.05); padding: 8px 12px; margin: 4px; border-radius: 6px;">
                            <strong>#${idx + 1} ${item.api_key.substring(0, 10)}...</strong>
                            <div style="font-size: 0.85em; color: #a0aec0;">Tokens: ${item.prompt_tokens + item.completion_tokens} | Est. Cost: $${item.estimated_cost_usd}</div>
                        </div>
                    `).join('');
                } else {
                    top5Container.innerHTML = '<p class="table-placeholder">No active key usage metrics recorded yet.</p>';
                }

                // Render Key Table
                if (data.metrics && data.metrics.length > 0) {
                    apiKeyBody.innerHTML = '';
                    data.metrics.forEach(m => {
                        const tr = document.createElement('tr');
                        const isAnomaly = m.error_count > 5 || (m.prompt_tokens + m.completion_tokens) > 50000;
                        tr.innerHTML = `
                            <td>Client-App</td>
                            <td><code>${m.api_key.substring(0, 8)}****</code></td>
                            <td>${m.request_count}</td>
                            <td>${m.error_count} ${isAnomaly ? '<span title="High Error/Traffic Anomaly">⚠️</span>' : ''}</td>
                            <td>${m.prompt_tokens}</td>
                            <td>${m.completion_tokens}</td>
                            <td>$${m.estimated_cost_usd}</td>
                            <td>
                                <button class="danger-btn revoke-key-btn" data-key="${m.api_key}" style="padding: 2px 8px; font-size: 0.8em;">Revoke</button>
                            </td>
                        `;
                        apiKeyBody.appendChild(tr);
                    });

                    // Attach revoke handlers
                    document.querySelectorAll('.revoke-key-btn').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            const keyToRevoke = e.target.getAttribute('data-key');
                            const adminSecret = prompt('Enter Admin Secret to revoke key:');
                            if (!adminSecret) return;
                            const revRes = await fetch('/dashboard/api/keys/revoke', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                    'X-Admin-Secret': adminSecret
                                },
                                body: JSON.stringify({ key: keyToRevoke })
                            });
                            if (revRes.ok) {
                                alert('API key revoked successfully.');
                                loadKeyMetrics();
                            } else {
                                alert('Failed to revoke API key.');
                            }
                        });
                    });
                } else {
                    apiKeyBody.innerHTML = '<tr><td colspan="8" class="table-placeholder">No key metrics recorded yet.</td></tr>';
                }
            }
        } catch (e) {
            console.error('Failed loading key metrics:', e);
        }
    }

    const toggleSecurityBtn = document.getElementById('toggle-security-btn');
    if (toggleSecurityBtn) {
        toggleSecurityBtn.addEventListener('click', async () => {
            const adminSecret = prompt('Enter Admin Secret to toggle Security Mode:');
            if (!adminSecret) return;
            const currentState = document.getElementById('toggle-status-text').textContent.includes('ENABLED');
            const targetState = !currentState;

            const res = await fetch('/dashboard/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Secret': adminSecret
                },
                body: JSON.stringify({ api_key_enabled: targetState })
            });
            if (res.ok) {
                const data = await res.json();
                alert(data.message);
                document.getElementById('toggle-status-text').textContent = `Current Mode: ${targetState ? 'ENABLED (API Key Required)' : 'DISABLED (Public Access)'}`;
            } else {
                alert('Unauthorized: Invalid Admin Secret.');
            }
        });
    }

    const exportCsvBtn = document.getElementById('export-csv-btn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', () => {
            window.location.href = '/dashboard/api/keys/export/csv';
        });
    }

    // --- Initial Bootstrapping ---
    initMetricsChart();
    setupMetricSSE();
    loadCapabilities();
    loadKeyMetrics();
});
