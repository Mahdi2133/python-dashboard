(function () {
  'use strict';
  var A = window.App;

  function alertBox(target, message, kind) {
    A.qs(target).innerHTML = message
      ? '<div class="alert ' + (kind || 'error') + '">' + A.esc(message) + '</div>' : '';
  }

  async function submit(ev) {
    ev.preventDefault();
    var button = A.qs('#login-btn');
    button.disabled = true;
    button.textContent = 'در حال بررسی…';
    alertBox('#login-alert', '');
    try {
      var res = await A.api.post('/api/login', {
        username: A.qs('#username').value.trim(),
        password: A.qs('#password').value,
        next: window.LOGIN_NEXT || ''
      });
      if (res.data && res.data.must_change_password) {
        A.qs('#pw-current').value = A.qs('#password').value;
        A.openModal('pwchange-modal');
        A.qs('#pw-new').focus();
        return;
      }
      window.location.href = res.next || '/';
    } catch (err) {
      alertBox('#login-alert', err.message);
      A.qs('#password').value = '';
      A.qs('#password').focus();
    } finally {
      button.disabled = false;
      button.textContent = 'ورود به سامانه';
    }
  }

  async function changePassword() {
    var next = A.qs('#pw-new').value, again = A.qs('#pw-new2').value;
    if (next !== again) {
      alertBox('#pwchange-alert', 'دو رمز عبور یکسان نیستند.');
      return;
    }
    var button = A.qs('#pw-save');
    button.disabled = true;
    try {
      await A.api.post('/api/me/password', {
        current_password: A.qs('#pw-current').value, new_password: next
      });
      window.location.href = window.LOGIN_NEXT || '/';
    } catch (err) {
      alertBox('#pwchange-alert', err.message);
    } finally { button.disabled = false; }
  }

  document.addEventListener('DOMContentLoaded', function () {
    A.qs('#login-form').addEventListener('submit', submit);
    A.qs('#pw-save').addEventListener('click', changePassword);
    A.qs('#pw-toggle').addEventListener('click', function () {
      var input = A.qs('#password');
      input.type = input.type === 'password' ? 'text' : 'password';
      this.textContent = input.type === 'password' ? '👁' : '🙈';
    });
  });
})();
