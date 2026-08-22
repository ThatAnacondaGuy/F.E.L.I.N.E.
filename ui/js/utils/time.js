// Time Utilities
const TimeUtils = {
    formatRelative: (dateObj) => {
        const now = new Date();
        const diff = Math.floor((now - dateObj) / 1000);
        
        if (diff < 60) return 'Just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        
        const days = Math.floor(diff / 86400);
        if (days === 1) return 'Yesterday';
        if (days < 0 && days === -1) return 'Tomorrow';
        if (days < 0) return `in ${Math.abs(days)} days`;
        return `${days}d ago`;
    },
    
    formatTime: (dateObj) => {
        return dateObj.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    },
    
    formatDate: (dateObj) => {
        return dateObj.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    },
    
    getGreeting: () => {
        const hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 18) return 'Good afternoon';
        return 'Good evening';
    },
    
    deadlineUrgency: (dateObj) => {
        const now = new Date();
        const diffDays = Math.ceil((dateObj - now) / (1000 * 60 * 60 * 24));
        
        if (diffDays < 0) return 'overdue';
        if (diffDays === 0) return 'today';
        if (diffDays <= 3) return 'soon';
        if (diffDays <= 14) return 'upcoming';
        return 'distant';
    },
    
    getCountdown: (dateObj) => {
        const now = new Date();
        const diff = dateObj - now;
        if (diff <= 0) return '0d 0h';
        
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        return `${days}d ${hours}h`;
    }
};
