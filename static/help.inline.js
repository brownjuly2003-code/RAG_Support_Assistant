        (async () => {
            try {
                const response = await fetch('/api/feedback/stats?days=30');
                if (!response.ok) return;
                const data = await response.json();
                if (data.total === 0) return;

                document.getElementById('statsSection').style.display = '';
                document.getElementById('statsText').textContent =
                    `За 30 дней: ${data.total} оценок, ${data.up_pct}% положительных. ` +
                    `Авто-ответы: ${(data.by_route?.auto?.up || 0)} up / ${(data.by_route?.auto?.down || 0)} down. ` +
                    `Эскалации: ${(data.by_route?.human?.up || 0)} up / ${(data.by_route?.human?.down || 0)} down.`;
            } catch (_) {}
        })();
