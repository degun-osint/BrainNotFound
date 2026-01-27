// ============================================
// Utility Functions
// ============================================
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        Toast.show('Code copié !', 'success');
    }).catch(function() {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        Toast.show('Code copié !', 'success');
    });
}

// ============================================
// Modal System
// ============================================
const Modal = {
    // Create modal HTML structure
    init: function() {
        if (document.getElementById('modal-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'modal-overlay';
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal" id="modal-container">
                <div class="modal-header">
                    <h3 class="modal-title" id="modal-title"></h3>
                    <button class="modal-close" id="modal-close">&times;</button>
                </div>
                <div class="modal-body" id="modal-body"></div>
                <div class="modal-footer" id="modal-footer"></div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Close on overlay click
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                Modal.close();
            }
        });

        // Close button
        document.getElementById('modal-close').addEventListener('click', Modal.close);

        // ESC key to close
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && overlay.classList.contains('active')) {
                Modal.close();
            }
        });
    },

    // Show modal
    show: function(options) {
        Modal.init();

        const overlay = document.getElementById('modal-overlay');
        const title = document.getElementById('modal-title');
        const body = document.getElementById('modal-body');
        const footer = document.getElementById('modal-footer');
        const container = document.getElementById('modal-container');

        // Set content
        title.textContent = options.title || '';
        body.innerHTML = options.body || '';

        // Set type class
        container.className = 'modal';
        if (options.type) {
            container.classList.add('modal-' + options.type);
        }

        // Build footer buttons
        footer.innerHTML = '';
        if (options.buttons) {
            options.buttons.forEach(function(btn) {
                const button = document.createElement('button');
                button.textContent = btn.text;
                button.className = 'btn ' + (btn.class || 'btn-secondary');
                button.addEventListener('click', function() {
                    if (btn.action) btn.action();
                    if (btn.close !== false) Modal.close();
                });
                footer.appendChild(button);
            });
        }

        // Show
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';

        // Focus first button
        const firstBtn = footer.querySelector('button');
        if (firstBtn) firstBtn.focus();
    },

    // Close modal
    close: function() {
        const overlay = document.getElementById('modal-overlay');
        if (overlay) {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
        Modal._resolvePromise = null;
    },

    // Alert dialog (replacement for alert())
    alert: function(message, title) {
        title = title || 'Information';
        return new Promise(function(resolve) {
            Modal.show({
                title: title,
                body: '<p>' + message + '</p>',
                type: 'info',
                buttons: [
                    { text: 'OK', class: 'btn-primary', action: resolve }
                ]
            });
        });
    },

    // Confirm dialog (replacement for confirm())
    confirm: function(message, title) {
        title = title || 'Confirmation';
        return new Promise(function(resolve) {
            Modal.show({
                title: title,
                body: '<p>' + message + '</p>',
                type: 'warning',
                buttons: [
                    { text: 'Annuler', class: 'btn-secondary', action: function() { resolve(false); } },
                    { text: 'Confirmer', class: 'btn-primary', action: function() { resolve(true); } }
                ]
            });
        });
    },

    // Confirm delete dialog
    confirmDelete: function(message, title) {
        title = title || 'Supprimer';
        return new Promise(function(resolve) {
            Modal.show({
                title: title,
                body: '<p>' + message + '</p>',
                type: 'danger',
                buttons: [
                    { text: 'Annuler', class: 'btn-secondary', action: function() { resolve(false); } },
                    { text: 'Supprimer', class: 'btn-error', action: function() { resolve(true); } }
                ]
            });
        });
    },

    // Success notification
    success: function(message, title) {
        title = title || 'Succes';
        return new Promise(function(resolve) {
            Modal.show({
                title: title,
                body: '<p>' + message + '</p>',
                type: 'success',
                buttons: [
                    { text: 'OK', class: 'btn-primary', action: resolve }
                ]
            });
        });
    },

    // Error notification
    error: function(message, title) {
        title = title || 'Erreur';
        return new Promise(function(resolve) {
            Modal.show({
                title: title,
                body: '<p>' + message + '</p>',
                type: 'danger',
                buttons: [
                    { text: 'OK', class: 'btn-error', action: resolve }
                ]
            });
        });
    }
};

// ============================================
// Form helpers with modal confirmation
// ============================================
function confirmSubmit(form, message) {
    Modal.confirm(message).then(function(confirmed) {
        if (confirmed) {
            form.submit();
        }
    });
    return false;
}

function confirmDelete(form, itemName) {
    Modal.confirmDelete('Voulez-vous vraiment supprimer ' + itemName + ' ? Cette action est irreversible.').then(function(confirmed) {
        if (confirmed) {
            form.submit();
        }
    });
    return false;
}

// ============================================
// CSRF Protection
// ============================================
function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function injectCSRFTokens() {
    const csrfToken = getCSRFToken();
    if (!csrfToken) return;

    // Add CSRF token to all forms that don't have it
    document.querySelectorAll('form').forEach(function(form) {
        if (!form.querySelector('input[name="csrf_token"]')) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = csrfToken;
            form.appendChild(input);
        }
    });
}

// Add CSRF token to all fetch/XMLHttpRequest calls
(function() {
    const originalFetch = window.fetch;
    window.fetch = function(url, options) {
        options = options || {};
        if (options.method && options.method.toUpperCase() !== 'GET') {
            options.headers = options.headers || {};
            if (!options.headers['X-CSRFToken']) {
                options.headers['X-CSRFToken'] = getCSRFToken();
            }
        }
        return originalFetch.call(this, url, options);
    };

    const originalXHROpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        this._method = method;
        return originalXHROpen.apply(this, arguments);
    };

    const originalXHRSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(data) {
        if (this._method && this._method.toUpperCase() !== 'GET') {
            this.setRequestHeader('X-CSRFToken', getCSRFToken());
        }
        return originalXHRSend.apply(this, arguments);
    };
})();

// ============================================
// Toast Notification System
// ============================================
const Toast = {
    container: null,

    init: function() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }

        // Show existing toasts with animation
        const toasts = this.container.querySelectorAll('.toast');
        toasts.forEach((toast, index) => {
            setTimeout(() => {
                toast.classList.add('show');
                this.autoDissmiss(toast);
            }, index * 100);
        });
    },

    show: function(message, type = 'info', duration = 5000) {
        const icons = {
            success: 'check-circle',
            error: 'warning-circle',
            warning: 'warning-triangle',
            info: 'info-circle'
        };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <i class="toast-icon iconoir-${icons[type] || icons.info}"></i>
            <span>${message}</span>
            <button class="toast-close" onclick="Toast.dismiss(this.parentElement)">
                <i class="iconoir-xmark"></i>
            </button>
        `;

        this.container.appendChild(toast);

        // Trigger animation
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });

        // Auto dismiss
        if (duration > 0) {
            toast.dataset.autoDismiss = duration;
            this.autoDissmiss(toast);
        }

        return toast;
    },

    autoDissmiss: function(toast) {
        const duration = parseInt(toast.dataset.autoDismiss) || 5000;
        setTimeout(() => {
            this.dismiss(toast);
        }, duration);
    },

    dismiss: function(toast) {
        if (!toast) return;
        toast.classList.remove('show');
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
        }, 300);
    },

    success: function(message, duration) {
        return this.show(message, 'success', duration);
    },

    error: function(message, duration) {
        return this.show(message, 'error', duration);
    },

    warning: function(message, duration) {
        return this.show(message, 'warning', duration);
    },

    info: function(message, duration) {
        return this.show(message, 'info', duration);
    }
};

// ============================================
// Searchable Select Component
// ============================================
const SearchableSelect = {
    init: function() {
        document.querySelectorAll('.searchable-select').forEach(function(wrapper) {
            SearchableSelect.initInstance(wrapper);
        });

        // Close all dropdowns when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.searchable-select')) {
                document.querySelectorAll('.searchable-select.open').forEach(function(el) {
                    el.classList.remove('open');
                });
            }
        });
    },

    initInstance: function(wrapper) {
        const trigger = wrapper.querySelector('.searchable-select-trigger');
        const dropdown = wrapper.querySelector('.searchable-select-dropdown');
        const searchInput = wrapper.querySelector('.searchable-select-search input');
        const options = wrapper.querySelectorAll('.searchable-select-option');
        const hiddenInput = wrapper.querySelector('input[type="hidden"]');
        const triggerText = trigger.querySelector('span');

        // Toggle dropdown
        trigger.addEventListener('click', function(e) {
            e.stopPropagation();
            const wasOpen = wrapper.classList.contains('open');

            // Close all other dropdowns
            document.querySelectorAll('.searchable-select.open').forEach(function(el) {
                if (el !== wrapper) el.classList.remove('open');
            });

            wrapper.classList.toggle('open');

            if (!wasOpen && searchInput) {
                setTimeout(function() { searchInput.focus(); }, 10);
            }
        });

        // Search functionality
        if (searchInput) {
            searchInput.addEventListener('input', function() {
                const query = this.value.toLowerCase().trim();
                let hasVisible = false;

                options.forEach(function(opt) {
                    const text = opt.textContent.toLowerCase();
                    if (query === '' || text.includes(query)) {
                        opt.classList.remove('hidden');
                        hasVisible = true;
                    } else {
                        opt.classList.add('hidden');
                    }
                });

                // Show/hide empty message
                let emptyMsg = wrapper.querySelector('.searchable-select-empty');
                if (!hasVisible) {
                    if (!emptyMsg) {
                        emptyMsg = document.createElement('div');
                        emptyMsg.className = 'searchable-select-empty';
                        emptyMsg.textContent = 'Aucun resultat';
                        wrapper.querySelector('.searchable-select-options').appendChild(emptyMsg);
                    }
                    emptyMsg.style.display = 'block';
                } else if (emptyMsg) {
                    emptyMsg.style.display = 'none';
                }
            });

            // Prevent dropdown close on search input click
            searchInput.addEventListener('click', function(e) {
                e.stopPropagation();
            });
        }

        // Option selection
        options.forEach(function(opt) {
            opt.addEventListener('click', function(e) {
                e.stopPropagation();
                const value = this.dataset.value;
                const text = this.textContent.trim();

                // Update selection
                options.forEach(function(o) { o.classList.remove('selected'); });
                this.classList.add('selected');

                // Update trigger text and hidden input
                if (triggerText) triggerText.textContent = text;
                if (hiddenInput) hiddenInput.value = value;

                // Close dropdown
                wrapper.classList.remove('open');

                // Clear search
                if (searchInput) {
                    searchInput.value = '';
                    options.forEach(function(o) { o.classList.remove('hidden'); });
                }

                // Trigger form submit if configured
                const form = wrapper.closest('form');
                if (form && wrapper.dataset.autosubmit === 'true') {
                    form.submit();
                }
            });
        });
    }
};

// ============================================
// DOMContentLoaded initialization
// ============================================
document.addEventListener('DOMContentLoaded', function() {
    // Inject CSRF tokens into all forms
    injectCSRFTokens();

    // Initialize toast system
    Toast.init();

    // Initialize modal system
    Modal.init();

    // Initialize searchable selects
    SearchableSelect.init();

    // Initialize mobile menu
    initMobileMenu();
});

// ============================================
// Mobile Menu
// ============================================
function initMobileMenu() {
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');

    if (!navToggle || !navMenu) return;

    // Toggle main menu
    navToggle.addEventListener('click', function() {
        navToggle.classList.toggle('active');
        navMenu.classList.toggle('active');
    });

    // Handle dropdowns in mobile
    const dropdowns = navMenu.querySelectorAll('.nav-dropdown, .tenant-dropdown');
    dropdowns.forEach(function(dropdown) {
        const btn = dropdown.querySelector('.nav-dropdown-btn, .tenant-dropdown-btn');
        if (btn) {
            btn.addEventListener('click', function(e) {
                // Only handle in mobile view
                if (window.innerWidth <= 1300) {
                    e.preventDefault();
                    e.stopPropagation();
                    dropdown.classList.toggle('active');
                }
            });
        }
    });

    // Close menu when clicking outside
    document.addEventListener('click', function(e) {
        if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
            navToggle.classList.remove('active');
            navMenu.classList.remove('active');
        }
    });

    // Close menu on window resize to desktop
    window.addEventListener('resize', function() {
        if (window.innerWidth > 1300) {
            navToggle.classList.remove('active');
            navMenu.classList.remove('active');
            dropdowns.forEach(function(d) { d.classList.remove('active'); });
        }
    });
}

// ============================================
// Form validation for quiz submission
// ============================================
const quizForm = document.getElementById('quizForm');
if (quizForm) {
    quizForm.addEventListener('submit', function(e) {
        const questions = document.querySelectorAll('.question');
        let allAnswered = true;

        questions.forEach(function(question) {
            const mcqInputs = question.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            const textInputs = question.querySelectorAll('textarea');

            if (mcqInputs.length > 0) {
                const checkboxes = question.querySelectorAll('input[type="checkbox"]');
                const radios = question.querySelectorAll('input[type="radio"]');

                if (checkboxes.length > 0) {
                    const checked = Array.from(checkboxes).some(cb => cb.checked);
                    if (!checked) {
                        allAnswered = false;
                    }
                }
            }

            if (textInputs.length > 0) {
                textInputs.forEach(function(textarea) {
                    if (textarea.value.trim() === '') {
                        allAnswered = false;
                    }
                });
            }
        });

        if (!allAnswered) {
            e.preventDefault();
            Modal.alert('Veuillez repondre a toutes les questions avant de soumettre.', 'Attention');
            return false;
        }
    });
}

// ============================================
// Theme Toggle (Dark Mode)
// ============================================
(function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const iconLight = document.getElementById('theme-icon-light');
    const iconDark = document.getElementById('theme-icon-dark');

    // Update icon based on current theme
    function updateIcon() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        if (iconLight && iconDark) {
            iconLight.style.display = isDark ? 'none' : 'inline';
            iconDark.style.display = isDark ? 'inline' : 'none';
        }
    }

    // Initialize icon on page load
    updateIcon();

    // Toggle theme on click
    themeToggle.addEventListener('click', function() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

        if (isDark) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
        }

        updateIcon();
    });
})();
