// WebSocket
const WS = {
    socket: null,
    statusIndicator: null,
    reconnectTime: 1000,
    maxReconnectTime: 30000,
    pingInterval: null,
    
    init() {
        this.statusIndicator = document.getElementById('ws-indicator');
        this.connect();
    },
    
    connect() {
        this.updateStatus('connecting');
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Mock connection path
        this.socket = new WebSocket(`${protocol}//${window.location.host}/ws/chat`);
        
        this.socket.onopen = () => {
            this.updateStatus('connected');
            this.reconnectTime = 1000; // Reset
            
            this.pingInterval = setInterval(() => {
                this.send({ type: 'ping' });
            }, 30000);
        };
        
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Dispatch custom event
                window.dispatchEvent(new CustomEvent('ws-message', { detail: data }));
            } catch (e) {
                console.error('Failed to parse WS message', e);
            }
        };
        
        this.socket.onclose = () => {
            this.updateStatus('disconnected');
            clearInterval(this.pingInterval);
            
            // Reconnect
            setTimeout(() => this.connect(), this.reconnectTime);
            this.reconnectTime = Math.min(this.reconnectTime * 2, this.maxReconnectTime);
        };
        
        this.socket.onerror = (err) => {
            console.error('WS Error:', err);
        };
    },
    
    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(typeof data === 'string' ? data : JSON.stringify(data));
            return true;
        }
        return false;
    },
    
    updateStatus(status) {
        if (!this.statusIndicator) return;
        const dot = this.statusIndicator.querySelector('.status-dot');
        dot.className = `status-dot ${status}`;
        this.statusIndicator.title = `WebSocket: ${status}`;
    }
};
