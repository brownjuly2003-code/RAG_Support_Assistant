        const tokenInput = document.getElementById('agentToken');
        const saveAgentTokenBtn = document.getElementById('saveAgentToken');
        const agentStatus = document.getElementById('agentStatus');
        const ticketStatusFilter = document.getElementById('ticketStatusFilter');
        const ticketList = document.getElementById('ticketList');
        const ticketMeta = document.getElementById('ticketMeta');
        const ticketMessages = document.getElementById('ticketMessages');
        const operatorResponse = document.getElementById('operatorResponse');
        const sendResponse = document.getElementById('sendResponse');
        const similarTickets = document.getElementById('similarTickets');
        const qualityScores = document.getElementById('qualityScores');
        const retrievedDocs = document.getElementById('retrievedDocs');

        let currentTicketId = null;

        function getToken() {
            return localStorage.getItem('agent_token') || '';
        }

        function setStatus(message, isError) {
            agentStatus.textContent = message;
            agentStatus.classList.toggle('is-error', Boolean(isError));
        }

        async function apiFetch(path, options) {
            const token = getToken();
            const headers = Object.assign({}, options && options.headers ? options.headers : {});
            if (token) {
                headers.Authorization = 'Bearer ' + token;
            }
            if (!headers['Content-Type'] && options && options.body) {
                headers['Content-Type'] = 'application/json';
            }
            const response = await fetch(path, Object.assign({}, options || {}, { headers }));
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        }

        function renderTicketList(tickets) {
            ticketList.textContent = '';
            if (!tickets.length) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'Тикетов нет.';
                ticketList.appendChild(empty);
                return;
            }

            tickets.forEach(function(ticket) {
                const button = document.createElement('button');
                const status = String(ticket.status || '');
                const statusClass = status.replace(/[^a-z0-9_-]/gi, '');
                const statusBadge = document.createElement('span');
                const question = document.createElement('strong');
                const createdAt = document.createElement('span');
                button.type = 'button';
                button.className = 'ticket-card' + (ticket.id === currentTicketId ? ' active' : '');
                statusBadge.className = 'ticket-status';
                if (statusClass) {
                    statusBadge.classList.add('status-' + statusClass);
                }
                statusBadge.textContent = status;
                question.textContent = ticket.user_question || '';
                createdAt.textContent = String(ticket.created_at || '').replace('T', ' ').slice(0, 16);
                button.appendChild(statusBadge);
                button.appendChild(question);
                button.appendChild(createdAt);
                button.addEventListener('click', function() {
                    loadTicket(ticket.id);
                });
                ticketList.appendChild(button);
            });
        }

        function renderMessages(messages) {
            ticketMessages.textContent = '';
            if (!messages.length) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'История сообщений недоступна.';
                ticketMessages.appendChild(empty);
                return;
            }

            messages.forEach(function(message) {
                const item = document.createElement('article');
                const roleName = String(message.role || 'message');
                const roleClass = roleName.replace(/[^a-z0-9_-]/gi, '') || 'message';
                const role = document.createElement('div');
                const content = document.createElement('div');
                item.className = 'context-message';
                item.classList.add(roleClass);
                role.className = 'context-role';
                role.textContent = roleName;
                content.className = 'context-content';
                content.textContent = message.content || '';
                item.appendChild(role);
                item.appendChild(content);
                ticketMessages.appendChild(item);
            });
        }

        function renderQualityScores(scores) {
            qualityScores.textContent = '';
            const entries = Object.entries(scores || {}).filter(function(entry) {
                return entry[1] !== null && entry[1] !== undefined && entry[1] !== '';
            });
            if (!entries.length) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'Оценки качества недоступны.';
                qualityScores.appendChild(empty);
                return;
            }

            entries.forEach(function(entry) {
                const card = document.createElement('article');
                const label = document.createElement('strong');
                const value = document.createElement('p');
                card.className = 'similar-card';
                label.textContent = entry[0].replace(/_/g, ' ');
                value.textContent = String(entry[1]);
                card.appendChild(label);
                card.appendChild(value);
                qualityScores.appendChild(card);
            });
        }

        function renderRetrievedDocs(items) {
            retrievedDocs.textContent = '';
            if (!items.length) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'Документы не найдены.';
                retrievedDocs.appendChild(empty);
                return;
            }

            items.forEach(function(item) {
                const card = document.createElement('article');
                const title = document.createElement('strong');
                const source = document.createElement('p');
                const excerpt = document.createElement('p');
                card.className = 'similar-card';
                title.textContent = item.title || 'Document';
                source.textContent = item.source || '';
                excerpt.textContent = item.excerpt || '';
                card.appendChild(title);
                if (source.textContent) {
                    card.appendChild(source);
                }
                card.appendChild(excerpt);
                retrievedDocs.appendChild(card);
            });
        }

        function renderSimilar(items) {
            similarTickets.textContent = '';
            if (!items.length) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'Нет похожих resolved тикетов.';
                similarTickets.appendChild(empty);
                return;
            }

            items.forEach(function(item) {
                const card = document.createElement('article');
                const question = document.createElement('strong');
                const response = document.createElement('p');
                card.className = 'similar-card';
                question.textContent = item.user_question || '';
                response.textContent = item.operator_response || 'Ответ пока не сохранён.';
                card.appendChild(question);
                card.appendChild(response);
                similarTickets.appendChild(card);
            });
        }

        async function loadTickets() {
            try {
                const suffix = ticketStatusFilter.value ? '?status=' + encodeURIComponent(ticketStatusFilter.value) : '';
                const data = await apiFetch('/api/agent/tickets' + suffix);
                renderTicketList(data.tickets || []);
                setStatus('Тикеты загружены.', false);
            } catch (error) {
                renderTicketList([]);
                setStatus('Не удалось загрузить тикеты: ' + error.message, true);
            }
        }

        async function loadTicket(ticketId) {
            currentTicketId = ticketId;
            try {
                const data = await apiFetch('/api/agent/tickets/' + ticketId);
                ticketMeta.textContent = 'Session: ' + data.ticket.session_id + ' • Status: ' + data.ticket.status;
                operatorResponse.value = data.ticket.operator_response || data.ticket.ai_draft || '';
                renderMessages(data.messages || []);
                renderRetrievedDocs(data.retrieved_docs || []);
                renderQualityScores(data.quality_scores || {});
                renderSimilar(data.similar_tickets || []);
                loadTickets();
            } catch (error) {
                setStatus('Не удалось загрузить тикет: ' + error.message, true);
            }
        }

        async function respondToTicket() {
            if (!currentTicketId || !operatorResponse.value.trim()) {
                setStatus('Выберите тикет и заполните ответ.', true);
                return;
            }

            try {
                const data = await apiFetch('/api/agent/tickets/' + currentTicketId + '/respond', {
                    method: 'POST',
                    body: JSON.stringify({ response: operatorResponse.value.trim() }),
                });
                setStatus('Ответ сохранён для тикета ' + data.ticket.id + '.', false);
                await loadTicket(currentTicketId);
            } catch (error) {
                setStatus('Не удалось сохранить ответ: ' + error.message, true);
            }
        }

        saveAgentTokenBtn.addEventListener('click', function() {
            localStorage.setItem('agent_token', tokenInput.value.trim());
            setStatus(tokenInput.value.trim() ? 'Токен сохранён.' : 'Токен очищен.', false);
            loadTickets();
        });

        ticketStatusFilter.addEventListener('change', loadTickets);
        sendResponse.addEventListener('click', respondToTicket);

        tokenInput.value = getToken();
        loadTickets();
