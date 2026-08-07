        (function() {
            'use strict';

            var apiBase = window.location.origin.replace(/\/+$/, '');
            var widgetTitle = 'Поддержка';
            var embedded = window.parent !== window;
            var parentOrigin = '';
            var handshakeComplete = false;
            var expectedNonce = '';
            var tenantId = 'default';
            var sessionId = '';
            var accessToken = '';
            var bootstrapPromise = null;
            var messages = document.getElementById('messages');
            var input = document.getElementById('input');
            var sendBtn = document.getElementById('sendBtn');
            var status = document.getElementById('status');
            var titleNode = document.getElementById('widgetTitle');
            var closeBtn = document.getElementById('closeBtn');
            var typingNode = null;
            var isSending = false;

            function isValidOrigin(value) {
                if (!value || value === 'null' || value === '*') {
                    return false;
                }
                try {
                    var parsed = new URL(value);
                    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
                } catch (err) {
                    return false;
                }
            }

            try {
                if (document.referrer) {
                    var refOrigin = new URL(document.referrer).origin;
                    if (isValidOrigin(refOrigin)) {
                        parentOrigin = refOrigin;
                    }
                }
            } catch (err) {
                parentOrigin = '';
            }

            function postToParent(message) {
                if (!embedded || !isValidOrigin(parentOrigin)) {
                    return;
                }
                window.parent.postMessage(message, parentOrigin);
            }

            function scheduleResize() {
                requestAnimationFrame(function() {
                    var scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight || 520;
                    postToParent({
                        type: 'rag-widget-resize',
                        height: Math.min(Math.max(scrollHeight, 420), 580)
                    });
                });
            }

            function updateTitle(nextTitle) {
                widgetTitle = nextTitle || widgetTitle;
                document.title = widgetTitle;
                titleNode.textContent = widgetTitle;
            }

            function setStatus(message, isError) {
                status.textContent = message || '';
                status.className = isError ? 'widget-status error' : 'widget-status';
                scheduleResize();
            }

            function autoSizeInput() {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 108) + 'px';
                scheduleResize();
            }

            function scrollMessages() {
                messages.scrollTop = messages.scrollHeight;
            }

            function addMessage(role, text) {
                var node = document.createElement('div');
                node.className = 'widget-msg ' + role;
                node.textContent = text;
                messages.appendChild(node);
                scrollMessages();
                scheduleResize();
            }

            function setTyping(active) {
                if (active && !typingNode) {
                    typingNode = document.createElement('div');
                    typingNode.className = 'widget-msg assistant';
                    typingNode.innerHTML = '<div class="typing" aria-label="Ассистент печатает"><span></span><span></span><span></span></div>';
                    messages.appendChild(typingNode);
                    scrollMessages();
                    scheduleResize();
                    return;
                }

                if (!active && typingNode) {
                    typingNode.remove();
                    typingNode = null;
                    scheduleResize();
                }
            }

            async function ensureBootstrap() {
                if (accessToken && sessionId) {
                    return;
                }
                if (bootstrapPromise) {
                    return bootstrapPromise;
                }
                if (!isValidOrigin(parentOrigin) && embedded) {
                    throw new Error('Parent origin not established for widget bootstrap.');
                }
                var originForBootstrap = isValidOrigin(parentOrigin)
                    ? parentOrigin
                    : window.location.origin;

                bootstrapPromise = fetch(apiBase + '/api/widget/bootstrap', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        parent_origin: originForBootstrap,
                        tenant_id: tenantId,
                        session_id: sessionId || null,
                        handshake_nonce: expectedNonce || null
                    })
                }).then(function(response) {
                    return response.json().catch(function() {
                        return {};
                    }).then(function(data) {
                        if (!response.ok) {
                            var detail = data.detail || 'Widget bootstrap failed.';
                            throw new Error(typeof detail === 'string' ? detail : 'Widget bootstrap failed.');
                        }
                        accessToken = data.token || '';
                        sessionId = data.session_id || sessionId || '';
                        if (data.tenant_id) {
                            tenantId = String(data.tenant_id);
                        }
                        if (!accessToken) {
                            throw new Error('Widget token missing from bootstrap.');
                        }
                        postToParent({
                            type: 'rag-widget-bootstrapped',
                            sessionId: sessionId,
                            handshake_nonce: data.handshake_nonce || expectedNonce || null
                        });
                    });
                }).finally(function() {
                    bootstrapPromise = null;
                });
                return bootstrapPromise;
            }

            async function send() {
                var question = input.value.trim();
                if (!question || isSending) {
                    return;
                }

                isSending = true;
                sendBtn.disabled = true;
                setStatus('', false);
                addMessage('user', question);
                input.value = '';
                autoSizeInput();
                setTyping(true);

                try {
                    await ensureBootstrap();
                    var headers = {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + accessToken
                    };
                    var response = await fetch(apiBase + '/api/ask', {
                        method: 'POST',
                        headers: headers,
                        body: JSON.stringify({
                            question: question,
                            session_id: sessionId || null
                        })
                    });

                    var data = await response.json().catch(function() {
                        return {};
                    });

                    if (!response.ok) {
                        throw new Error(data.detail || 'Не удалось получить ответ.');
                    }

                    if (data.session_id) {
                        sessionId = String(data.session_id);
                    }

                    addMessage('assistant', data.answer || 'Нет ответа');
                } catch (err) {
                    setStatus(err && err.message ? err.message : 'Ошибка подключения. Попробуйте позже.', true);
                    addMessage('assistant', 'Не удалось подключиться к сервису. Попробуйте ещё раз чуть позже.');
                } finally {
                    setTyping(false);
                    isSending = false;
                    sendBtn.disabled = false;
                    input.focus();
                }
            }

            closeBtn.addEventListener('click', function() {
                postToParent({ type: 'rag-widget-close' });
            });

            sendBtn.addEventListener('click', send);

            input.addEventListener('input', autoSizeInput);
            input.addEventListener('keydown', function(event) {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    send();
                }
            });

            window.addEventListener('message', function(event) {
                if (!event.data || typeof event.data !== 'object') {
                    return;
                }
                // Strict handshake: only known message types; origin must be http(s).
                if (!isValidOrigin(event.origin)) {
                    return;
                }
                if (handshakeComplete && parentOrigin && event.origin !== parentOrigin) {
                    return;
                }

                if (event.data.type === 'rag-widget-init') {
                    parentOrigin = event.origin;
                    handshakeComplete = true;
                    if (event.data.apiBase) {
                        apiBase = String(event.data.apiBase).replace(/\/+$/, '');
                    }
                    if (event.data.title) {
                        updateTitle(String(event.data.title));
                    }
                    if (event.data.tenantId || event.data.tenant_id) {
                        tenantId = String(event.data.tenantId || event.data.tenant_id);
                    }
                    if (event.data.sessionId || event.data.session_id) {
                        sessionId = String(event.data.sessionId || event.data.session_id);
                    }
                    if (event.data.handshake_nonce || event.data.nonce) {
                        expectedNonce = String(event.data.handshake_nonce || event.data.nonce);
                    }
                    if (event.data.isEmbedded) {
                        embedded = true;
                        closeBtn.hidden = false;
                    }
                    postToParent({
                        type: 'rag-widget-ack',
                        handshake_nonce: expectedNonce || null
                    });
                    scheduleResize();
                    ensureBootstrap().catch(function(err) {
                        setStatus(err && err.message ? err.message : 'Bootstrap failed', true);
                    });
                    return;
                }

                if (event.data.type === 'rag-widget-focus') {
                    if (!handshakeComplete && embedded) {
                        return;
                    }
                    input.focus();
                }
            });

            if (embedded) {
                closeBtn.hidden = false;
                postToParent({ type: 'rag-widget-ready' });
            }

            updateTitle(widgetTitle);
            autoSizeInput();
            scheduleResize();
            input.focus();
        })();
