/* Adapter for Bale Web.
 * Observe incoming messages only; no outgoing messaging API is exposed.
 * Module ids shift whenever Bale rebuilds the bundle, so every lookup is by
 * export shape (with a candidate list) instead of by a pinned filename hash.
 */
(() => {
  'use strict';
  if (location.origin !== 'https://web.bale.ai' || window.BaleDesktop) return;
  let runtime, store, core, subscription, connectedCore, connectedOwner, background = false;
  let attempts = 0;
  const post = (value) => window.webkit.messageHandlers.bale.postMessage(JSON.stringify(value));

  // ids[symbol] lists module ids that have exported the symbol, newest first.
  const ids = {
    events: [11934],
    currentPeer: [94215],
    selfId: [49655, 41219],
    settings: [55468],
    exPeer: [45387],
    notifications: [25023],
    title: [6044]
  };

  function pick(list, key) {
    for (const id of list) {
      try {
        const module = runtime(id);
        if (module && typeof module[key] !== 'undefined') return module[key];
      } catch (_) { /* module not loaded yet */ }
    }
    return undefined;
  }

  function contract() {
    const events = pick(ids.events, 'i');
    return {
      events,
      currentPeer: pick(ids.currentPeer, 'zw'),
      selfId: pick(ids.selfId, 'H4'),
      settings: pick(ids.settings, 't2'),
      exPeer: pick(ids.exPeer, 'jq'),
      notifications: {
        allows: pick(ids.notifications, 'Lq'),
        unmuted: pick(ids.notifications, 'nJ'),
        preview: pick(ids.notifications, 'qV')
      },
      title: pick(ids.title, 'qM')
    };
  }

  function contractReady(c) {
    return Boolean(c.events?.NewMessages) &&
      typeof c.currentPeer === 'function' && typeof c.selfId === 'function' &&
      typeof c.settings === 'function' && typeof c.exPeer === 'function' &&
      typeof c.notifications.allows === 'function' &&
      typeof c.notifications.unmuted === 'function' &&
      typeof c.notifications.preview === 'function' &&
      typeof c.title === 'function';
  }

  function providers() {
    store = core = undefined;
    const root = document.getElementById('root');
    if (!root) return;
    const key = Object.keys(root).find(k => k.startsWith('__reactContainer$'));
    const fiber = key && root[key];
    if (!fiber) return;
    const stack = [fiber.stateNode?.current || fiber];
    let count = 0;
    while (stack.length && ++count < 30000) {
      const node = stack.pop();
      const value = node.memoizedProps?.value;
      if (value?.store?.getState && value.store.getState().dialogsStore) store = value.store;
      if (value?.webSdk?.core?.messaging) core = value.webSdk.core;
      if (node.child) stack.push(node.child);
      if (node.sibling) stack.push(node.sibling);
    }
  }

  function notify(event) {
    try {
      const c = contract();
      if (event.type !== c.events.NewMessages) return;
      const peer = event.peer;
      const state = store.getState();
      const current = c.currentPeer(state);
      if (!background && document.hasFocus() && current?.id === peer.id && current?.type === peer.type) return;
      const mine = c.selfId(state);
      const messages = event.messages.filter(m => !m.isOut && m.senderUid !== mine);
      if (!messages.length) return;
      const settings = c.settings(state);
      const exPeer = c.exPeer(peer, state);
      if (!c.notifications.allows(settings, exPeer.type) || !c.notifications.unmuted(settings, peer)) return;
      const preview = c.notifications.preview(settings);
      const last = messages[messages.length - 1];
      const id = `${peer.type}:${peer.id}:${last.rid}`;
      const title = c.title(state, peer) || 'پیام جدید بله';
      const body = preview ? (last.message?.textMessage?.text || 'پیام چندرسانه‌ای') : 'پیام جدید';
      post({kind: 'notification', id, title, body});
    } catch (_) {
      post({kind: 'adapter-error', error: 'ساختار نسخهٔ وب تغییر کرده؛ دریافت اعلان نیاز به بررسی دارد.'});
    }
  }

  let ticks = 0;
  function connect() {
    try {
      // Once connected, a cheap owner check replaces the full React tree walk;
      // still rescan every ~30 s in case Bale remounted its providers.
      if (subscription && store && ++ticks % 15 &&
          pick(ids.selfId, 'H4')?.(store.getState()) === connectedOwner) return;
      if (!runtime) {
        if (!window.rspackChunkweb?.push) return;
        window.rspackChunkweb.push([[`bale-desktop-${Date.now()}`], {}, r => { runtime = r; }]);
      }
      // Bale rebuilds the bundle often; symbols move between module ids. Wait a
      // few ticks for the chunk that carries them, then report a stale adapter.
      const c = contract();
      if (!contractReady(c)) {
        if (++attempts >= 5) {
          post({kind: 'adapter-error', error: 'نسخهٔ وب بله تغییر کرده؛ دریافت اعلان اختصاصی نیاز به به‌روزرسانی دارد.'});
          clearInterval(timer);
        }
        return;
      }
      attempts = 0;
      providers();
      const owner = store && pick(ids.selfId, 'H4')?.(store.getState());
      if (subscription && (connectedCore !== core || connectedOwner !== owner)) {
        subscription.unsubscribe();
        subscription = null;
      }
      if (subscription || !store || !core || !owner) return;
      subscription = core.messaging.bindToEvents().subscribe({next: notify, error: () => {
        subscription = null;
        post({kind: 'adapter-error', error: 'ارتباط دریافت پیام قطع شد؛ صفحه را تازه‌سازی کنید.'});
      }});
      connectedCore = core;
      connectedOwner = owner;
      post({kind: 'ready'});
    } catch (_) { /* MainRoutes and authenticated providers may still be loading. */ }
  }

  window.BaleDesktop = Object.freeze({
    background(value) { background = Boolean(value); }
  });

  // Bale fetches a file first and only hands it to the browser while
  // navigator.userActivation.isActive is still true. WebKit expires that flag
  // after ~1 s (Chromium: 5 s), so every file slower than that was silently
  // dropped. Report the click as live; WebKit's own gesture checks are unaffected.
  try {
    if (typeof UserActivation !== 'undefined') {
      Object.defineProperty(UserActivation.prototype, 'isActive', {configurable: true, get: () => true});
    }
  } catch (_) { /* fall back to Bale's own behaviour */ }

  // blob: downloads lose their name before WebKit sees them; report it first.
  // One capture listener on window instead of one listener per object URL.
  addEventListener('click', (event) => {
    try {
      const anchor = event.target.closest?.('a[download]');
      if (anchor && anchor.href.startsWith('blob:')) {
        post({kind: 'download-name', uri: anchor.href, name: anchor.getAttribute('download') || 'file'});
      }
    } catch (_) { /* naming is best-effort; the download itself must still work */ }
  }, true);

  const timer = setInterval(connect, 2000);
  addEventListener('pagehide', () => { clearInterval(timer); subscription?.unsubscribe(); });
})();
