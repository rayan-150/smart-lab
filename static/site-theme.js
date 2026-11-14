(() => {
    'use strict';

    const root = document.documentElement;
    const key = 'smart-lab.dashboard-theme';
    const themes = new Set(['grid', 'light', 'navy', 'emerald', 'sand']);

    function applyTheme(value) {
        root.dataset.siteTheme = themes.has(value) ? value : 'grid';
    }

    function restoreTheme() {
        try {
            applyTheme(window.localStorage.getItem(key));
        } catch {
            // Keep the current theme when browser storage is unavailable.
        }
    }

    applyTheme('grid');
    restoreTheme();

    function bindThemePicker() {
        const pickers = [...document.querySelectorAll('[data-theme-picker]')];
        const selects = pickers.map(picker => picker.querySelector('[data-site-theme-select]'));
        const themeColor = document.querySelector('meta[name="theme-color"]');

        function updateControls() {
            for (const select of selects) select.value = root.dataset.siteTheme;
            if (themeColor) themeColor.content = window.getComputedStyle(root).getPropertyValue('--background').trim();
        }

        updateControls();
        for (const select of selects) {
            select.addEventListener('change', () => {
                applyTheme(select.value);
                updateControls();
                try {
                    window.localStorage.setItem(key, root.dataset.siteTheme);
                } catch {
                    // A blocked storage API does not prevent changing this page.
                }
            });
        }
        for (const picker of pickers) picker.hidden = false;

        window.addEventListener('storage', (event) => {
            if (event.key !== key && event.key !== null) return;
            applyTheme(event.newValue);
            updateControls();
        });
        window.addEventListener('pageshow', event => {
            if (!event.persisted) return;
            restoreTheme();
            updateControls();
        });
    }

    document.addEventListener('DOMContentLoaded', bindThemePicker, { once: true });
})();
