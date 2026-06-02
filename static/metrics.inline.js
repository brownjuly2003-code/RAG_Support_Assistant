        const THRESHOLDS = {
            p95: 12,
            avgQuality: 65,
            escalationRate: 35,
            thumbsDown: 20,
            failureRate: 5,
        };

        function colorClass(value, threshold, lowerIsBetter = false) {
            if (value === null || value === undefined) return "";
            const bad = lowerIsBetter ? value < threshold : value > threshold;
            const warn = lowerIsBetter ? value < threshold * 1.1 : value > threshold * 0.8;
            if (bad) return "status-alert";
            if (warn) return "status-warn";
            return "status-ok";
        }

        function formatValue(value) {
            if (value === null || value === undefined) return "—";
            if (typeof value === "number" && Number.isInteger(value)) return String(value);
            if (typeof value === "number") return value.toFixed(1).replace(/\.0$/, "");
            return String(value);
        }

        function setMetric(id, value, cssClass) {
            const element = document.getElementById(id);
            if (!element) return;
            element.textContent = formatValue(value);
            element.className = cssClass ? `metric-value ${cssClass}` : "metric-value";
        }

        async function refresh() {
            try {
                const response = await fetch("/api/metrics");
                if (!response.ok) throw new Error(String(response.status));
                const metrics = await response.json();

                const latency = metrics.latency || {};
                setMetric("p50", latency.p50_sec, colorClass(latency.p50_sec, 6));
                setMetric("p95", latency.p95_sec, colorClass(latency.p95_sec, THRESHOLDS.p95));
                setMetric("p99", latency.p99_sec, colorClass(latency.p99_sec, 20));

                const quality = metrics.quality || {};
                setMetric(
                    "avgQuality",
                    quality.avg_quality,
                    colorClass(quality.avg_quality, THRESHOLDS.avgQuality, true)
                );

                const escalation = metrics.escalation || {};
                setMetric(
                    "escalationRate",
                    escalation.rate_pct,
                    colorClass(escalation.rate_pct, THRESHOLDS.escalationRate)
                );
                setMetric("totalTraces", escalation.total_traces);

                const feedback = metrics.feedback || {};
                setMetric(
                    "thumbsDown",
                    feedback.thumbs_down_rate_pct,
                    colorClass(feedback.thumbs_down_rate_pct, THRESHOLDS.thumbsDown)
                );

                const errors = metrics.errors || {};
                setMetric(
                    "failureRate",
                    errors.likely_failure_rate_pct,
                    colorClass(errors.likely_failure_rate_pct, THRESHOLDS.failureRate)
                );

                document.getElementById("refreshTs").textContent =
                    "Обновлено: " + new Date().toLocaleTimeString("ru-RU");
            } catch (error) {
                document.getElementById("refreshTs").textContent =
                    "Ошибка загрузки: " + error.message;
            }
        }

        refresh();
        setInterval(refresh, 30000);
