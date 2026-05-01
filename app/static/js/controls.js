// ======================================================
// Controls: ephemeral UI state for scoring form
// ======================================================
//
// Manages client-side state ONLY: player chip toggling,
// point button selection, event type switching, submit
// button enable/disable with dynamic label.
//
// Re-initializes after HTMX OOB swaps replace the
// #controls div with fresh HTML (no stale listeners).
// ======================================================

function initControls() {
    const controls = document.getElementById('controls');
    if (!controls) return;

    // -- Player chips (multi-select checkboxes) --
    controls.querySelectorAll('.player-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const checkbox = chip.querySelector('input[type="checkbox"]');
            checkbox.checked = !checkbox.checked;
            chip.classList.toggle('active', checkbox.checked);
            updateSubmitButton();
        });
    });

    // -- Event type buttons (radio, single-select) --
    controls.querySelectorAll('.type-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            controls.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const radio = btn.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;
        });
    });

    // -- Point buttons (single-select, sets hidden input) --
    const pointsInput = document.getElementById('points-input');
    const customInput = document.getElementById('custom-points');

    controls.querySelectorAll('.point-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            controls.querySelectorAll('.point-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            pointsInput.value = btn.dataset.points;
            if (customInput) customInput.value = '';
            updateSubmitButton();
        });
    });

    // Custom points input
    if (customInput) {
        customInput.addEventListener('input', () => {
            controls.querySelectorAll('.point-btn').forEach(b => b.classList.remove('active'));
            const val = parseInt(customInput.value);
            pointsInput.value = val > 0 ? val : '';
            updateSubmitButton();
        });
    }

    // -- Submit button state --
    function updateSubmitButton() {
        const btn = document.getElementById('btn-score');
        if (!btn) return;

        const selectedPlayers = controls.querySelectorAll('.player-chip input:checked');
        const hasPoints = pointsInput && pointsInput.value && parseInt(pointsInput.value) > 0;
        const canSubmit = selectedPlayers.length > 0 && hasPoints;

        btn.disabled = !canSubmit;

        if (canSubmit) {
            const names = Array.from(selectedPlayers).map(cb =>
                cb.closest('.player-chip').textContent.trim()
            ).join(', ');
            btn.textContent = 'Anotar +' + pointsInput.value + ' a ' + names;
        } else {
            btn.textContent = 'Anotar puntos';
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initControls);

// Re-initialize after HTMX swaps (controls are OOB-swapped after each score/undo)
document.body.addEventListener('htmx:afterSwap', (event) => {
    if (event.detail.target.id === 'controls' ||
        event.detail.elt.id === 'controls' ||
        document.getElementById('controls')) {
        initControls();
    }
});

// Also listen for OOB swaps specifically
document.body.addEventListener('htmx:oobAfterSwap', (event) => {
    initControls();
});
