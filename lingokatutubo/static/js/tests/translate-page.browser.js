/* DOM assertions evaluated by actual Chrome tests on the signed-in Translate page. */
globalThis.TranslatePageChecks = (() => {
  const el = id => document.getElementById(id);
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const visible = node => Boolean(node && node.getClientRects().length);
  function geometry() {
    const main = el('translate-main');
    const selectors = '#translate-flow-form, .translate-flow__drop, .translate-flow__selected, .translate-flow__status, .translate-flow__fields select, .translate-flow__fields button, .translate-flow__action button, .translate-flow__recovery-actions > *, .translate-flow__recent-item';
    const elements = [...main.querySelectorAll(selectors)].filter(visible);
    const violations = [];
    for (const node of elements) {
      const box = node.getBoundingClientRect();
      if (box.left < -1 || box.right > innerWidth + 1) violations.push(node.id || node.className);
      if (node.scrollWidth > node.clientWidth + 1) violations.push('clipped: ' + (node.id || node.className));
    }
    assert(document.documentElement.scrollWidth <= innerWidth + 1, 'Horizontal page overflow');
    assert(!violations.length, JSON.stringify(violations));
    const notice = main.querySelector('.active-job-banner');
    if (notice) {
      assert(getComputedStyle(notice).position === 'static', 'Processing notice covers form');
      assert(notice.getBoundingClientRect().top >= el('translate-flow-form').getBoundingClientRect().bottom, 'Notice overlaps form');
      assert(notice.getBoundingClientRect().right <= innerWidth + 1, 'Notice overflows viewport');
    }
    const controls = [...main.querySelectorAll('button, select')].filter(visible);
    assert(controls.every(n => n.getBoundingClientRect().height >= 44), 'Undersized touch control');
    return {width: innerWidth, height: innerHeight, checked: elements.length, violations};
  }
  function empty() {
    assert(document.querySelector('.translate-flow__title-row').innerText.trim() === 'Translate a document', 'Repeated header instructions');
    assert(visible(el('translate-drop-zone')), 'Missing file picker');
    assert(el('translate-file').labels.length === 1, 'File input label missing');
    assert(el('translate-file').getAttribute('aria-label') === 'Upload PDF or DOCX', 'File input accessible name');
    assert(el('translate-start-label').textContent === 'Translate Document', 'Primary action label');
    assert(el('translate-start').disabled, 'Submit must require a file');
    assert(el('translate-source').value === 'auto' && el('translate-swap').disabled, 'Automatic source default');
    assert(el('translate-source').options.length === 5 && el('translate-target').options.length === 4, 'Language scope changed');
    assert(document.querySelectorAll('.translate-flow__recent-head a').length === 1, 'Missing history access');
    return geometry();
  }
  function selected(name) {
    assert(!visible(el('translate-drop-zone')), 'Duplicate upload picker in selected state');
    assert(visible(el('translate-selected')) && el('translate-file-name').textContent === name, 'Selected filename');
    assert(el('translate-selected').querySelectorAll('button').length === 1, 'Selected state needs one control');
    assert(/PDF|DOCX/.test(el('translate-file-size').textContent), 'File type missing on mobile');
    assert(!el('translate-start').disabled, 'Valid file should enable translation');
    return geometry();
  }
  function accepted() {
    const stage = el('translate-error-stage');
    assert(stage.getAttribute('role') === 'status', 'Accepted state must not announce error');
    assert(el('translate-review-upload').textContent === 'View translation', 'Accepted primary action');
    assert(el('translate-error-description').textContent === '', 'Duplicate accepted explanation');
    assert(!visible(el('translate-start')), 'Duplicate main action after acceptance');
    assert(el('translate-start').disabled && el('translate-file').disabled, 'Accepted duplicate guard');
    assert(visible(el('translate-try-again')), 'Missing explicit new-document recovery');
    return geometry();
  }
  function uncertain() {
    assert(el('translate-error-title').textContent.includes('could not be confirmed'), 'Uncertainty mislabeled');
    assert(el('translate-error-stage').getAttribute('role') === 'status', 'Uncertainty is not confirmed failure');
    assert(visible(el('translate-review-upload')) && visible(el('translate-try-again')), 'Recovery controls missing');
    assert(el('translate-start').disabled && el('translate-file').disabled, 'Uncertain duplicate guard');
    return geometry();
  }
  return {geometry, empty, selected, accepted, uncertain};
})();
