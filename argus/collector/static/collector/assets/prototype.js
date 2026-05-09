(function () {
  var DEFAULT_COMPARE_SELECTION = ['north', 'quiet', 'west'];
  var STATION_NAMES = {
    north: 'North Relay',
    quiet: 'Quiet Gateway',
    south: 'South Bridge',
    west: 'West Meter'
  };
  var COMPARE_SELECTION_STORAGE_KEY = 'argus.prototype.compare.selection';
  var COMPARE_SELECTION_UPDATED_KEY = 'argus.prototype.compare.selection.updated';

  function normalizeCompareSelection(values, limit) {
    var normalized = [];
    (values || []).forEach(function (value) {
      if (!value || normalized.indexOf(value) !== -1) return;
      normalized.push(value);
    });
    if (typeof limit === 'number') return normalized.slice(0, limit);
    return normalized;
  }

  function readStoredCompareSelection() {
    try {
      var raw = window.localStorage.getItem(COMPARE_SELECTION_STORAGE_KEY);
      if (raw == null) return null;
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return null;
      return normalizeCompareSelection(parsed);
    } catch (error) {
      return null;
    }
  }

  function writeStoredCompareSelection(values, markUpdated) {
    try {
      window.localStorage.setItem(COMPARE_SELECTION_STORAGE_KEY, JSON.stringify(normalizeCompareSelection(values)));
      window.localStorage.setItem(COMPARE_SELECTION_UPDATED_KEY, markUpdated === false ? '0' : '1');
    } catch (error) {
      // Ignore storage failures in the static prototype.
    }
  }

  function shouldRefreshStoredComparison(force) {
    if (force) return true;
    try {
      return window.localStorage.getItem(COMPARE_SELECTION_UPDATED_KEY) === '1';
    } catch (error) {
      return false;
    }
  }

  function clearStoredComparisonFlag() {
    try {
      window.localStorage.setItem(COMPARE_SELECTION_UPDATED_KEY, '0');
    } catch (error) {
      // Ignore storage failures in the static prototype.
    }
  }

  function findDialog(name) {
    return document.querySelector('[data-dialog="' + name + '"]');
  }

  function readCookie(name) {
    var prefix = name + '=';
    return document.cookie.split(';').map(function (item) {
      return item.trim();
    }).filter(function (item) {
      return item.indexOf(prefix) === 0;
    }).map(function (item) {
      return decodeURIComponent(item.slice(prefix.length));
    })[0] || '';
  }

  function postForm(url, values) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'X-CSRFToken': readCookie('csrftoken')
      },
      body: new URLSearchParams(values),
      credentials: 'same-origin'
    }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || '请求失败，请稍后重试。');
        }
        return payload;
      });
    });
  }

  function postLoginForm(url, values) {
    return postForm(url, values);
  }

  function showLoginStatus(target, message, isError) {
    if (!target) return;
    target.textContent = message;
    target.classList.remove('argus-hidden');
    target.classList.toggle('bg-[#eef8f0]', !isError);
    target.classList.toggle('text-[#2f6a3d]', !isError);
    target.classList.toggle('bg-[#fff1f0]', !!isError);
    target.classList.toggle('text-[#8a3d2d]', !!isError);
  }

  function showInlineStatus(target, message, isError) {
    if (!target) return;
    target.textContent = message;
    target.classList.remove('argus-hidden');
    target.classList.toggle('bg-[#eef8f0]', !isError);
    target.classList.toggle('text-[#2f6a3d]', !isError);
    target.classList.toggle('bg-[#fff1f0]', !!isError);
    target.classList.toggle('text-[#8a3d2d]', !!isError);
  }

  function ensureDialogMarkup(name, markup) {
    if (findDialog(name)) return;
    document.body.insertAdjacentHTML('beforeend', markup);
  }

  function openDialog(name) {
    var dialog = findDialog(name);
    if (!dialog) return;
    document.querySelectorAll('[data-dialog].is-open').forEach(function (openItem) {
      if (openItem !== dialog) closeDialog(openItem);
    });
    dialog.classList.add('is-open');
    dialog.setAttribute('aria-hidden', 'false');
    var closeButton = dialog.querySelector('[data-dialog-close]');
    if (closeButton) closeButton.focus({ preventScroll: true });
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    dialog.classList.remove('is-open');
    dialog.setAttribute('aria-hidden', 'true');
  }

  function setFieldValue(root, selector, value) {
    var element = root.querySelector(selector);
    if (!element || value == null) return;
    if (element.matches('input, textarea, select')) {
      element.value = value;
      return;
    }
    element.textContent = value;
  }

  function populateSiteEditor(trigger) {
    var dialog = findDialog('site-editor');
    if (!dialog) return;

    var mode = trigger.getAttribute('data-site-mode') || 'edit';
    var isCreate = mode === 'create' || mode === 'add';
    var title = isCreate ? '添加候选AI中转站' : '编辑候选AI中转站';
    var summary = isCreate
      ? '录入 Base URL、名称和汇率。保存后会立即做一次端点校验。'
      : '调整名称、根地址、汇率和备注。保存后只刷新当前候选AI中转站的档案。';

    dialog.dataset.siteId = isCreate ? '' : (trigger.getAttribute('data-site-id') || '');

    setFieldValue(dialog, '[data-site-editor-heading]', title);
    setFieldValue(dialog, '[data-site-editor-summary]', summary);
    setFieldValue(dialog, '[data-site-editor-name]', trigger.getAttribute('data-site-name') || 'New Relay');
    setFieldValue(dialog, '[data-site-editor-url]', trigger.getAttribute('data-site-url') || 'https://new.example.ai/');
    setFieldValue(dialog, '[data-site-editor-rate]', trigger.getAttribute('data-site-rate') || '7.20');
    setFieldValue(dialog, '[data-site-editor-note]', trigger.getAttribute('data-site-note') || '');
    const enabledInput = dialog.querySelector('[data-site-editor-enabled]');
    if (enabledInput) {
      enabledInput.checked = trigger.getAttribute('data-site-disabled') !== 'true';
    }
    setFieldValue(dialog, '[data-site-editor-status]', trigger.getAttribute('data-site-status') || (isCreate ? '保存后会自动排一次价格校验。' : '上次成功 12 分钟前，当前快照可继续参与比价。'));
    setFieldValue(dialog, '[data-site-editor-models]', trigger.getAttribute('data-site-models') || (isCreate ? '保存后读取' : '184 个模型'));

    var success = dialog.querySelector('[data-site-editor-success]');
    if (success) success.classList.add('argus-hidden');
  }

  function populateLoginDialog(trigger) {
    var dialog = findDialog('login');
    if (!dialog) return;
    var defaultNextHref = window.location.pathname.indexOf('/watchlist/') !== -1
      ? 'sites.html'
      : (window.location.pathname.indexOf('/account/') !== -1 || window.location.pathname.indexOf('/pricing/') !== -1 ? '../watchlist/sites.html' : 'watchlist/sites.html');

    setFieldValue(dialog, '[data-login-heading]', trigger.getAttribute('data-login-title') || '邮箱登录');
    setFieldValue(dialog, '[data-login-summary]', trigger.getAttribute('data-login-summary') || '输入邮箱和验证码后进入当前账户的工作台。这里只做轻量验证，不再切到独立登录页。');
    setFieldValue(dialog, '[data-login-submit]', trigger.getAttribute('data-login-submit') || '验证并进入');
    setFieldValue(dialog, '[data-login-email-input]', trigger.getAttribute('data-login-email') || 'hello@example.com');
    setFieldValue(dialog, '[data-login-code-input]', trigger.getAttribute('data-login-code') || '1024');

    var nextLink = dialog.querySelector('[data-login-next]');
    if (nextLink) {
      nextLink.textContent = trigger.getAttribute('data-login-next-label') || '进入候选AI中转站清单';
      nextLink.setAttribute('href', trigger.getAttribute('data-login-next-href') || defaultNextHref);
    }

    var codeSent = dialog.querySelector('[data-login-code-sent]');
    if (codeSent) codeSent.classList.add('argus-hidden');

    var success = dialog.querySelector('[data-login-success]');
    if (success) success.classList.add('argus-hidden');
  }

  function ensureSharedDialogs() {
    if (document.querySelector('[data-dialog-open="site-editor"]')) {
      ensureDialogMarkup('site-editor', `
        <div class="argus-dialog-backdrop" data-dialog="site-editor" aria-hidden="true">
          <section class="argus-dialog argus-dialog-lg" role="dialog" aria-modal="true" aria-labelledby="site-editor-title">
            <div class="argus-dialog-head"><div><h2 id="site-editor-title" data-site-editor-heading class="argus-serif text-[26px] font-bold text-slate-900">编辑候选AI中转站</h2><p data-site-editor-summary class="mt-2 text-[15px] leading-7 text-slate-500">调整名称、根地址、汇率和备注。保存后只刷新当前候选AI中转站的档案。</p></div><button class="argus-icon-btn" data-dialog-close aria-label="关闭">×</button></div>
            <div class="argus-dialog-body">
              <form class="grid gap-5" data-site-editor-form data-static-form="#site-editor-success">
                <div class="grid gap-5 sm:grid-cols-[1.1fr_0.9fr]">
                  <div class="argus-field"><label for="site-editor-name">候选AI中转站名称</label><input id="site-editor-name" data-site-editor-name class="argus-input" type="text" value="North Relay"></div>
                  <div class="argus-field"><label for="site-editor-rate">USD 汇率</label><input id="site-editor-rate" data-site-editor-rate class="argus-input" type="number" step="0.01" value="7.20"></div>
                </div>
                <div class="argus-field"><label for="site-editor-url">服务根地址</label><input id="site-editor-url" data-site-editor-url class="argus-input" type="url" value="https://north.example.ai"></div>
                <div class="argus-field"><label for="site-editor-note">内部备注</label><textarea id="site-editor-note" data-site-editor-note class="argus-textarea">适合 Claude 系列测试。</textarea></div>
                <div class="argus-field"><div class="flex items-center gap-2"><input id="site-editor-enabled" data-site-editor-enabled type="checkbox" checked class="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"><label for="site-editor-enabled" class="text-[14px] font-bold text-slate-700">开启自动巡价</label></div><p class="mt-1 pl-6 text-[13px] text-slate-400">关闭后站点进入静默状态，仅保留历史快照供追溯，不再主动更新。</p></div>
                <div class="grid gap-4 sm:grid-cols-2">
                  <p class="text-[13px] font-bold leading-6 text-slate-500" data-site-editor-status>上次成功 12 分钟前，当前快照可继续参与比价。</p>
                  <p class="text-[13px] font-bold leading-6 text-slate-500">当前档案内含 <strong data-site-editor-models>184 个模型</strong> 的最新快照。</p>
                </div>
                <p id="site-editor-success" data-site-editor-success class="argus-hidden rounded-[16px] bg-[#eef8f0] px-4 py-3 text-[13px] font-bold leading-6 text-[#2f6a3d]">候选AI中转站档案已更新，当前页面会继续使用新的名称和参数。</p>
                <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button class="argus-btn argus-btn-secondary" type="button" data-dialog-close>取消</button><button class="argus-btn argus-btn-primary" type="submit">保存档案</button></div>
              </form>
            </div>
          </section>
        </div>
      `);
    }

    if (document.querySelector('[data-dialog-open="login"]')) {
      ensureDialogMarkup('login', `
        <div class="argus-dialog-backdrop" data-dialog="login" aria-hidden="true">
          <section class="argus-dialog" role="dialog" aria-modal="true" aria-labelledby="login-dialog-title">
            <div class="argus-dialog-head"><div><h2 id="login-dialog-title" data-login-heading class="argus-serif text-[26px] font-bold text-slate-900">邮箱登录</h2><p data-login-summary class="mt-2 text-[15px] leading-7 text-slate-500">输入邮箱和验证码后进入当前账户的工作台。这里只做轻量验证，不再切到独立登录页。</p></div><button class="argus-icon-btn" data-dialog-close aria-label="关闭">×</button></div>
            <div class="argus-dialog-body">
              <form class="space-y-5" data-login-form data-static-form="#login-success">
                <div class="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                  <div class="argus-field"><label for="login-email">邮箱地址</label><input id="login-email" name="email" data-login-email-input class="argus-input" type="email" value="hello@example.com"></div>
                  <button class="argus-btn argus-btn-secondary min-h-[56px] rounded-[16px]" type="button" data-login-send-code data-reveal-target="#login-code-sent">发送验证码</button>
                </div>
                <p id="login-code-sent" data-login-code-sent class="argus-hidden rounded-[16px] bg-[#eef8f0] px-4 py-3 text-[13px] font-bold leading-6 text-[#2f6a3d]">验证码已发送到当前邮箱，5 分钟内有效。</p>                <div class="argus-field"><label for="login-code">验证码</label><input id="login-code" data-login-code-input class="argus-input" type="text" inputmode="numeric" value="1024"></div>
                <button class="argus-btn argus-btn-primary w-full rounded-[16px]" data-login-submit type="submit">验证并进入</button>
                <div id="login-success" data-login-success class="argus-hidden space-y-4"><p class="rounded-[16px] bg-[#eef8f0] px-4 py-3 text-[13px] font-bold leading-6 text-[#2f6a3d]">邮箱验证通过，当前会话已恢复。</p><a data-login-next href="sites.html" class="argus-btn argus-btn-dark w-full rounded-[16px]">进入候选AI中转站清单</a></div>
              </form>
            </div>
          </section>
        </div>
      `);
    }
  }

  function updateCompareForm(form) {
    var limit = Number(form.getAttribute('data-plan-limit') || '3');
    var checkboxes = Array.prototype.slice.call(form.querySelectorAll('[data-compare-station]'));
    var selectedCount = checkboxes.filter(function (checkbox) {
      return checkbox.checked;
    }).length;
    var countLabel = form.querySelector('[data-compare-count]');
    var limitLabel = form.querySelector('[data-compare-limit]');
    var submitButton = form.querySelector('[data-compare-submit]');

    if (countLabel) countLabel.textContent = String(selectedCount);
    if (limitLabel) limitLabel.textContent = String(limit);

    checkboxes.forEach(function (checkbox) {
      checkbox.disabled = !checkbox.checked && selectedCount >= limit;
      var choiceCard = checkbox.closest('.argus-choice-card');
      if (choiceCard) {
        choiceCard.classList.toggle('is-selected', checkbox.checked);
        choiceCard.classList.toggle('opacity-60', checkbox.disabled);
      }
    });

    if (submitButton) {
      submitButton.disabled = selectedCount === 0;
      submitButton.classList.toggle('cursor-not-allowed', selectedCount === 0);
      submitButton.classList.toggle('opacity-60', selectedCount === 0);
    }

  }

  function updateSiteDirectoryFilter(directory) {
    var searchInput = directory.querySelector('[data-site-search]');
    var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var visibleCount = 0;

    directory.querySelectorAll('[data-site-row]').forEach(function (row) {
      var matches = !query || (row.getAttribute('data-site-search') || '').toLowerCase().indexOf(query) !== -1;
      row.classList.toggle('argus-hidden', !matches);
      if (matches) visibleCount += 1;
    });

    directory.querySelectorAll('[data-site-visible-count]').forEach(function (target) {
      target.textContent = String(visibleCount);
    });
  }

  function updateSiteDirectoryCompare(directory, options) {
    options = options || {};
    var limit = Number(directory.getAttribute('data-plan-limit') || '3');
    var checkboxes = Array.prototype.slice.call(directory.querySelectorAll('[data-compare-station]'));
    var selected = checkboxes.filter(function (checkbox) {
      return checkbox.checked;
    });
    var selectedIds = selected.map(function (checkbox) {
      return checkbox.value;
    });
    var selectedLabels = selected.map(function (checkbox) {
      return checkbox.getAttribute('data-station-label') || checkbox.value;
    });
    var compareTable = directory.querySelector('[data-inline-compare-table]');
    var emptyState = directory.querySelector('[data-inline-compare-empty]');

    checkboxes.forEach(function (checkbox) {
      checkbox.disabled = !checkbox.checked && selected.length >= limit;
      var row = checkbox.closest('[data-site-row]');
      if (row) {
        row.classList.toggle('is-selected', checkbox.checked);
      }
    });

    directory.querySelectorAll('[data-inline-compare-count]').forEach(function (target) {
      target.textContent = String(selected.length);
    });
    directory.querySelectorAll('[data-inline-compare-limit]').forEach(function (target) {
      target.textContent = String(limit);
    });
    directory.querySelectorAll('[data-inline-selected-list]').forEach(function (target) {
      target.textContent = selectedLabels.length ? selectedLabels.join('、') : '未选择';
    });

    if (compareTable) compareTable.classList.toggle('argus-hidden', selected.length === 0);
    if (emptyState) emptyState.classList.toggle('argus-hidden', selected.length !== 0);

    directory.querySelectorAll('[data-inline-compare-column], [data-inline-compare-cell]').forEach(function (element) {
      var station = element.getAttribute('data-inline-compare-column') || element.getAttribute('data-inline-compare-cell');
      element.classList.toggle('argus-hidden', selectedIds.indexOf(station) === -1);
    });

    if (options.syncStorage !== false) {
      writeStoredCompareSelection(selectedIds, options.markUpdated !== false);
    }
  }

  function initializeSiteDirectory() {
    var directory = document.querySelector('[data-site-directory]');
    if (!directory) return;
    var total = directory.querySelectorAll('[data-site-row]').length;
    var limit = Number(directory.getAttribute('data-plan-limit') || '3');
    var searchInput = directory.querySelector('[data-site-search]');
    var clearButton = directory.querySelector('[data-clear-compare]');
    var storedSelection = readStoredCompareSelection();

    if (storedSelection !== null) {
      var appliedCount = 0;
      directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
        var shouldCheck = storedSelection.indexOf(checkbox.value) !== -1 && appliedCount < limit;
        checkbox.checked = shouldCheck;
        if (shouldCheck) appliedCount += 1;
      });
    }

    directory.querySelectorAll('[data-site-total-count]').forEach(function (target) {
      target.textContent = String(total);
    });

    if (searchInput && !searchInput.dataset.siteBound) {
      searchInput.addEventListener('input', function () {
        updateSiteDirectoryFilter(directory);
      });
      searchInput.dataset.siteBound = 'true';
    }

    if (clearButton && !clearButton.dataset.siteBound) {
      clearButton.addEventListener('click', function (event) {
        event.preventDefault();
        directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
          checkbox.checked = false;
        });
        updateSiteDirectoryCompare(directory);
      });
      clearButton.dataset.siteBound = 'true';
    }

    directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
      if (checkbox.dataset.siteBound) return;
      checkbox.addEventListener('change', function () {
        updateSiteDirectoryCompare(directory);
      });
      checkbox.dataset.siteBound = 'true';
    });

    updateSiteDirectoryFilter(directory);
    updateSiteDirectoryCompare(directory, { syncStorage: false });
  }

  function renderStoredComparisonPage(page, selectedStations, hasStoredSelection) {
    var selectedLabels = selectedStations.map(function (station) {
      return STATION_NAMES[station] || station;
    });
    var compareTable = page.querySelector('[data-synced-compare-table]');
    var emptyState = page.querySelector('[data-synced-compare-empty]');

    page.querySelectorAll('[data-synced-compare-count]').forEach(function (target) {
      target.textContent = String(selectedStations.length);
    });
    page.querySelectorAll('[data-synced-selected-list]').forEach(function (target) {
      target.textContent = selectedLabels.length ? selectedLabels.join('、') : '未选择站点';
    });

    if (compareTable) compareTable.classList.toggle('argus-hidden', selectedStations.length === 0);
    if (emptyState) emptyState.classList.toggle('argus-hidden', selectedStations.length !== 0);

    page.querySelectorAll('[data-synced-compare-column], [data-synced-compare-cell]').forEach(function (element) {
      var station = element.getAttribute('data-synced-compare-column') || element.getAttribute('data-synced-compare-cell');
      element.classList.toggle('argus-hidden', selectedStations.indexOf(station) === -1);
    });
  }

  function syncStoredComparisonPage(page, force) {
    if (!shouldRefreshStoredComparison(force)) return;
    var storedSelection = readStoredCompareSelection();
    var selectedStations = storedSelection === null ? DEFAULT_COMPARE_SELECTION.slice() : storedSelection;
    renderStoredComparisonPage(page, selectedStations, storedSelection !== null);
    clearStoredComparisonFlag();
  }

  function initializeStoredComparisonPage() {
    var page = document.querySelector('[data-synced-comparison-page]');
    if (!page) return;
    syncStoredComparisonPage(page, true);
    window.addEventListener('focus', function () {
      syncStoredComparisonPage(page, false);
    });
  }

  function syncCustomComparisonPage() {
    var selectedStations = normalizeCompareSelection(new URLSearchParams(window.location.search).getAll('compare'), 5);
    if (!selectedStations.length) selectedStations = DEFAULT_COMPARE_SELECTION.slice();

    document.querySelectorAll('[data-custom-selected-count]').forEach(function (target) {
      target.textContent = String(selectedStations.length);
    });
    document.querySelectorAll('[data-compare-column], [data-compare-cell]').forEach(function (element) {
      var station = element.getAttribute('data-compare-column') || element.getAttribute('data-compare-cell');
      element.classList.toggle('argus-hidden', selectedStations.indexOf(station) === -1);
    });
  }

  document.addEventListener('click', function (event) {
    var fetchTrigger = event.target.closest('[data-site-fetch]');
    if (fetchTrigger && document.body.dataset.siteFetchUrl) {
      event.preventDefault();
      fetchTrigger.disabled = true;
      var originalText = fetchTrigger.textContent;
      fetchTrigger.textContent = '采集中';
      postForm(document.body.dataset.siteFetchUrl, { site_id: fetchTrigger.getAttribute('data-site-id') || '' })
        .then(function () {
          window.location.reload();
        })
        .catch(function (error) {
          window.alert(error.message);
          fetchTrigger.disabled = false;
          fetchTrigger.textContent = originalText;
        });
      return;
    }

    var deactivateTrigger = event.target.closest('[data-site-deactivate]');
    if (deactivateTrigger && document.body.dataset.siteDeactivateUrl) {
      event.preventDefault();
      if (!window.confirm('确认移除这个站点？后续会停止自动巡价，历史快照仍会保留。')) return;
      deactivateTrigger.disabled = true;
      postForm(document.body.dataset.siteDeactivateUrl, { site_id: deactivateTrigger.getAttribute('data-site-id') || '' })
        .then(function () {
          window.location.reload();
        })
        .catch(function (error) {
          window.alert(error.message);
          deactivateTrigger.disabled = false;
        });
      return;
    }

    var openTrigger = event.target.closest('[data-dialog-open]');
    if (openTrigger) {
      event.preventDefault();
      var dialogName = openTrigger.getAttribute('data-dialog-open');
      if (dialogName === 'site-editor') {
        populateSiteEditor(openTrigger);
      } else if (dialogName === 'login') {
        populateLoginDialog(openTrigger);
      }
      openDialog(dialogName);
      return;
    }

    var closeTrigger = event.target.closest('[data-dialog-close]');
    if (closeTrigger) {
      event.preventDefault();
      closeDialog(closeTrigger.closest('[data-dialog]'));
      return;
    }

    var backdrop = event.target.closest('[data-dialog]');
    if (backdrop && event.target === backdrop) {
      closeDialog(backdrop);
    }

    var revealTrigger = event.target.closest('[data-reveal-target]');
    if (revealTrigger) {
      var sendCodeTrigger = revealTrigger.closest('[data-login-send-code]');
      if (sendCodeTrigger && document.body.dataset.loginSendUrl) {
        event.preventDefault();
        var loginForm = sendCodeTrigger.closest('[data-login-form]');
        var emailInput = loginForm ? loginForm.querySelector('[data-login-email-input]') : null;
        var codeSent = loginForm ? loginForm.querySelector('[data-login-code-sent]') : null;
        sendCodeTrigger.disabled = true;
        postLoginForm(document.body.dataset.loginSendUrl, { email: emailInput ? emailInput.value : '' })
          .then(function (payload) {
            showLoginStatus(codeSent, payload.message || '验证码已发送，10 分钟内有效。', false);
          })
          .catch(function (error) {
            showLoginStatus(codeSent, error.message, true);
          })
          .finally(function () {
            sendCodeTrigger.disabled = false;
          });
        return;
      }
      event.preventDefault();
      var target = document.querySelector(revealTrigger.getAttribute('data-reveal-target'));
      if (target) target.classList.remove('argus-hidden');
      return;
    }

    var clearCompareTrigger = event.target.closest('[data-clear-compare]');
    if (clearCompareTrigger) {
      if (clearCompareTrigger.dataset.siteBound) return;
      event.preventDefault();
      var directory = clearCompareTrigger.closest('[data-site-directory]') || document.querySelector('[data-site-directory]');
      if (!directory) return;
      directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
        checkbox.checked = false;
      });
      updateSiteDirectoryCompare(directory);
    }
  });

  document.addEventListener('change', function (event) {
    var checkbox = event.target.closest('[data-compare-station]');
    if (checkbox) {
      var form = checkbox.closest('[data-compare-form]');
      if (form) {
        updateCompareForm(form);
        return;
      }
      var directory = checkbox.closest('[data-site-directory]');
      if (directory && !checkbox.dataset.siteBound) updateSiteDirectoryCompare(directory);
      return;
    }
  });

  document.addEventListener('input', function (event) {
    var searchInput = event.target.closest('[data-site-search]');
    if (!searchInput) return;
    if (searchInput.dataset.siteBound) return;
    var directory = searchInput.closest('[data-site-directory]');
    if (directory) updateSiteDirectoryFilter(directory);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('[data-dialog].is-open').forEach(function (dialog) {
      closeDialog(dialog);
    });
  });

  document.addEventListener('submit', function (event) {
    var siteEditorForm = event.target.closest('[data-site-editor-form]');
    if (siteEditorForm && document.body.dataset.siteSaveUrl) {
      event.preventDefault();
      var dialog = siteEditorForm.closest('[data-dialog="site-editor"]');
      var submitButton = siteEditorForm.querySelector('[type="submit"]');
      var success = siteEditorForm.querySelector('[data-site-editor-success]');
      var enabledInput = siteEditorForm.querySelector('[data-site-editor-enabled]');
      if (submitButton) submitButton.disabled = true;
      postForm(document.body.dataset.siteSaveUrl, {
        site_id: dialog ? (dialog.dataset.siteId || '') : '',
        name: (siteEditorForm.querySelector('[data-site-editor-name]') || {}).value || '',
        base_url: (siteEditorForm.querySelector('[data-site-editor-url]') || {}).value || '',
        usd_exchange_rate: (siteEditorForm.querySelector('[data-site-editor-rate]') || {}).value || '',
        note: (siteEditorForm.querySelector('[data-site-editor-note]') || {}).value || '',
        enabled: enabledInput && enabledInput.checked ? '1' : '0'
      }).then(function (payload) {
        showInlineStatus(success, payload.message || '站点档案已保存。', false);
        window.location.reload();
      }).catch(function (error) {
        showInlineStatus(success, error.message, true);
        if (submitButton) submitButton.disabled = false;
      });
      return;
    }

    var loginForm = event.target.closest('[data-login-form]');
    if (loginForm && document.body.dataset.loginVerifyUrl) {
      event.preventDefault();
      var emailInput = loginForm.querySelector('[data-login-email-input]');
      var codeInput = loginForm.querySelector('[data-login-code-input]');
      var success = loginForm.querySelector('[data-login-success]');
      var codeSent = loginForm.querySelector('[data-login-code-sent]');
      postLoginForm(document.body.dataset.loginVerifyUrl, {
        email: emailInput ? emailInput.value : '',
        code: codeInput ? codeInput.value : ''
      }).then(function (payload) {
        showLoginStatus(codeSent, payload.message || '邮箱验证通过，当前会话已恢复。', false);
        if (success) success.classList.remove('argus-hidden');
      }).catch(function (error) {
        showLoginStatus(codeSent, error.message, true);
      });
      return;
    }

    var compareForm = event.target.closest('[data-compare-form]');
    if (compareForm) {
      event.preventDefault();
      var selectedCount = compareForm.querySelectorAll('[data-compare-station]:checked').length;
      if (selectedCount === 0) {
        updateCompareForm(compareForm);
        return;
      }
      var action = compareForm.getAttribute('action') || 'custom-comparison.html';
      var params = new URLSearchParams();
      compareForm.querySelectorAll('[data-compare-station]:checked').forEach(function (checkbox) {
        params.append('compare', checkbox.value);
      });
      window.location.href = action + '?' + params.toString();
      return;
    }

    var form = event.target.closest('[data-static-form]');
    if (!form) return;
    event.preventDefault();
    var targetSelector = form.getAttribute('data-static-form');
    if (!targetSelector) return;
    var target = document.querySelector(targetSelector);
    if (target) target.classList.remove('argus-hidden');
  });

  document.addEventListener('DOMContentLoaded', function () {
    ensureSharedDialogs();
    initializeSiteDirectory();
    initializeStoredComparisonPage();
    document.querySelectorAll('[data-compare-form]').forEach(function (form) {
      updateCompareForm(form);
    });
    syncCustomComparisonPage();
  });
})();