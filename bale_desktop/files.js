/* Hand dropped or pasted files to Bale Web as real File objects.
 * WebKitGTK gives pages no files for drops (only a text/uri-list) and none
 * for pasted images, so the app reads them itself and serves each one once
 * at a random bale-file:// address; this rebuilds them and fires the same
 * drop / paste event a browser would, which Bale's own handlers then take.
 * Evaluated by the app as (this function)(event, files, x, y).
 */
(async (event, files, x, y) => {
  'use strict';
  if (location.origin !== 'https://web.bale.ai') return;
  const list = [];
  for (const f of files) {
    const response = await fetch(f.url);
    if (!response.ok) throw new Error('file not available: ' + f.name);
    list.push(new File([await response.blob()], f.name, {type: f.type, lastModified: f.modified || Date.now()}));
  }
  if (!list.length) return;
  const data = new DataTransfer();
  for (const file of list) data.items.add(file);
  if (event === 'drop') {
    const target = document.elementFromPoint(x, y) || document.body;
    target.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, composed: true,
                                                dataTransfer: data, clientX: x, clientY: y}));
  } else {
    const target = document.activeElement || document.body;
    target.dispatchEvent(new ClipboardEvent('paste', {bubbles: true, cancelable: true, composed: true,
                                                      clipboardData: data}));
  }
})
