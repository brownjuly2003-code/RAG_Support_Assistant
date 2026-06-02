        (function() {
            'use strict';

            var apiBase = window.location.origin.replace(/\/+$/, '');
            var widgetTitle = 'Поддержка';
            var embedded = window.parent !== window;
            var parentOrigin = '*';
            var messages = document.getElementById('messages');
            var input = document.getElementById('input');
            var sendBtn = document.getElementById('sendBtn');
            var status = document.getElementById('status');
            var titleNode = document.getElementById('widgetTitle');
            var closeBtn = document.getElementById('closeBtn');
            var typingNode = null;
            var isSending = false;

            function resolveParentOrigin(value) {
                return value && value !== 'null' ? value : '*';
            }

            try {
                if (document.referrer) {
                    parentOrigin = resolveParentOrigin(new URL(document.referrer).origin);
                }
            } catch (err) {
                parentOrigin = '*';
            }

            function postToParent(message) {
                if (!embedded) {
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
                    var response = await fetch(apiBase + '/api/ask', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ question: question })
                    });

                    var data = await response.json().catch(function() {
                        return {};
                    });

                    if (!response.ok) {
                        throw new Error(data.detail || 'Не удалось получить ответ.');
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
                if (!event.data) {
                    return;
                }

                if (event.data.type === 'rag-widget-init') {
                    parentOrigin = resolveParentOrigin(event.origin) || parentOrigin;
                    if (event.data.apiBase) {
                        apiBase = String(event.data.apiBase).replace(/\/+$/, '');
                    }
                    if (event.data.title) {
                        updateTitle(String(event.data.title));
                    }
                    if (event.data.isEmbedded) {
                        embedded = true;
                        closeBtn.hidden = false;
                    }
                    scheduleResize();
                    return;
                }

                if (event.data.type === 'rag-widget-focus') {
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
