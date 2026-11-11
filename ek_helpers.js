(function () {
  function btn(re, not) {
    var bs = Array.prototype.slice.call(document.querySelectorAll('button, a, input[type=button], input[type=submit]'));
    for (var i = 0; i < bs.length; i++) {
      var t = (bs[i].textContent || bs[i].value || '').trim();
      if (re.test(t) && !(not && not.test(t))) return bs[i];
    }
    return null;
  }
  function token() {
    var ta = document.querySelector('textarea[name="g-recaptcha-response"], #g-recaptcha-response');
    var t = ta && ta.value ? ta.value : '';
    try { if (!t && window.grecaptcha && window.grecaptcha.getResponse) t = window.grecaptcha.getResponse() || ''; } catch (e) {}
    return t;
  }
  window.__glFill = function (cdc) {
    var el = document.querySelector('input[placeholder="CDC"]');
    if (!el) return 'noinput';
    var set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    set.call(el, cdc);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return 'ok';
  };
  window.__glState = function () {
    var inp = document.querySelector('input[placeholder="CDC"]');
    return JSON.stringify({
      url: location.href,
      input: !!inp,
      val: inp ? String(inp.value || '').replace(/\D/g, '') : '',
      captcha: token().length > 20,
      consult: !!btn(/^\s*consultar\s*$/i),
      dl: !!btn(/descargar\s+archivo\s+xml|descargar\s+xml/i)
    });
  };
  /* deja el recuadro «No soy un robot» a la vista (los portales son bajos) */
  window.__glReveal = function () {
    var el = document.querySelector('iframe[src*="recaptcha/api2/anchor"], iframe[src*="recaptcha/enterprise/anchor"], iframe[title="reCAPTCHA"], .g-recaptcha');
    if (!el) return 'no';
    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) { el.scrollIntoView(); }
    return 'ok';
  };
  window.__glConsult = function () {
    var b = btn(/^\s*consultar\s*$/i);
    if (!b) return 'nobtn';
    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return 'disabled';
    b.click();
    return 'ok';
  };
  window.__glDownload = function () {
    var b = btn(/descargar\s+archivo\s+xml|descargar\s+xml/i);
    if (!b) return 'nobtn';
    b.click();
    return 'ok';
  };
})();
