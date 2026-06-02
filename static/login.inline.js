        const providersRoot = document.getElementById('providers');
        const statusNode = document.getElementById('status');

        function renderProvider(provider) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'provider-btn ' + provider.name;
            button.textContent = 'Войти через ' + provider.label;
            button.addEventListener('click', function() {
                window.location.href = '/api/auth/sso/' + provider.name + '/login';
            });
            providersRoot.appendChild(button);
        }

        async function loadProviders() {
            try {
                const response = await fetch('/api/auth/sso/providers');
                const payload = await response.json();
                const providers = Array.isArray(payload.providers) ? payload.providers : [];

                providersRoot.innerHTML = '';
                if (!providers.length) {
                    const fallback = document.createElement('a');
                    fallback.className = 'fallback-link';
                    fallback.href = '/static/chat.html';
                    fallback.textContent = 'Открыть чат без SSO';
                    providersRoot.appendChild(fallback);
                    statusNode.textContent = 'SSO пока не настроен. Доступен fallback-переход в чат.';
                    return;
                }

                providers.forEach(renderProvider);
                statusNode.textContent = 'Выберите провайдера и продолжите авторизацию.';
            } catch (error) {
                providersRoot.innerHTML = '';
                statusNode.textContent = 'Не удалось загрузить список провайдеров.';
            }
        }

        loadProviders();
