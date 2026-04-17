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
    },

    // ── Sidebar Navigation ─────────────────────────────────────

    /**
     * Initialize the sidebar drawer (hamburger toggle, overlay, Escape key).
     * Called automatically when the page has a sidebar.
     */
    initSidebar() {
        const sidebar = document.getElementById('cems-sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        const toggle = document.getElementById('sidebar-toggle');
        if (!sidebar || !overlay || !toggle) return;

        const openSidebar = () => {
            sidebar.classList.add('open');
            overlay.classList.add('open');
            toggle.classList.add('active');
            document.body.classList.add('sidebar-open');
        };

        const closeSidebar = () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('open');
            toggle.classList.remove('active');
            document.body.classList.remove('sidebar-open');
        };

        toggle.addEventListener('click', () => {
            if (sidebar.classList.contains('open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        overlay.addEventListener('click', closeSidebar);

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                closeSidebar();
            }
        });

        // Close sidebar on nav link click (mobile)
        sidebar.querySelectorAll('.cems-sidebar-link').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) {
                    closeSidebar();
                }
            });
        });
    },

    /**
     * Initialize the student navigation elements (user name, admin link, logout).
     * Replaces the old duplicated per-page nav init code.
     * @param {Object} user - The user object from CEMS.getUser()
     */
    initStudentNav(user) {
        if (!user) return;

        // Sidebar user card
        const nameEl = document.getElementById('sidebar-user-name');
        if (nameEl) nameEl.textContent = user.full_name || user.student_id;

        const collegeEl = document.getElementById('sidebar-user-college');
        if (collegeEl) collegeEl.textContent = user.college || '';

        const avatarEl = document.getElementById('sidebar-user-avatar');
        if (avatarEl && user.full_name) {
            const initials = user.full_name
                .split(' ')
                .filter(Boolean)
                .map(w => w[0])
                .slice(0, 2)
                .join('')
                .toUpperCase();
            avatarEl.innerHTML = '<span>' + initials + '</span>';
        }

        // Admin link
        if (user.is_admin) {
            const adminLink = document.getElementById('sidebar-admin-link');
            const adminSection = document.getElementById('sidebar-admin-section');
            if (adminLink) adminLink.classList.remove('d-none');
            if (adminSection) adminSection.classList.remove('d-none');
        }

        // Logout handlers
        const logoutBtn = document.getElementById('sidebar-logout-btn');
        if (logoutBtn) logoutBtn.addEventListener('click', () => CEMS.logout());

        const mobileLogoutBtn = document.getElementById('mobile-logout-btn');
        if (mobileLogoutBtn) mobileLogoutBtn.addEventListener('click', () => CEMS.logout());

        // Initialize sidebar toggle behavior
        CEMS.initSidebar();
    }
};
