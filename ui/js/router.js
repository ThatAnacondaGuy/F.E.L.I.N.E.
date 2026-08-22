// Router
const Router = {
    routes: ['dashboard', 'calendar', 'tasks', 'projects', 'opportunities', 'goals', 'intelligence', 'chat', 'memory', 'alerts'],
    
    init() {
        window.addEventListener('hashchange', () => this.handleRoute());
        
        if (!window.location.hash) {
            window.location.hash = '#/dashboard';
        } else {
            this.handleRoute();
        }
    },
    
    handleRoute() {
        let route = window.location.hash.replace('#/', '');
        if (!route || !this.routes.includes(route)) {
            route = 'dashboard';
        }
        
        // Update nav styling
        document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('active'));
        const activeLink = document.querySelector(`.nav-link[data-route="${route}"]`);
        if (activeLink) activeLink.classList.add('active');
        
        this.renderRoute(route);
        window.appState.currentRoute = route;
    },
    
    renderRoute(route) {
        const root = document.getElementById('app-root');
        
        // Fade out
        root.style.opacity = 0;
        
        setTimeout(() => {
            // Capitalize first letter
            const title = route.charAt(0).toUpperCase() + route.slice(1);
            
            // Map to component render functions if they exist
            let content = '';
            if (window.Components && typeof window.Components[route] === 'function') {
                content = window.Components[route]();
            } else {
                content = `
                    <div class="page-header">
                        <h2>${title}</h2>
                    </div>
                    <div class="empty-state">
                        <div class="empty-icon">🚧</div>
                        <h3>Module under construction</h3>
                        <p class="text-muted">The ${title} module is being built.</p>
                    </div>
                `;
            }
            
            root.innerHTML = content;
            
            // Call afterRender if exists
            if (window.Components && typeof window.Components[`${route}AfterRender`] === 'function') {
                window.Components[`${route}AfterRender`]();
            }
            
            // Fade in
            root.style.opacity = 1;
        }, 200);
    }
};
