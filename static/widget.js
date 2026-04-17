(function() {
    'use strict';

    var script = document.currentScript || (function() {
        var scripts = document.getElementsByTagName('script');
        return scripts[scripts.length - 1] || null;
    })();

    if (!script || typeof window === 'undefined' || typeof document === 'undefined') {
        return;
    }

    if (document.getElementById('rag-widget-toggle') || document.getElementById('rag-widget-container')) {
        return;
    }

    var scriptUrl;
    try {
        scriptUrl = new URL(script.src, window.location.href);
    } catch (err) {
        scriptUrl = null;
    }

    var configuredApiBase = script.getAttribute('data-api') || '';
    var apiBase = configuredApiBase || (scriptUrl ? scriptUrl.origin : window.location.origin);
    apiBase = apiBase.replace(/\/+$/, '');

    var position = script.getAttribute('data-position') === 'bottom-left' ? 'bottom-left' : 'bottom-right';
    var title = script.getAttribute('data-title') || 'Поддержка';
    var side = position === 'bottom-left' ? 'left' : 'right';
    var iframeSrc = apiBase + '/static/widget.html';
    var iframeOrigin;

    try {
        iframeOrigin = new URL(iframeSrc, window.location.href).origin;
    } catch (err) {
        iframeOrigin = '*';
    }

    var btn;
    var container;
    var iframe;
    var isOpen = false;

    function sendInit() {
        if (!iframe || !iframe.contentWindow) {
            return;
        }

        iframe.contentWindow.postMessage(
            {
                type: 'rag-widget-init',
                apiBase: apiBase,
                title: title,
                isEmbedded: true
            },
            iframeOrigin
        );
    }

    function updateButtonIcon() {
        if (!btn) {
            return;
        }

        btn.innerHTML = isOpen
            ? '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2"/></svg>'
            : '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v7A2.5 2.5 0 0 1 17.5 15H9l-4.5 4v-4.5A2.5 2.5 0 0 1 4 12z" fill="currentColor"/></svg>';
    }

    function syncVisibility() {
        if (!container || !btn) {
            return;
        }

        container.style.opacity = isOpen ? '1' : '0';
        container.style.visibility = isOpen ? 'visible' : 'hidden';
        container.style.transform = isOpen ? 'translateY(0) scale(1)' : 'translateY(16px) scale(0.96)';
        container.style.pointerEvents = isOpen ? 'auto' : 'none';
        btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        updateButtonIcon();

        if (isOpen) {
            sendInit();
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.postMessage({ type: 'rag-widget-focus' }, iframeOrigin);
            }
        }
    }

    function setOpen(nextState) {
        isOpen = !!nextState;
        syncVisibility();
    }

    function mount() {
        if (!document.body || btn || container) {
            return;
        }

        btn = document.createElement('button');
        btn.id = 'rag-widget-toggle';
        btn.type = 'button';
        btn.setAttribute('aria-label', title);
        btn.setAttribute('aria-expanded', 'false');
        btn.style.cssText = [
            'position:fixed',
            side + ':20px',
            'bottom:20px',
            'width:60px',
            'height:60px',
            'border:none',
            'border-radius:999px',
            'background:linear-gradient(135deg,#1957c2,#2e8cf3)',
            'color:#ffffff',
            'cursor:pointer',
            'display:flex',
            'align-items:center',
            'justify-content:center',
            'box-shadow:0 18px 45px rgba(25,87,194,0.35)',
            'z-index:99999',
            'transition:transform 180ms ease,box-shadow 180ms ease'
        ].join(';');
        btn.addEventListener('mouseenter', function() {
            btn.style.transform = 'translateY(-2px)';
            btn.style.boxShadow = '0 22px 48px rgba(25,87,194,0.42)';
        });
        btn.addEventListener('mouseleave', function() {
            btn.style.transform = 'translateY(0)';
            btn.style.boxShadow = '0 18px 45px rgba(25,87,194,0.35)';
        });

        container = document.createElement('div');
        container.id = 'rag-widget-container';
        container.style.cssText = [
            'position:fixed',
            side + ':20px',
            'bottom:92px',
            'width:min(392px,calc(100vw - 24px))',
            'height:min(580px,calc(100vh - 112px))',
            'max-height:calc(100vh - 112px)',
            'border-radius:22px',
            'overflow:hidden',
            'background:#0b1220',
            'box-shadow:0 30px 90px rgba(8,15,32,0.32)',
            'z-index:99998',
            'opacity:0',
            'visibility:hidden',
            'pointer-events:none',
            'transform:translateY(16px) scale(0.96)',
            'transform-origin:' + (position === 'bottom-left' ? 'bottom left' : 'bottom right'),
            'transition:opacity 180ms ease,transform 180ms ease,visibility 180ms ease'
        ].join(';');

        iframe = document.createElement('iframe');
        iframe.src = iframeSrc;
        iframe.title = title;
        iframe.loading = 'lazy';
        iframe.allow = 'clipboard-write';
        iframe.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f5f7fb;';
        iframe.addEventListener('load', sendInit);
        container.appendChild(iframe);

        btn.addEventListener('click', function() {
            setOpen(!isOpen);
        });

        window.addEventListener('message', function(event) {
            if (!iframe || event.source !== iframe.contentWindow || !event.data) {
                return;
            }

            if (event.data.type === 'rag-widget-ready') {
                sendInit();
                return;
            }

            if (event.data.type === 'rag-widget-close') {
                setOpen(false);
                return;
            }

            if (event.data.type === 'rag-widget-resize') {
                var nextHeight = Number(event.data.height);
                if (!nextHeight || !isFinite(nextHeight)) {
                    return;
                }
                var maxHeight = Math.max(360, Math.floor(window.innerHeight - 112));
                var safeHeight = Math.max(360, Math.min(nextHeight, maxHeight));
                container.style.height = safeHeight + 'px';
            }
        });

        window.addEventListener('resize', function() {
            if (!container) {
                return;
            }

            var currentHeight = parseInt(container.style.height, 10);
            if (!currentHeight) {
                return;
            }

            var maxHeight = Math.max(360, Math.floor(window.innerHeight - 112));
            container.style.height = Math.min(currentHeight, maxHeight) + 'px';
        });

        document.body.appendChild(container);
        document.body.appendChild(btn);
        updateButtonIcon();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount, { once: true });
    } else {
        mount();
    }
})();
