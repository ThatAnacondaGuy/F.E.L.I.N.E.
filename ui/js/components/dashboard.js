
window.Components.dashboard = () => {
    return `
        <div class="page-header">
            <div>
                <h2>${TimeUtils.getGreeting()}, Aniket.</h2>
                <div class="text-muted">${TimeUtils.formatDate(new Date())}</div>
            </div>
            <div class="flex gap-2">
                <button class="btn btn-primary"><span>+</span> Add Task</button>
                <button class="btn btn-secondary" onclick="window.location.hash='#/chat'">Chat</button>
            </div>
        </div>
        
        <div class="stats-row">
            <div class="card" style="min-width: 200px; flex: 1;">
                <div class="text-muted text-sm">Tasks Today</div>
                <div class="font-bold mt-2" style="font-size: 28px;">5</div>
            </div>
            <div class="card" style="min-width: 200px; flex: 1; border-color: rgba(239, 68, 68, 0.3);">
                <div class="text-danger text-sm">Overdue</div>
                <div class="font-bold mt-2" style="font-size: 28px;">1</div>
            </div>
            <div class="card" style="min-width: 200px; flex: 1;">
                <div class="text-muted text-sm">Active Projects</div>
                <div class="font-bold mt-2" style="font-size: 28px;">3</div>
            </div>
            <div class="card" style="min-width: 200px; flex: 1; background: linear-gradient(145deg, #111827 0%, rgba(118, 185, 0, 0.1) 100%); border-color: rgba(118, 185, 0, 0.3);">
                <div class="text-nvidia text-sm font-bold">NVIDIA Career Goal</div>
                <div class="mt-2 progress-bar-container">
                    <div class="progress-bar nvidia" style="width: 35%"></div>
                </div>
                <div class="text-xs text-muted mt-2">35% Ready (TE Phase)</div>
            </div>
        </div>
        
        <div class="grid gap-6" style="grid-template-columns: 2fr 1fr;">
            <div>
                <h3 class="mb-4">Today's Timeline</h3>
                <div class="card">
                    <div class="timeline">
                        <div class="timeline-item">
                            <div class="timeline-time">9:15 AM - 11:15 AM</div>
                            <div class="font-bold">Artificial Intelligence (PCC301COM)</div>
                            <div class="text-sm text-muted">Room 304</div>
                        </div>
                        <div class="timeline-item">
                            <div class="timeline-time">11:30 AM - 1:30 PM</div>
                            <div class="font-bold">Computer Networks (PCC302COM)</div>
                            <div class="text-sm text-muted">Lab 2</div>
                        </div>
                        <div class="timeline-item" style="opacity: 0.5;">
                            <div class="timeline-time">4:30 PM - 7:00 PM</div>
                            <div class="font-bold">Deep Focus: Project Meow OS</div>
                            <div class="text-sm text-muted">Home</div>
                        </div>
                    </div>
                </div>
            </div>
            <div>
                <h3 class="mb-4">Urgent Alerts</h3>
                <div class="flex-col gap-4">
                    <div class="card" style="border-left: 4px solid var(--color-danger);">
                        <div class="text-sm font-bold text-danger mb-1">DUE TOMORROW</div>
                        <div>Submit AI Assignment 3</div>
                    </div>
                    <div class="card" style="border-left: 4px solid var(--color-warning);">
                        <div class="text-sm font-bold text-warning mb-1">INACTIVE PROJECT</div>
                        <div>React Native App hasn't been updated in 14 days.</div>
                    </div>
                </div>
            </div>
        </div>
    `;
};
