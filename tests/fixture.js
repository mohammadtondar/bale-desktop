// Minimal SDK contract fixture. No network, credentials or real messages.
globalThis.window = globalThis;
var reports = [], sends = [], observer, tick, state = {
  dialogsStore: {}, owner: 7, current: {type: 1, id: 10},
  settings: {enabled: true, unmuted: true, preview: true}
};
var callbacks = [], sendMode = 'success';
var sdk = {messaging: {
  bindToEvents: () => ({subscribe: o => {observer = o; return {unsubscribe(){observer = null;}};}}),
  addPendingMessages: (peer, thread, messages) => ({subscribe: o => o.next()}),
  sendTextMessage: (message, peer, type) => ({subscribe(o) {
    sends.push({message, peer, type});
    if (sendMode === 'success') o.next({});
    else if (sendMode === 'error') o.error(new Error('offline'));
    else if (sendMode === 'throw') throw new Error('offline');
    else callbacks.push(o);
  }})
}};
var root = {__reactContainer$test: {memoizedProps: {value: {
  store: {getState: () => state}, webSdk: {core: sdk}
}}}};
if (typeof document === 'undefined') {
  globalThis.location = {origin: 'https://web.bale.ai'};
  globalThis.document = {getElementById: () => root, scripts: [{src: 'https://web.bale.ai/index.8d8cd3fd92.js'}], hasFocus: () => false};
  globalThis.addEventListener = () => {};
  globalThis.webkit = {messageHandlers: {bale: {postMessage: s => reports.push(JSON.parse(s))}}};
  globalThis.crypto = {getRandomValues: a => {a[0] = 123456; return a;}};
} else {
  document.getElementById('root').__reactContainer$test = root.__reactContainer$test;
  var originalPost = webkit.messageHandlers.bale.postMessage.bind(webkit.messageHandlers.bale);
  webkit.messageHandlers.bale.postMessage = s => reports.push(JSON.parse(s));
}
globalThis.setInterval = fn => {tick = fn; return 1;};
globalThis.clearInterval = () => {};
var modules = {
  11934: {i: {NewMessages: 'new'}},
  94215: {zw: s => s.current}, 49655: {H4: s => s.owner},
  55468: {t2: s => s.settings}, 45387: {jq: p => ({...p, accessHash: 'private'})},
  25023: {Lq: s => s.enabled, nJ: s => s.unmuted, qV: s => s.preview},
  6044: {qM: (s,p) => 'Chat ' + p.id},
  5594: {m4: {EXPEERTYPE_CHANNEL: 3}},
  87712: {xp: (text,rid,date,mentions,owner) => ({text,rid,date,owner})}
};
globalThis.rspackChunkweb = {push: item => item[2](id => modules[id])};
var serial = 0;
function receive(peer = {id: 10,type: 1}, extras = {}) {
  observer.next({type: 'new', peer, messages: [{rid: ++serial, senderUid: 8,
    message: {textMessage: {text: 'سلام'}}, ...extras}]});
  return `${peer.type}:${peer.id}:${serial}`;
}
function assert(value, text) {if (!value) throw new Error(text);}
