/* Local reading preferences only: no dependencies or network requests. */
(() => {
  'use strict';
  const key = 'powerfit-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const normalize = value => ['light', 'dark'].includes(value) ? value : 'system';
  let mode = 'system';
  try {
    mode = normalize(localStorage.getItem(key));
  } catch (_) { /* Storage can be unavailable; the control still works in this page. */ }

  function apply() {
    document.documentElement.dataset.theme = mode === 'system'
      ? (system.matches ? 'dark' : 'light') : mode;
  }
  // Run before the stylesheet paints, including when an explicit choice is saved.
  apply();
  system.addEventListener('change', apply);
  document.addEventListener('DOMContentLoaded', () => {
    const select = document.getElementById('theme-select');
    select.value = mode;
    select.closest('label').hidden = false;
    select.addEventListener('change', () => {
      mode = normalize(select.value);
      try {
        if (mode === 'system') localStorage.removeItem(key);
        else localStorage.setItem(key, mode);
      } catch (_) { /* Keep the selected theme even without persistent storage. */ }
      apply();
    });
    window.addEventListener('storage', event => {
      if (event.key === key || event.key === null) {
        mode = normalize(event.newValue);
        select.value = mode;
        apply();
      }
    });
    const contents = document.querySelector('.toc details');
    if (contents) contents.open = !window.matchMedia('(max-width: 760px)').matches;
  });
})();
