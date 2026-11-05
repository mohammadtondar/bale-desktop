/* Report Bale's theme colour to the Windows host so the title bar matches.
 * Bale sets <meta name="theme-color"> to its chat background whenever the
 * theme changes (light #FFFFFF, dark #1A1B1C). Read-only; no page changes. */
(() => {
  'use strict';
  if (location.origin !== 'https://web.bale.ai' || window.top !== window || !window.chrome?.webview) return;
  let last = '';
  const send = () => {
    const color = document.querySelector('meta[name="theme-color"]')?.getAttribute('content') || '';
    if (/^#[0-9a-f]{6}$/i.test(color) && color.toLowerCase() !== last) {
      last = color.toLowerCase();
      window.chrome.webview.postMessage(JSON.stringify({kind: 'theme', color}));
    }
  };
  const watch = () => {
    send();
    new MutationObserver(send).observe(document.head, {subtree: true, childList: true, attributes: true, attributeFilter: ['content']});
  };
  if (document.head) watch(); else addEventListener('DOMContentLoaded', watch, {once: true});
})();
