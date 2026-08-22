
window.Components.tasks = () => {
    return `
        <div class="page-header">
            <h2>Tasks</h2>
            <button class="btn btn-primary">+ New Task</button>
        </div>
        <div class="flex gap-2 mb-4">
            <button class="btn btn-secondary btn-sm">All</button>
            <button class="btn btn-ghost btn-sm">Today</button>
            <button class="btn btn-ghost btn-sm">High Priority</button>
        </div>
        <div class="card p-0">
            <div class="task-item priority-critical">
                <input type="checkbox">
                <div class="task-content">
                    <div class="task-title">Submit AI Assignment 3</div>
                    <div class="task-meta"><span class="text-danger">Due Tomorrow</span> • AI Course</div>
                </div>
            </div>
            <div class="task-item priority-high">
                <input type="checkbox">
                <div class="task-content">
                    <div class="task-title">Implement Dashboard UI</div>
                    <div class="task-meta"><span>Due in 2 days</span> • Meow OS</div>
                </div>
            </div>
            <div class="task-item priority-medium task-complete">
                <input type="checkbox" checked>
                <div class="task-content">
                    <div class="task-title">Read Research Paper on Edge AI</div>
                    <div class="task-meta">Completed yesterday</div>
                </div>
            </div>
        </div>
    `;
};
