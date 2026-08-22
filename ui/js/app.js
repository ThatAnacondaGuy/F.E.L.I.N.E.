// App Core
window.appState = {
    currentRoute: '',
    data: {}
};

window.Components = {}; // Registry for UI components

document.addEventListener('DOMContentLoaded', () => {
    // Init Clock
    const clockEl = document.getElementById('live-clock');
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = TimeUtils.formatTime(now);
    }, 1000);
    
    // Init systems
    Notifications.init();
    WS.init();
    Router.init();
    
    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    themeToggle.addEventListener('click', () => {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
    });
    
    // Command Palette (Cmd+K / Ctrl+K)
    const palette = document.getElementById('command-palette');
    const paletteInput = document.getElementById('palette-input');
    
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            palette.classList.toggle('hidden');
            if (!palette.classList.contains('hidden')) {
                paletteInput.focus();
            }
        }
        
        if (e.key === 'Escape' && !palette.classList.contains('hidden')) {
            palette.classList.add('hidden');
        }
    });
    
    palette.querySelector('.palette-overlay').addEventListener('click', () => {
        palette.classList.add('hidden');
    });
});
