/**
 * CEMS - Campus Election Management System
 * Core JavaScript utilities for API calls, auth, and UI helpers.
 */
const CEMS = {
    /**
     * Persist user info for frontend navigation state.
     */
    setUser(user) {
        if (!user) return;
        sessionStorage.setItem('cems_user', JSON.stringify(user));
    },

    /**
     * Make an API call with automatic CSRF token and JSON handling.
     * Throws on network errors or non-OK responses that aren't JSON.
     */
    async api(url, options = {}) {
        const defaults = {
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CEMS.getCookie('csrftoken'),
            },
        };

        const merged = { ...defaults, ...options };
        merged.headers = { ...defaults.headers, ...(options.headers || {}) };

        const response = await fetch(url, merged);

        // Handle rate limiting
        if (response.status === 429) {
            throw new Error('Too many requests. Please wait a moment and try again.');
        }

        // Try to parse JSON response
        const text = await response.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch (e) {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return { success: true, raw: text };
        }

        return data;
    },

    /**
     * Get a cookie value by name.
     */
    getCookie(name) {
        const cookies = document.cookie.split(';');
        for (let c of cookies) {
            c = c.trim();
            if (c.startsWith(name + '=')) {
                return decodeURIComponent(c.substring(name.length + 1));
            }
        }
        return '';
    },

    /**
     * Get authenticated user info from sessionStorage or server bootstrap.
     */
    getUser() {
        try {
            const stored = JSON.parse(sessionStorage.getItem('cems_user'));
            if (stored) {
                return stored;
            }
        } catch (e) {
            // Fall through to server-bootstrapped user.
        }

        const bootstrapEl = document.getElementById('cems-bootstrap-user');
        if (!bootstrapEl) return null;

        try {
            const user = JSON.parse(bootstrapEl.textContent);
            CEMS.setUser(user);
            return user;
        } catch (e) {
            return null;
        }
    },

    /**
     * Remove cached user info from sessionStorage.
     */
    clearUser() {
        sessionStorage.removeItem('cems_user');
    },

    /**
     * Logout - clear session and redirect.
     */
    async logout() {
        try {
            await CEMS.api('/api/auth/logout/', { method: 'POST' });
        } catch (e) {
            // Ignore errors during logout
        }
        CEMS.clearUser();
        window.location.href = '/';
    },

    /**
     * Show a Bootstrap toast notification.
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const icons = {
            success: 'bi-check-circle-fill',
            danger: 'bi-exclamation-triangle-fill',
            warning: 'bi-exclamation-circle-fill',
            info: 'bi-info-circle-fill'
        };

        const id = 'toast-' + Date.now();
        const html = `
            <div id="${id}" class="toast align-items-center text-bg-${type} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="bi ${icons[type] || icons.info} me-1"></i>
                        ${CEMS.escapeHtml(message)}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto"
                            data-bs-dismiss="toast"></button>
                </div>
            </div>`;

        container.insertAdjacentHTML('beforeend', html);
        const toastEl = document.getElementById(id);
        const toast = new bootstrap.Toast(toastEl, { delay: 5000 });
        toast.show();

        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    },

    /**
     * HTML-escape a string to prevent XSS.
     */
    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};
