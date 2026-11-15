// Bale shows its notifications through its service worker
// (registration.showNotification). WebView2 displays those itself and never
// raises NotificationReceived, so the app could not suppress them: every
// message produced Bale Desktop's notification and a second, WebView2 one.
// Route them through a page notification instead; the app handles that event,
// shows nothing while its own adapter is connected, and uses it as a fallback
// otherwise.
(() => {
  'use strict';
  try {
    if (typeof ServiceWorkerRegistration === 'undefined' || typeof Notification === 'undefined') return;
    const show = ServiceWorkerRegistration.prototype.showNotification;
    if (typeof show !== 'function') return;
    ServiceWorkerRegistration.prototype.showNotification = function (title, options) {
      try {
        new Notification(String(title ?? ''), options && typeof options === 'object' ? {body: options.body, tag: options.tag} : undefined);
        return Promise.resolve();
      } catch (_) {
        return show.apply(this, arguments);
      }
    };
  } catch (_) { /* leave Bale's own behaviour */ }
})();
