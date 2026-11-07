/* Evaluated by actual Chrome against completed-job fixtures, not fake workers. */
globalThis.CompletedPopupChecks = (() => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const visible = node => Boolean(node && node.getClientRects().length);
  function inspect() {
    const dialog = document.getElementById('translation-terminal-overlay');
    const card = dialog.querySelector('.translation-terminal-state.is-complete');
    const title = card.querySelector('h2');
    const close = card.querySelector('[data-close-translation-status]');
    const preview = card.querySelector('#job-terminal-preview-action');
    const download = card.querySelector('#job-terminal-download-action');
    assert(dialog.open && dialog.getAttribute('aria-modal') === 'true', 'Completed dialog must be modal');
    assert(title.textContent === 'Translation Complete' && !title.hasAttribute('tabindex'), 'Heading must not take focus');
    assert(close.getAttribute('aria-label') === 'Close translation status', 'Close button accessible name');
    assert(close.querySelector('svg') && !close.textContent.trim(), 'Close must use a small X icon');
    assert(card.querySelectorAll('button').length === 1, 'Completed popup has only one dismissal control');
    assert(card.querySelectorAll('.translation-complete-actions a').length === 2, 'Completed popup needs two actions');
    assert(preview.textContent === 'Preview Document' && download.textContent === 'Download PDF', 'Action labels');
    assert(!card.textContent.includes('View document history') && !card.textContent.includes('Close status'), 'Redundant controls');
    assert(visible(card.querySelector('.translation-terminal-icon')), 'Success check icon missing');
    const rect = card.getBoundingClientRect();
    assert(rect.left >= 0 && rect.right <= innerWidth + 1, 'Card overflows horizontally');
    assert(rect.top >= 0 && rect.bottom <= innerHeight + 1, 'Normal completed card must fit viewport');
    assert(dialog.scrollWidth <= dialog.clientWidth + 1 && card.scrollWidth <= card.clientWidth + 1, 'Horizontal clipping');
    const controls = [close, preview, download];
    for (const control of controls) {
      const r = control.getBoundingClientRect();
      assert(r.width >= 44 && r.height >= 44, 'Control below touch size');
      assert(r.left >= rect.left && r.right <= rect.right && r.top >= rect.top && r.bottom <= rect.bottom, 'Control outside card');
    }
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i].getBoundingClientRect(), b = controls[j].getBoundingClientRect();
      assert(!(a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom), 'Controls overlap');
    }
    assert(preview.getBoundingClientRect().width === download.getBoundingClientRect().width, 'Action widths differ');
    assert(preview.getBoundingClientRect().height === download.getBoundingClientRect().height, 'Action heights differ');
    assert(getComputedStyle(preview).backgroundColor === 'rgb(11, 93, 59)', 'Preview must use existing primary green');
    assert(getComputedStyle(download).borderStyle === 'solid', 'Download needs outline');
    assert(document.activeElement === preview, 'Initial focus must be on preview, not heading');
    return {width: innerWidth, height: innerHeight, card: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      controls: controls.map(n => n.id || n.className), headingOutline: getComputedStyle(title).outlineStyle};
  }
  return {inspect};
})();
