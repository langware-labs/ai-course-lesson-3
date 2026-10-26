// Share button: a small pill in a corner of the page that copies the page's link,
// ready to paste into WhatsApp. Self-contained — no dependencies, no network.
//
//   <script src="share.js" defer></script>
//   <script src="share.js" defer data-corner="bottom-left" data-label="שתפו"></script>
//
// data-corner: top-left (default) | top-right | bottom-left | bottom-right.
//   Not top-right inside Flowpad: Flowpad floats its own Share pill there.
// data-label / data-done: override the button text and the "copied" message.
// The language follows <html lang>: he, ar, otherwise English.
(() => {
  const script = document.currentScript;
  const TEXT = {
    he: { label: 'העתקת קישור', done: 'הקישור הועתק! הדביקו אותו בווטסאפ', fail: 'לא הצלחנו להעתיק — העתיקו מהשורה הזו:' },
    ar: { label: 'نسخ الرابط', done: 'تم نسخ الرابط! الصقوه في واتساب', fail: 'لم ننجح في النسخ — انسخوا من هنا:' },
    en: { label: 'Copy link', done: 'Link copied! Paste it in WhatsApp', fail: "Couldn't copy — copy it from here:" },
  };
  const lang = (document.documentElement.lang || 'en').slice(0, 2).toLowerCase();
  const text = TEXT[lang] || TEXT.en;
  const label = script?.dataset.label || text.label;
  const done = script?.dataset.done || text.done;
  const corner = script?.dataset.corner || 'top-left';
  const [vertical, horizontal] = corner.split('-');

  // The link to share: this page, without the display's own `theme` hint.
  function pageLink() {
    const url = new URL(location.href);
    url.searchParams.delete('theme');
    return url.toString();
  }

  async function copy(value) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Older browsers / insecure contexts: the textarea fallback.
      const area = document.createElement('textarea');
      area.value = value;
      area.setAttribute('readonly', '');
      area.style.cssText = 'position:fixed;opacity:0;inset:0;';
      document.body.append(area);
      area.select();
      const ok = document.execCommand('copy');
      area.remove();
      return ok;
    }
  }

  const style = document.createElement('style');
  style.textContent = `
    .share-pill {
      position: fixed; z-index: 2147483000; ${vertical}: max(12px, env(safe-area-inset-${vertical}));
      ${horizontal}: max(12px, env(safe-area-inset-${horizontal}));
      display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
      border: 0; border-radius: 999px; cursor: pointer;
      font: 600 14px/1 system-ui, -apple-system, "Segoe UI", sans-serif;
      color: #fff; background: rgb(20 20 30 / .72); backdrop-filter: blur(8px);
      box-shadow: 0 4px 14px rgb(0 0 0 / .25); touch-action: manipulation;
      transition: transform .15s ease, background .15s ease;
    }
    .share-pill:hover { background: rgb(20 20 30 / .88); }
    .share-pill:active { transform: scale(.95); }
    .share-pill:focus-visible { outline: 3px solid #ffd54a; outline-offset: 2px; }
    .share-pill svg { width: 16px; height: 16px; }
    .share-toast {
      position: fixed; z-index: 2147483001; left: 50%; bottom: max(24px, env(safe-area-inset-bottom));
      transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
      max-width: min(90vw, 420px); padding: 12px 18px; border-radius: 14px; text-align: center;
      font: 600 15px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; overflow-wrap: anywhere;
      color: #fff; background: rgb(20 20 30 / .92); box-shadow: 0 8px 24px rgb(0 0 0 / .3);
      transition: opacity .2s ease, transform .2s ease;
    }
    .share-toast.show { opacity: 1; transform: translate(-50%, 0); pointer-events: auto; user-select: all; }
    @media (prefers-reduced-motion: reduce) { .share-pill, .share-toast { transition: none; } }
  `;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'share-pill';
  button.setAttribute('aria-label', label);
  button.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>';
  button.append(label);

  const toast = document.createElement('div');
  toast.className = 'share-toast';
  toast.setAttribute('role', 'status');
  let hideTimer;

  function say(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => toast.classList.remove('show'), 4000);
  }

  // A tap on the button must never reach the game underneath it.
  for (const type of ['pointerdown', 'touchstart', 'mousedown', 'keydown']) {
    button.addEventListener(type, (event) => event.stopPropagation(), { passive: true });
  }
  button.addEventListener('click', async (event) => {
    event.stopPropagation();
    button.blur(); // so the game's Space / Enter keys don't press it again
    const link = pageLink();
    if (await copy(link)) say(done);
    else say(`${text.fail} ${link}`);
  });

  function mount() {
    document.head.append(style);
    document.body.append(button, toast);
  }
  if (document.body) mount();
  else document.addEventListener('DOMContentLoaded', mount);
})();
