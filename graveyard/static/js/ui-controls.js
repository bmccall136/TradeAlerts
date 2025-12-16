// static/js/ui-controls.js
// Sets up UI interactions

export function initUIControls({ resetSimulation }) {
    // Reset simulator
    const resetBtn = document.getElementById('reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            await resetSimulation();
            window.location.reload();
        });
    }

    // TODO: wire Buy/Sell buttons and quantity selectors
}
