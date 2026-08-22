// API Client
const API = {
    baseUrl: window.location.origin,
    
    async _fetch(endpoint, options = {}) {
        try {
            const res = await fetch(`${this.baseUrl}/api${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json'
                },
                ...options
            });
            
            if (!res.ok) {
                throw new Error(`API Error: ${res.status}`);
            }
            
            return await res.json();
        } catch (err) {
            console.error(`API Call failed for ${endpoint}:`, err);
            Notifications.showToast(`Failed to load data`, 'error');
            return null; // Return null on failure for safe handling
        }
    },
    
    // Stub methods that simulate API calls for the UI
    async getDashboard() {
        // Simulated data for Phase 1
        return {
            tasks: { today: 5, overdue: 1 },
            events: { upcoming: 2 },
            projects: { active: 3 },
            now: { title: "Artificial Intelligence", type: "class", until: "4:30 PM" }
        };
    },
    async getTasks() { return []; },
    async createTask(data) { return {}; },
    async completeTask(id) { return {}; },
    async getEvents() { return []; },
    async getProjects() { return []; },
    async getOpportunities() { return []; },
    async getGoals() { return []; },
    async getMemories() { return []; },
    async getBriefing() { return { content: "Good day, Aniket." }; },
    async searchMemory(query) { return []; },
    async chat(message) { return { response: "Received: " + message }; }
};
