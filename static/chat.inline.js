        // ---------------------------------------------------------------------------
        // State
        // ---------------------------------------------------------------------------
        const API_BASE = '/api';
        let sessionId = localStorage.getItem('rag_session_id') || null;
        let isLoading = false;
        let chatStreamingEnabled = false;

        // ---------------------------------------------------------------------------
        // DOM elements
        // ---------------------------------------------------------------------------
        const chatContainer = document.getElementById('chatContainer');
        const chatMessages = document.getElementById('chatMessages');
        const chatForm = document.getElementById('chatForm');
        const questionInput = document.getElementById('questionInput');
        const sendBtn = document.getElementById('sendBtn');
        const typingIndicator = document.getElementById('typingIndicator');
        const welcomeBlock = document.getElementById('welcomeBlock');
        const sessionList = document.getElementById('sessionList');
        const sidebar = document.getElementById('sidebar');
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebarCollapseToggle = document.getElementById('sidebarCollapseToggle');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const sourcePanel = document.getElementById('sourcePanel');
        const sourcePanelOverlay = document.getElementById('sourcePanelOverlay');
        const sourcePanelTitle = document.getElementById('sourcePanelTitle');
        const sourcePanelMeta = document.getElementById('sourcePanelMeta');
        const sourcePanelContent = document.getElementById('sourcePanelContent');
        const sourcePanelClose = document.getElementById('sourcePanelClose');
        const onboardingPanel = document.getElementById('onboardingPanel');
        const onboardingClose = document.getElementById('onboardingClose');
        const themeToggle = document.getElementById('themeToggle');
        const themeIcon = document.getElementById('themeIcon');
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        const newSessionBtn = document.getElementById('newSessionBtn');
        const uploadBtn = document.getElementById('uploadBtn');
        const uploadOverlay = document.getElementById('uploadOverlay');
        const uploadDropzone = document.getElementById('uploadDropzone');
        const fileInput = document.getElementById('fileInput');
        const uploadClose = document.getElementById('uploadClose');
        const uploadStatus = document.getElementById('uploadStatus');
        const uploadProgress = document.getElementById('uploadProgress');
        const uploadProgressBar = document.getElementById('uploadProgressBar');
        const uploadProgressValue = document.getElementById('uploadProgressValue');
        const dragOverlay = document.getElementById('dragOverlay');
        const escalateBtn = document.getElementById('escalateBtn');
        const escalateModal = document.getElementById('escalateModal');
        const escalateConfirm = document.getElementById('escalateConfirm');
        const escalateCancel = document.getElementById('escalateCancel');
        const appToast = document.getElementById('appToast');
        let activeSourcePanelTrigger = null;
        let activeModalTrigger = null;
        let toastTimer = null;

        function getErrorMessage(error, context) {
            if (error && error.message && error.message.includes('Failed to fetch')) {
                return {
                    text: 'Сервер недоступен. Проверьте подключение к интернету.',
                    actions: ['retry', 'escalate'],
                };
            }
            if (error && error.status === 429) {
                return {
                    text: 'Слишком много запросов. Подождите минуту и попробуйте снова.',
                    actions: ['retry'],
                };
            }
            if (error && error.status === 503) {
                return {
                    text: 'Сервис временно недоступен. Ollama может перезагружаться.',
                    actions: ['retry', 'escalate'],
                };
            }
            if (context === 'escalate') {
                return {
                    text: 'Не удалось передать запрос оператору. Попробуйте позже или повторите запрос.',
                    actions: ['retry', 'escalate'],
                };
            }
            if (context === 'stream' || (error && error.context === 'stream')) {
                return {
                    text: 'Потоковая передача прервана. Попробуйте отправить вопрос заново.',
                    actions: ['retry'],
                };
            }
            return {
                text: 'Произошла ошибка: ' + ((error && error.message) || error || 'неизвестная ошибка'),
                actions: ['retry', 'escalate'],
            };
        }

        // ---------------------------------------------------------------------------
        // Theme
        // ---------------------------------------------------------------------------
        const savedTheme = localStorage.getItem('rag_theme') || 'light';
        if (savedTheme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
        updateThemeIcon();

        themeToggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('rag_theme', next);
            updateThemeIcon();
        });

        function updateThemeIcon() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            themeIcon.innerHTML = isDark
                ? '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
                : '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
        }

        function hideCitationTooltip() {
            const tooltip = document.getElementById('citationTooltip');
            if (tooltip) {
                tooltip.classList.remove('visible');
            }
        }

        function closeSourcePanel() {
            if (!sourcePanel || !sourcePanelOverlay) return;
            sourcePanel.classList.remove('open');
            sourcePanel.setAttribute('aria-hidden', 'true');
            sourcePanel.setAttribute('inert', '');
            sourcePanelOverlay.classList.remove('active');
            sourcePanelOverlay.hidden = true;
            if (sourcePanelClose) {
                sourcePanelClose.setAttribute('tabindex', '-1');
            }
            if (activeSourcePanelTrigger) {
                activeSourcePanelTrigger.focus();
                activeSourcePanelTrigger = null;
            }
        }

        function openSourcePanel(citation, source, trigger) {
            if (!sourcePanel || !sourcePanelOverlay || !sourcePanelTitle || !sourcePanelMeta || !sourcePanelContent) return;
            activeSourcePanelTrigger = trigger || null;
            sourcePanelTitle.textContent = citation.title || (source && source.source) || 'Источник';
            sourcePanelMeta.textContent = 'Цитата [' + citation.index + ']' + (citation.doc_id ? ' • ' + citation.doc_id : '');
            sourcePanelContent.textContent = (source && source.page_content) || citation.excerpt || 'Нет содержимого источника.';
            sourcePanelOverlay.hidden = false;
            sourcePanelOverlay.classList.add('active');
            sourcePanel.classList.add('open');
            sourcePanel.removeAttribute('inert');
            sourcePanel.setAttribute('aria-hidden', 'false');
            hideCitationTooltip();
            if (sourcePanelClose) {
                sourcePanelClose.removeAttribute('tabindex');
                sourcePanelClose.focus();
            }
        }

        function showToast(message) {
            if (!appToast) return;
            appToast.textContent = message;
            appToast.hidden = false;
            appToast.classList.add('visible');
            if (toastTimer) {
                clearTimeout(toastTimer);
            }
            toastTimer = setTimeout(function() {
                appToast.classList.remove('visible');
                appToast.hidden = true;
            }, 2600);
        }

        function setUploadProgress(value) {
            if (!uploadProgress || !uploadProgressBar || !uploadProgressValue) return;
            const safeValue = Math.max(0, Math.min(100, Math.round(value)));
            uploadProgress.hidden = false;
            uploadProgressBar.value = safeValue;
            uploadProgressValue.textContent = safeValue + '%';
        }

        function dismissOnboarding() {
            if (!onboardingPanel) return;
            localStorage.setItem('onboarding_done', '1');
            onboardingPanel.hidden = true;
            onboardingPanel.classList.remove('visible');
        }

        function maybeShowOnboarding() {
            if (!onboardingPanel) return;
            const hasMessages = chatMessages.querySelectorAll('.message').length > 0;
            const shouldShow = !localStorage.getItem('onboarding_done') && !sessionId && !hasMessages;
            onboardingPanel.hidden = !shouldShow;
            onboardingPanel.classList.toggle('visible', shouldShow);
        }

        const sidebarMobileMQ = window.matchMedia('(max-width: 768px)');

        function setSidebarOpen(isOpen) {
            if (!sidebar || !sidebarOverlay || !sidebarToggle) return;
            sidebar.classList.toggle('open', isOpen);
            sidebarOverlay.classList.toggle('active', isOpen);
            sidebarToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            document.body.style.overflow = isOpen ? 'hidden' : '';
        }

        function handleSidebarMQ(e) {
            if (!sidebar || !sidebarToggle) return;
            const isMobile = e.matches;
            sidebarToggle.style.display = isMobile ? 'flex' : 'none';
            if (isMobile) {
                sidebar.classList.remove('collapsed');
                sidebarToggle.setAttribute('aria-expanded', sidebar.classList.contains('open') ? 'true' : 'false');
            } else {
                setSidebarOpen(false);
            }
        }

        chatMessages.addEventListener('click', async function(e) {
            const btn = e.target.closest('.btn-feedback');
            if (!btn) return;

            const fbDiv = btn.closest('.msg-feedback');
            if (!fbDiv) return;

            const rating = btn.dataset.rating;
            const traceId = fbDiv.dataset.traceId || '';
            const feedbackSessionId = fbDiv.dataset.sessionId || '';

            fbDiv.querySelectorAll('.btn-feedback').forEach(b => b.classList.add('voted'));

            try {
                await fetch(API_BASE + '/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        trace_id: traceId,
                        session_id: feedbackSessionId,
                        rating: rating,
                    }),
                });
            } catch (err) {
                console.warn('feedback failed:', err);
                fbDiv.querySelectorAll('.btn-feedback').forEach(b => b.classList.remove('voted'));
                showToast('Не удалось отправить отзыв');
            }
        });

        async function loadSessions() {
            try {
                const resp = await fetch(API_BASE + '/sessions');
                if (!resp.ok || !sessionList) return;
                const sessions = await resp.json();
                sessionList.innerHTML = '';
                if (sessions.length === 0) {
                    sessionList.innerHTML = '<div class="session-empty">Нет сессий</div>';
                    return;
                }
                sessions.forEach(function(s) {
                    const item = document.createElement('div');
                    item.className = 'session-item' + (s.session_id === sessionId ? ' active' : '');
                    item.textContent = s.session_id.slice(0, 8) + '... (' + s.message_count + ')';
                    item.title = s.session_id;
                    item.addEventListener('click', function() {
                        switchSession(s.session_id);
                    });
                    sessionList.appendChild(item);
                });
            } catch (err) {
                console.warn('Failed to load sessions:', err);
            }
        }

        async function switchSession(newSessionId) {
            if (newSessionId === sessionId) return;
            sessionId = newSessionId;
            localStorage.setItem('rag_session_id', sessionId);
            if (onboardingPanel) {
                onboardingPanel.hidden = true;
                onboardingPanel.classList.remove('visible');
            }
            chatMessages.innerHTML = '';
            try {
                const resp = await fetch(API_BASE + '/sessions/' + sessionId + '/history');
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.messages && data.messages.length > 0) {
                        data.messages.forEach(function(msg) {
                            addMessage(msg.role === 'user' ? 'user' : 'bot', msg.content);
                        });
                    } else {
                        chatMessages.innerHTML = '<div class="welcome" id="welcomeBlock"><h2>RAG Support Assistant</h2><p>Новая сессия. Задайте ваш вопрос.</p></div>';
                    }
                }
            } catch (err) {
                console.warn('Failed to switch session:', err);
            }
            loadSessions();
            scrollToBottom();
        }

        // ---------------------------------------------------------------------------
        // Health check
        // ---------------------------------------------------------------------------
        async function checkHealth() {
            try {
                const res = await fetch(API_BASE + '/health');
                if (res.ok) {
                    const data = await res.json();
                    chatStreamingEnabled = Boolean(data.features && data.features.streaming_enabled);
                    statusDot.classList.remove('offline');
                    if (data.vector_store_loaded && data.pipeline_available) {
                        statusText.textContent = 'Онлайн';
                    } else if (data.pipeline_available) {
                        statusText.textContent = 'Онлайн (нет векторной БД)';
                    } else {
                        statusText.textContent = 'Онлайн (демо-режим)';
                    }
                } else {
                    statusDot.classList.add('offline');
                    statusText.textContent = 'Ошибка сервера';
                }
            } catch (e) {
                statusDot.classList.add('offline');
                statusText.textContent = 'Нет соединения';
            }
        }
        checkHealth();
        setInterval(checkHealth, 30000);

        // ---------------------------------------------------------------------------
        // Auto-resize textarea
        // ---------------------------------------------------------------------------
        questionInput.addEventListener('input', () => {
            questionInput.style.height = 'auto';
            questionInput.style.height = Math.min(questionInput.scrollHeight, 120) + 'px';
        });

        // ---------------------------------------------------------------------------
        // Send message
        // ---------------------------------------------------------------------------
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            sendMessage();
        });
        questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        if (onboardingClose) {
            onboardingClose.addEventListener('click', dismissOnboarding);
        }
        if (onboardingPanel) {
            onboardingPanel.querySelectorAll('[data-sample-question]').forEach(function(button) {
                button.addEventListener('click', function() {
                    questionInput.value = button.getAttribute('data-sample-question') || '';
                    dismissOnboarding();
                    sendMessage();
                });
            });
        }

        escalateBtn.addEventListener('click', function() {
            activeModalTrigger = document.activeElement;
            escalateModal.classList.add('active');
            escalateCancel.focus();
        });

        escalateCancel.addEventListener('click', function() {
            escalateModal.classList.remove('active');
            if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                activeModalTrigger.focus();
                activeModalTrigger = null;
            }
        });

        escalateConfirm.addEventListener('click', async function() {
            escalateModal.classList.remove('active');
            const typedQuestion = questionInput.value.trim();
            const questionToEscalate = typedQuestion || '(пользователь запросил оператора)';
            try {
                const resp = await fetch(API_BASE + '/escalate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId || 'manual-escalation',
                        question: questionToEscalate,
                        reason: 'user_request',
                    }),
                });
                if (!resp.ok) {
                    const httpError = new Error('HTTP ' + resp.status);
                    httpError.status = resp.status;
                    throw httpError;
                }
                const data = await resp.json();
                const currentWelcome = document.getElementById('welcomeBlock');
                if (currentWelcome) currentWelcome.style.display = 'none';
                addMessage('bot', data.message || 'Запрос передан оператору.', { route: 'human' });
            } catch (err) {
                const currentWelcome = document.getElementById('welcomeBlock');
                if (currentWelcome) currentWelcome.style.display = 'none';
                const errInfo = getErrorMessage(err, 'escalate');
                addMessage('bot', errInfo.text, {
                    error: true,
                    actions: typedQuestion ? errInfo.actions : ['escalate'],
                    originalQuestion: typedQuestion,
                });
                console.warn('Escalation error:', err);
            }
        });

        escalateModal.addEventListener('click', function(e) {
            if (e.target === escalateModal) {
                escalateModal.classList.remove('active');
                if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                    activeModalTrigger.focus();
                    activeModalTrigger = null;
                }
            }
        });

        async function sendMessage() {
            const question = questionInput.value.trim();
            if (!question || isLoading) return;
            if (onboardingPanel && !onboardingPanel.hidden) {
                dismissOnboarding();
            }

            // Hide welcome
            const currentWelcome = document.getElementById('welcomeBlock');
            if (currentWelcome) currentWelcome.style.display = 'none';

            // Add user message
            addMessage('user', question);
            questionInput.value = '';
            questionInput.style.height = 'auto';

            // Show typing
            isLoading = true;
            sendBtn.disabled = true;
            typingIndicator.classList.add('active');
            scrollToBottom();
            let streamingMsg = null;
            let streamingBubble = null;

            try {
                const body = { question: question };
                if (sessionId) body.session_id = sessionId;
                const streamEndpoint = chatStreamingEnabled ? '/chat/stream' : '/ask/stream';

                const res = await fetch(API_BASE + streamEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });

                if (!res.ok) {
                    const httpError = new Error('HTTP ' + res.status);
                    httpError.status = res.status;
                    throw httpError;
                }

                if (!res.body) {
                    const streamBodyError = new Error('Поток данных не получен');
                    streamBodyError.context = 'stream';
                    throw streamBodyError;
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let data = null;
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            let event;
                            try {
                                event = JSON.parse(line.slice(6));
                            } catch (err) {
                                console.warn('Operation failed:', err);
                                continue;
                            }
                            if (event.type === 'error') {
                                const streamError = new Error(event.detail || 'Ошибка потоковой передачи');
                                streamError.context = 'stream';
                                throw streamError;
                            }
                            if (event.type === 'token_start') {
                                typingIndicator.classList.remove('active');
                                if (!streamingMsg) {
                                    streamingMsg = document.createElement('div');
                                    streamingMsg.className = 'message bot';

                                    const avatar = document.createElement('div');
                                    avatar.className = 'message-avatar';
                                    avatar.textContent = 'A';

                                    const content = document.createElement('div');
                                    content.className = 'message-content';

                                    streamingBubble = document.createElement('div');
                                    streamingBubble.className = 'message-bubble';
                                    content.appendChild(streamingBubble);

                                    streamingMsg.appendChild(avatar);
                                    streamingMsg.appendChild(content);
                                    chatMessages.appendChild(streamingMsg);
                                    scrollToBottom();
                                }
                                continue;
                            }
                            if (event.type === 'token') {
                                typingIndicator.classList.remove('active');
                                if (!streamingMsg) {
                                    streamingMsg = document.createElement('div');
                                    streamingMsg.className = 'message bot';

                                    const avatar = document.createElement('div');
                                    avatar.className = 'message-avatar';
                                    avatar.textContent = 'A';

                                    const content = document.createElement('div');
                                    content.className = 'message-content';

                                    streamingBubble = document.createElement('div');
                                    streamingBubble.className = 'message-bubble';
                                    content.appendChild(streamingBubble);

                                    streamingMsg.appendChild(avatar);
                                    streamingMsg.appendChild(content);
                                    chatMessages.appendChild(streamingMsg);
                                }
                                if (streamingBubble) {
                                    streamingBubble.textContent += event.token || '';
                                    scrollToBottom();
                                }
                                continue;
                            }
                            if (event.type === 'result') {
                                if (streamingMsg) {
                                    streamingMsg.remove();
                                    streamingMsg = null;
                                    streamingBubble = null;
                                }
                                data = event;
                            }
                        }
                    }
                }

                if (!data) {
                    const resultError = new Error('Ответ не был получен');
                    resultError.context = 'stream';
                    throw resultError;
                }

                // Save session
                if (data.session_id) {
                    sessionId = data.session_id;
                    localStorage.setItem('rag_session_id', sessionId);
                }

                // Add bot message
                addMessage('bot', data.answer, {
                    quality: data.quality_score,
                    route: data.route,
                    sources: data.sources,
                    citations: data.citations,
                    trace_id: data.trace_id,
                    session_id: data.session_id,
                    suggested_questions: data.suggested_questions,
                });
                loadSessions();
            } catch (err) {
                if (streamingMsg) {
                    streamingMsg.remove();
                }
                const errInfo = getErrorMessage(err, (err && err.context) || 'send');
                addMessage('bot', errInfo.text, { error: true, actions: errInfo.actions, originalQuestion: question });
            } finally {
                isLoading = false;
                sendBtn.disabled = false;
                typingIndicator.classList.remove('active');
                scrollToBottom();
            }
        }

        // ---------------------------------------------------------------------------
        // Add message to chat
        // ---------------------------------------------------------------------------
        function addMessage(role, text, meta) {
            meta = meta || {};
            const msg = document.createElement('div');
            msg.className = 'message ' + role;

            const avatar = document.createElement('div');
            avatar.className = 'message-avatar';
            avatar.textContent = role === 'user' ? 'U' : 'A';

            const content = document.createElement('div');
            content.className = 'message-content';

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.textContent = text;
            content.appendChild(bubble);

            let actionsDiv = null;
            if (role === 'bot' && text) {
                actionsDiv = document.createElement('div');
                actionsDiv.className = 'msg-actions';

                if (!meta || !meta.error) {
                    const copyBtn = document.createElement('button');
                    copyBtn.className = 'btn-action';
                    copyBtn.title = 'Копировать';
                    copyBtn.setAttribute('aria-label', 'Копировать ответ');
                    copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                    copyBtn.addEventListener('click', async function() {
                        try {
                            await navigator.clipboard.writeText(text);
                            copyBtn.innerHTML = '✓';
                            setTimeout(function() {
                                copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
                            }, 2000);
                        } catch (copyErr) {
                            console.warn('Copy failed:', copyErr);
                        }
                    });
                    actionsDiv.appendChild(copyBtn);
                }

                if (meta && meta.actions && meta.actions.length > 0) {
                    meta.actions.forEach(function(action) {
                        if (action === 'retry') {
                            const retryBtn = document.createElement('button');
                            retryBtn.className = 'btn-action btn-retry';
                            retryBtn.type = 'button';
                            retryBtn.textContent = 'Повторить';
                            retryBtn.setAttribute('aria-label', 'Повторить отправку');
                            retryBtn.addEventListener('click', function() {
                                const questionToRetry = meta.originalQuestion || '';
                                if (!questionToRetry) return;
                                msg.remove();
                                questionInput.value = questionToRetry;
                                sendMessage();
                            });
                            actionsDiv.appendChild(retryBtn);
                        }

                        if (action === 'escalate') {
                            const escalateActionBtn = document.createElement('button');
                            escalateActionBtn.className = 'btn-action btn-escalate-action';
                            escalateActionBtn.type = 'button';
                            escalateActionBtn.textContent = 'Передать оператору';
                            escalateActionBtn.setAttribute('aria-label', 'Передать запрос оператору');
                            escalateActionBtn.addEventListener('click', function() {
                                const questionToEscalate = (meta && meta.originalQuestion) || '';
                                if (!questionToEscalate) return;
                                questionInput.value = questionToEscalate;
                                escalateModal.classList.add('active');
                            });
                            actionsDiv.appendChild(escalateActionBtn);
                        }
                    });
                }

                if (!actionsDiv.childElementCount) {
                    actionsDiv = null;
                } else if (meta && meta.error) {
                    actionsDiv.style.opacity = '1';
                }
            }

            // Badges (bot only)
            if (role === 'bot' && meta) {
                const badges = document.createElement('div');
                badges.className = 'message-badges';

                if (meta.quality !== undefined && meta.quality !== null) {
                    const qBadge = document.createElement('span');
                    qBadge.className = 'badge badge-quality';
                    if (meta.quality < 50) qBadge.classList.add('critical');
                    else if (meta.quality < 70) qBadge.classList.add('low');
                    qBadge.textContent = 'Качество: ' + meta.quality;
                    badges.appendChild(qBadge);
                }

                if (meta.route) {
                    const rBadge = document.createElement('span');
                    rBadge.className = 'badge badge-route';
                    if (meta.route === 'human' || meta.route === 'error') rBadge.classList.add('human');
                    rBadge.textContent = 'Маршрут: ' + meta.route;
                    badges.appendChild(rBadge);
                }

                content.appendChild(badges);

                const citations = Array.isArray(meta.citations) && meta.citations.length > 0
                    ? meta.citations
                    : (meta.sources || []).map(function(source, index) {
                        return {
                            index: index + 1,
                            doc_id: source.source || '',
                            title: source.source || ('Источник ' + (index + 1)),
                            excerpt: (source.page_content || '').substring(0, 300),
                        };
                    });

                if (citations.length > 0) {
                    let bubbleHtml = bubble.innerHTML;
                    citations.forEach(function(citation) {
                        const num = citation.index;
                        const ref = '<button class="citation" type="button" data-citation-index="' + num + '" aria-label="Цитата ' + num + '">[' + num + ']</button>';
                        bubbleHtml = bubbleHtml.replace(new RegExp('\\[' + num + '\\]', 'g'), ref);
                    });
                    if (bubbleHtml !== bubble.innerHTML) {
                        bubble.innerHTML = bubbleHtml;
                    }
                }

                // Sources
                if (meta.sources && meta.sources.length > 0) {
                    const srcBlock = document.createElement('details');
                    srcBlock.className = 'message-sources';
                    const summary = document.createElement('summary');
                    summary.textContent = 'Источники (' + meta.sources.length + ')';
                    srcBlock.appendChild(summary);
                    const ul = document.createElement('ul');
                    meta.sources.forEach(function(s) {
                        const li = document.createElement('li');
                        li.textContent = (s.source || 'Неизвестно') + ': ' + (s.page_content || '').substring(0, 120) + '...';
                        ul.appendChild(li);
                    });
                    srcBlock.appendChild(ul);
                    content.appendChild(srcBlock);
                }

                if (citations.length > 0) {
                    bubble.querySelectorAll('.citation').forEach(function(ref) {
                        const citationIndex = parseInt(ref.dataset.citationIndex, 10);
                        const citation = citations.find(function(item) {
                            return item.index === citationIndex;
                        });
                        if (!citation) return;

                        ref.addEventListener('mouseenter', function() {
                            const src = meta.sources && meta.sources[citationIndex - 1] ? meta.sources[citationIndex - 1] : null;

                            let tooltip = document.getElementById('citationTooltip');
                            if (!tooltip) {
                                tooltip = document.createElement('div');
                                tooltip.id = 'citationTooltip';
                                tooltip.className = 'citation-tooltip';
                                document.body.appendChild(tooltip);
                            }

                            const title = document.createElement('div');
                            title.className = 'source-title';
                            title.textContent = citation.title || (src && src.source) || 'Источник';

                            const excerpt = document.createElement('div');
                            excerpt.className = 'source-excerpt';
                            const excerptText = citation.excerpt || (src && src.page_content) || '';
                            excerpt.textContent = excerptText.length > 180 ? excerptText.substring(0, 180) + '...' : excerptText;

                            tooltip.replaceChildren(title, excerpt);
                            tooltip.classList.add('visible');

                            const rect = ref.getBoundingClientRect();
                            tooltip.style.left = window.scrollX + rect.left + 'px';
                            tooltip.style.top = window.scrollY + rect.bottom + 4 + 'px';
                        });

                        ref.addEventListener('focus', function() {
                            ref.dispatchEvent(new Event('mouseenter'));
                        });

                        ref.addEventListener('mouseleave', function() {
                            hideCitationTooltip();
                        });

                        ref.addEventListener('blur', function() {
                            hideCitationTooltip();
                        });

                        ref.addEventListener('click', function() {
                            const src = meta.sources && meta.sources[citationIndex - 1] ? meta.sources[citationIndex - 1] : null;
                            openSourcePanel(citation, src, ref);
                        });

                        ref.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                const src = meta.sources && meta.sources[citationIndex - 1] ? meta.sources[citationIndex - 1] : null;
                                openSourcePanel(citation, src, ref);
                            }
                        });
                    });
                }

                if (meta.suggested_questions && meta.suggested_questions.length > 0) {
                    const sqDiv = document.createElement('div');
                    sqDiv.className = 'suggested-questions';
                    meta.suggested_questions.forEach(function(q) {
                        const btn = document.createElement('button');
                        btn.className = 'btn-suggested';
                        btn.type = 'button';
                        btn.textContent = q;
                        btn.addEventListener('click', function() {
                            questionInput.value = q;
                            sendMessage();
                        });
                        sqDiv.appendChild(btn);
                    });
                    content.appendChild(sqDiv);
                }

                if (meta.trace_id || meta.session_id) {
                    const fbDiv = document.createElement('div');
                    fbDiv.className = 'msg-feedback';
                    fbDiv.dataset.traceId = meta.trace_id || '';
                    fbDiv.dataset.sessionId = meta.session_id || sessionId || '';
                    fbDiv.innerHTML = `
                        <button class="btn-feedback" data-rating="up" title="Ответ полезен">👍</button>
                        <button class="btn-feedback" data-rating="down" title="Ответ не помог">👎</button>
                    `;
                    content.appendChild(fbDiv);
                }
            }

            if (actionsDiv) {
                content.appendChild(actionsDiv);
            }

            const timestamp = document.createElement('div');
            timestamp.className = 'msg-timestamp';
            timestamp.textContent = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
            content.appendChild(timestamp);

            msg.appendChild(avatar);
            msg.appendChild(content);
            chatMessages.appendChild(msg);
            scrollToBottom();
        }

        function scrollToBottom() {
            requestAnimationFrame(function() {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            });
        }

        // ---------------------------------------------------------------------------
        // New session
        // ---------------------------------------------------------------------------
        newSessionBtn.addEventListener('click', async function() {
            if (sessionId) {
                try {
                    await fetch(API_BASE + '/sessions/' + sessionId, { method: 'DELETE' });
                } catch (err) {
                    console.warn('Failed to delete session:', err);
                }
            }
            sessionId = null;
            localStorage.removeItem('rag_session_id');
            chatMessages.innerHTML = '';
            const welcome = document.createElement('div');
            welcome.className = 'welcome';
            welcome.id = 'welcomeBlock';
            welcome.innerHTML = '<h2>RAG Support Assistant</h2><p>Новая сессия. Задайте ваш вопрос.</p>';
            chatMessages.appendChild(welcome);
            maybeShowOnboarding();
            loadSessions();
        });

        // ---------------------------------------------------------------------------
        // File upload
        // ---------------------------------------------------------------------------
        uploadBtn.addEventListener('click', function() {
            activeModalTrigger = document.activeElement;
            uploadOverlay.classList.add('active');
            uploadStatus.textContent = '';
            uploadStatus.className = 'upload-status';
            if (uploadProgress) uploadProgress.hidden = true;
            if (uploadProgressBar) uploadProgressBar.value = 0;
            if (uploadProgressValue) uploadProgressValue.textContent = '0%';
            uploadDropzone.focus();
        });

        uploadClose.addEventListener('click', function() {
            uploadOverlay.classList.remove('active');
            if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                activeModalTrigger.focus();
                activeModalTrigger = null;
            }
        });

        uploadOverlay.addEventListener('click', function(e) {
            if (e.target === uploadOverlay) {
                uploadOverlay.classList.remove('active');
                if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                    activeModalTrigger.focus();
                    activeModalTrigger = null;
                }
            }
        });

        uploadDropzone.addEventListener('click', function() { fileInput.click(); });
        uploadDropzone.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInput.click();
            }
        });

        fileInput.addEventListener('change', function(e) {
            if (e.target.files.length > 0) uploadFile(e.target.files[0]);
        });

        // Drag & drop on dropzone
        uploadDropzone.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadDropzone.classList.add('dragover');
        });
        uploadDropzone.addEventListener('dragleave', function() {
            uploadDropzone.classList.remove('dragover');
        });
        uploadDropzone.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadDropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
        });

        // Global drag & drop
        var dragCounter = 0;
        document.addEventListener('dragenter', function(e) {
            e.preventDefault();
            dragCounter++;
            if (!uploadOverlay.classList.contains('active')) {
                dragOverlay.classList.add('active');
            }
        });
        document.addEventListener('dragleave', function(e) {
            e.preventDefault();
            dragCounter--;
            if (dragCounter <= 0) {
                dragCounter = 0;
                dragOverlay.classList.remove('active');
            }
        });
        document.addEventListener('dragover', function(e) { e.preventDefault(); });
        document.addEventListener('drop', function(e) {
            e.preventDefault();
            dragCounter = 0;
            dragOverlay.classList.remove('active');
            if (!uploadOverlay.classList.contains('active') && e.dataTransfer.files.length > 0) {
                uploadOverlay.classList.add('active');
                uploadFile(e.dataTransfer.files[0]);
            }
        });

        async function uploadFile(file) {
            uploadStatus.textContent = 'Загрузка ' + file.name + '...';
            uploadStatus.className = 'upload-status';
            setUploadProgress(0);

            var formData = new FormData();
            formData.append('file', file);

            await new Promise(function(resolve) {
                var xhr = new XMLHttpRequest();

                xhr.upload.addEventListener('progress', function(e) {
                    if (e.lengthComputable) {
                        setUploadProgress((e.loaded / e.total) * 100);
                    }
                });

                xhr.addEventListener('load', function() {
                    setUploadProgress(100);
                    var data = {};
                    try {
                        data = JSON.parse(xhr.responseText || '{}');
                    } catch (err) {
                        console.warn('Upload response parse failed:', err);
                    }

                    if (xhr.status >= 200 && xhr.status < 300 && data.status === 'ok') {
                        uploadStatus.textContent = data.message;
                        uploadStatus.className = 'upload-status success';
                        checkHealth();
                    } else {
                        uploadStatus.textContent = data.message || data.detail || 'Ошибка загрузки';
                        uploadStatus.className = 'upload-status error';
                        showToast(uploadStatus.textContent);
                    }
                    resolve();
                });

                xhr.addEventListener('error', function() {
                    const errInfo = getErrorMessage(new Error('Network error'), 'upload');
                    uploadStatus.textContent = errInfo.text;
                    uploadStatus.className = 'upload-status error';
                    showToast(uploadStatus.textContent);
                    resolve();
                });

                xhr.open('POST', API_BASE + '/upload');
                xhr.send(formData);
            });

            fileInput.value = '';
        }

        // ---------------------------------------------------------------------------
        // Load history on page load
        // ---------------------------------------------------------------------------
        async function loadHistory() {
            if (!sessionId) {
                maybeShowOnboarding();
                return;
            }
            try {
                var res = await fetch(API_BASE + '/sessions/' + sessionId + '/history');
                if (!res.ok) {
                    sessionId = null;
                    localStorage.removeItem('rag_session_id');
                    maybeShowOnboarding();
                    return;
                }
                var data = await res.json();
                if (data.messages && data.messages.length > 0) {
                    if (onboardingPanel) {
                        onboardingPanel.hidden = true;
                        onboardingPanel.classList.remove('visible');
                    }
                    const currentWelcome = document.getElementById('welcomeBlock');
                    if (currentWelcome) currentWelcome.style.display = 'none';
                    data.messages.forEach(function(msg) {
                        addMessage(msg.role === 'user' ? 'user' : 'bot', msg.content);
                    });
                } else {
                    maybeShowOnboarding();
                }
            } catch (err) {
                console.warn('Failed to load history:', err);
            }
        }
        if (sidebarCollapseToggle) {
            sidebarCollapseToggle.addEventListener('click', function() {
                if (sidebar && !sidebarMobileMQ.matches) {
                    sidebar.classList.toggle('collapsed');
                }
            });
        }
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', function() {
                if (sidebar && sidebarMobileMQ.matches) {
                    setSidebarOpen(!sidebar.classList.contains('open'));
                }
            });
        }
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', function() {
                setSidebarOpen(false);
            });
        }
        if (sourcePanelOverlay) {
            sourcePanelOverlay.addEventListener('click', closeSourcePanel);
        }
        if (sourcePanelClose) {
            sourcePanelClose.addEventListener('click', closeSourcePanel);
        }
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && sourcePanel && sourcePanel.classList.contains('open')) {
                closeSourcePanel();
                return;
            }
            if (e.key === 'Escape' && escalateModal && escalateModal.classList.contains('active')) {
                escalateModal.classList.remove('active');
                if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                    activeModalTrigger.focus();
                    activeModalTrigger = null;
                }
                return;
            }
            if (e.key === 'Escape' && uploadOverlay && uploadOverlay.classList.contains('active')) {
                uploadOverlay.classList.remove('active');
                if (activeModalTrigger && typeof activeModalTrigger.focus === 'function') {
                    activeModalTrigger.focus();
                    activeModalTrigger = null;
                }
            }
        });
        sidebarMobileMQ.addEventListener('change', handleSidebarMQ);
        handleSidebarMQ(sidebarMobileMQ);
        loadSessions();
        loadHistory();
