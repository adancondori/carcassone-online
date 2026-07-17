// ======================================================
// Voice: push-to-talk recording + keyboard shortcuts
// (plan v2, fase 5)
//
// Space (hold) or mic button (hold) records; releasing
// (or Enter) sends the clip to POST /games/{id}/voice.
// Esc cancels. Cmd/Ctrl+Z undoes, Cmd/Ctrl+Shift+Z redoes.
//
// The response is the same multi-fragment HTMX payload the
// score routes return; applyFragments() swaps each fragment
// by id and re-runs htmx.process so hx-* attributes rebind.
// ======================================================

(function () {
    let mediaRecorder = null;
    let chunks = [];
    let recording = false;
    let cancelled = false;
    let toastTimer = null;

    const IDLE_HINT = 'Mantén presionado el micrófono o la tecla espacio';

    function controlsEl() { return document.getElementById('controls'); }

    function gameId() {
        const el = controlsEl();
        return el ? el.dataset.gameId : null;
    }

    function micBtn() { return document.getElementById('voice-mic-btn'); }

    function voiceSupported() {
        return !!(navigator.mediaDevices
            && navigator.mediaDevices.getUserMedia
            && window.MediaRecorder);
    }

    function setStatus(text, cls) {
        document.querySelectorAll('.voice-status').forEach((el) => {
            const extra = el.classList.contains('tm-status') ? ' tm-status' : '';
            el.textContent = text;
            el.className = 'voice-status' + extra + (cls ? ' ' + cls : '');
        });
        document.querySelectorAll('.voice-mic').forEach((btn) =>
            btn.classList.toggle('recording', cls === 'recording'));
    }

    async function startRecording() {
        if (recording || !gameId()) return;
        if (!voiceSupported()) {
            setStatus('El micrófono requiere HTTPS (o localhost)', 'error');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            chunks = [];
            cancelled = false;
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size) chunks.push(e.data);
            };
            mediaRecorder.onstop = () => {
                stream.getTracks().forEach((t) => t.stop());
                if (cancelled) {
                    setStatus(IDLE_HINT, '');
                    return;
                }
                sendClip(new Blob(chunks, {
                    type: mediaRecorder.mimeType || 'audio/webm',
                }));
            };
            mediaRecorder.start();
            recording = true;
            setStatus('\u{1F3A4} Escuchando…', 'recording');
        } catch (err) {
            setStatus('No pude acceder al micrófono: ' + err.message, 'error');
        }
    }

    function stopRecording(cancel = false) {
        if (!recording || !mediaRecorder) return;
        cancelled = cancel;
        recording = false;
        if (!cancel) setStatus('Procesando…', 'processing');
        mediaRecorder.stop();
    }

    async function sendClip(blob) {
        const id = gameId();
        if (!id) return;
        const form = new FormData();
        form.append('audio', blob, 'clip.webm');
        try {
            const resp = await fetch('/games/' + id + '/voice', {
                method: 'POST',
                body: form,
                headers: { 'HX-Request': 'true' },
            });
            if (!resp.ok) {
                setStatus('Error del servidor (' + resp.status + ')', 'error');
                return;
            }
            applyFragments(await resp.text());
        } catch (err) {
            setStatus('Sin conexión: ' + err.message, 'error');
        }
    }

    function applyFragments(html) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        Array.from(doc.body.children).forEach((node) => {
            if (!node.id) return;
            node.removeAttribute('hx-swap-oob');
            const current = document.getElementById(node.id);
            if (current) {
                current.replaceWith(node);
                if (window.htmx) htmx.process(node);
            }
        });
        if (typeof initControls === 'function') initControls();
        initVoice();
        wireAllMics();
        scheduleToastHide();
    }

    function scheduleToastHide() {
        const toast = document.getElementById('voice-toast');
        if (!toast || !toast.classList.contains('show')) return;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.remove('show'), 5000);
    }

    // -- Mode tabs (manual / voice), remembered per device --
    function applyMode(mode) {
        const controls = controlsEl();
        if (!controls) return;
        controls.querySelectorAll('.mode-tab').forEach((t) =>
            t.classList.toggle('active', t.dataset.mode === mode));
        const voicePanel = document.getElementById('voice-panel');
        const manualForm = document.getElementById('score-form');
        if (voicePanel) voicePanel.hidden = mode !== 'voice';
        if (manualForm) manualForm.hidden = mode === 'voice';
        try { localStorage.setItem('carcassonne-input-mode', mode); } catch (e) { /* private mode */ }
    }

    function savedMode() {
        try { return localStorage.getItem('carcassonne-input-mode') || 'manual'; }
        catch (e) { return 'manual'; }
    }

    function initVoice() {
        const controls = controlsEl();
        if (!controls || !controls.dataset.gameId) return;
        if (controls.dataset.voiceInit) return;  // fragment already wired
        controls.dataset.voiceInit = '1';

        controls.querySelectorAll('.mode-tab').forEach((tab) => {
            tab.addEventListener('click', () => applyMode(tab.dataset.mode));
        });
        if (document.getElementById('voice-panel')) applyMode(savedMode());

        wireMic(micBtn());
        if (micBtn() && !voiceSupported()) {
            setStatus('El micrófono requiere HTTPS (o localhost)', 'error');
        }
    }

    // Hold-to-talk wiring for any mic button (controls panel + table mode).
    function wireMic(btn) {
        if (!btn || btn.dataset.wired) return;
        btn.dataset.wired = '1';
        btn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
        btn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(); });
        btn.addEventListener('touchcancel', () => stopRecording(true));
        btn.addEventListener('mousedown', () => startRecording());
        btn.addEventListener('mouseup', () => stopRecording());
        btn.addEventListener('mouseleave', () => { if (recording) stopRecording(); });
    }

    function wireAllMics() {
        document.querySelectorAll('[data-voice-mic]').forEach(wireMic);
    }

    // -- Table mode (marcador gigante a pantalla completa) --
    let wakeLock = null;

    async function enterTableMode() {
        document.body.classList.add('table-mode-open');
        try {
            if (document.documentElement.requestFullscreen) {
                await document.documentElement.requestFullscreen();
            }
        } catch (e) { /* fullscreen denied: overlay still works */ }
        try {
            if (navigator.wakeLock) {
                wakeLock = await navigator.wakeLock.request('screen');
            }
        } catch (e) { /* wake lock requires HTTPS; optional */ }
    }

    function exitTableMode() {
        document.body.classList.remove('table-mode-open');
        if (document.fullscreenElement) document.exitFullscreen();
        if (wakeLock) { wakeLock.release(); wakeLock = null; }
    }

    // Delegated clicks survive OOB swaps of the overlay.
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-table-mode-open]')) enterTableMode();
        if (e.target.closest('[data-table-mode-close]')) exitTableMode();
        if (e.target.closest('[data-help-open]')) openHelp();
        if (e.target.closest('[data-help-close]')) closeHelp();
    });

    // -- Help modal (guía de voz, atajos y modo mesa) --
    // hoverArmed evita el loop reabrir-al-cerrar: si el puntero sigue sobre
    // el botón (i) cuando se cierra el modal, el mouseover inmediato no
    // debe reabrirlo; se re-arma cuando el puntero sale del botón.
    let hoverArmed = true;

    function openHelp() { document.body.classList.add('help-open'); }
    function closeHelp() {
        document.body.classList.remove('help-open');
        hoverArmed = false;
    }
    function helpIsOpen() { return document.body.classList.contains('help-open'); }

    // Hover also opens the guide on devices with a pointer.
    document.addEventListener('mouseover', (e) => {
        if (e.target.closest('[data-help-open]')) {
            if (hoverArmed) openHelp();
        } else {
            hoverArmed = true;
        }
    });

    // Browser exits fullscreen with Esc: close the overlay too.
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
            document.body.classList.remove('table-mode-open');
        }
    });

    // -- Global keyboard shortcuts --
    function inTextField() {
        const el = document.activeElement;
        return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA');
    }

    document.addEventListener('keydown', (e) => {
        if (!gameId() || inTextField()) return;

        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            const url = '/games/' + gameId() + '/' + (e.shiftKey ? 'redo' : 'undo');
            if (window.htmx) {
                htmx.ajax('POST', url, { target: '#score-table', swap: 'outerHTML' });
            }
            return;
        }
        if (e.code === 'Space' && !e.repeat) {
            e.preventDefault();
            startRecording();
        } else if (e.key === 'Enter' && recording) {
            e.preventDefault();
            stopRecording();
        } else if (e.key === 'Escape') {
            if (recording) {
                stopRecording(true);
            } else if (helpIsOpen()) {
                closeHelp();
            } else if (document.body.classList.contains('table-mode-open')) {
                exitTableMode();
            }
        }
    });

    document.addEventListener('keyup', (e) => {
        if (e.code === 'Space' && recording) {
            e.preventDefault();
            stopRecording();
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        initVoice();
        wireAllMics();
    });
    document.body.addEventListener('htmx:oobAfterSwap', () => {
        initVoice();
        wireAllMics();
        scheduleToastHide();
    });
})();
