// Notifications
const Notifications = {
    init: () => {
        if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
            Notification.requestPermission();
        }
    },
    
    showToast: (message, type = 'info', duration = 4000) => {
        const container = document.getElementById('toast-container');
        if (!container) return;
        
        // Remove older toasts if more than 3
        if (container.children.length >= 3) {
            container.removeChild(container.firstChild);
        }
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = type === 'success' ? '✅' : type === 'warning' ? '⚠️' : type === 'error' ? '❌' : 'ℹ️';
        
        toast.innerHTML = `
            <div>${icon}</div>
            <div style="flex:1">${message}</div>
            <button class="toast-close">✕</button>
        `;
        
        container.appendChild(toast);
        
        const closeBtn = toast.querySelector('.toast-close');
        
        const removeToast = () => {
            toast.classList.add('hiding');
            setTimeout(() => {
                if (container.contains(toast)) {
                    container.removeChild(toast);
                }
            }, 300);
        };
        
        closeBtn.addEventListener('click', removeToast);
        
        if (duration > 0) {
            setTimeout(removeToast, duration);
        }
    }
};
