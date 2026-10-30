/* Adapter for Bale Web 5.8.0 (index.fe3fa18088.js).
 * Observe incoming messages only; no outgoing messaging API is exposed.
 */
(() => {
  'use strict';
  if (location.origin !== 'https://web.bale.ai' || window.BaleDesktop) return;
  let runtime, store, core, subscription, connectedCore, connectedOwner, background = false;
  const post = (value) => window.webkit.messageHandlers.bale.postMessage(JSON.stringify(value));

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
      const eventTypes = runtime(11934).i;
      if (event.type !== eventTypes.NewMessages) return;
      const peer = event.peer;
      const state = store.getState();
      const current = runtime(94215).zw(state);
      if (!background && document.hasFocus() && current?.id === peer.id && current?.type === peer.type) return;
      const mine = runtime(41219).H4(state);
      const messages = event.messages.filter(m => !m.isOut && m.senderUid !== mine);
      if (!messages.length) return;
      const settings = runtime(55468).t2(state);
      const exPeer = runtime(45387).jq(peer, state);
      const notificationSettings = runtime(25023);
      if (!notificationSettings.Lq(settings, exPeer.type) || !notificationSettings.nJ(settings, peer)) return;
      const preview = notificationSettings.qV(settings);
      const last = messages[messages.length - 1];
      const id = `${peer.type}:${peer.id}:${last.rid}`;
      const title = runtime(6044).qM(state, peer) || 'پیام جدید بله';
      const body = preview ? (last.message?.textMessage?.text || 'پیام چندرسانه‌ای') : 'پیام جدید';
      post({kind: 'notification', id, title, body});
    } catch (_) {
      post({kind: 'adapter-error', error: 'ساختار نسخهٔ وب تغییر کرده؛ دریافت اعلان نیاز به بررسی دارد.'});
    }
  }

  function connect() {
    const script = [...document.scripts].find(s => /\/index\.[a-f0-9]+\.js/.test(s.src));
    if (script && !script.src.endsWith('/index.fe3fa18088.js')) {
      post({kind: 'adapter-error', error: 'نسخهٔ وب بله تغییر کرده؛ دریافت اعلان اختصاصی نیاز به به‌روزرسانی دارد.'});
      clearInterval(timer);
      return;
    }
    try {
      if (!runtime) {
        if (!window.rspackChunkweb?.push) return;
        window.rspackChunkweb.push([[`bale-desktop-${Date.now()}`], {}, r => { runtime = r; }]);
      }
      providers();
      const owner = store && runtime(41219).H4(store.getState());
      if (subscription && (connectedCore !== core || connectedOwner !== owner)) {
        subscription.unsubscribe();
        subscription = null;
      }
      if (subscription || !store || !core || !owner) return;
      // Validate the read-only notification adapter.
      if (!runtime(11934).i.NewMessages ||
          typeof runtime(45387).jq !== 'function' || typeof runtime(55468).t2 !== 'function') return;
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
  const timer = setInterval(connect, 2000);
  addEventListener('pagehide', () => { clearInterval(timer); subscription?.unsubscribe(); });
})();
