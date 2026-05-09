(function () {
  var DEFAULT_COMPARE_SELECTION = ['north', 'quiet', 'west'];
  var STATION_NAMES = {
    north: 'North Relay',
    quiet: 'Quiet Gateway',
    south: 'South Bridge',
    west: 'West Meter'
  };
  var COMPARE_SELECTION_STORAGE_KEY = 'argus.compare.selection';
  var COMPARE_SELECTION_UPDATED_KEY = 'argus.compare.selection.updated';

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
      // Ignore storage failures so comparison state never blocks the page.
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
      // Ignore storage failures so comparison state never blocks the page.
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

  function setHomeWatchlistLoading(form, isLoading) {
    var input = form.querySelector('[data-home-watchlist-url]');
    var fieldShell = form.querySelector('[data-home-watchlist-shell]');
    var submitButton = form.querySelector('[data-home-watchlist-submit]');
    var submitLabel = form.querySelector('[data-home-watchlist-label]');
    var spinner = form.querySelector('[data-home-watchlist-spinner]');

    if (input) {
      input.readOnly = isLoading;
      input.setAttribute('aria-disabled', isLoading ? 'true' : 'false');
    }
    if (fieldShell) fieldShell.classList.toggle('argus-field-is-busy', isLoading);
    if (submitButton) submitButton.disabled = isLoading;
    if (submitLabel) submitLabel.textContent = isLoading ? '数据采集中...' : '加入 Watchlist';
    if (spinner) spinner.classList.toggle('argus-hidden', !isLoading);
  }

  function replaceDocumentWithResponse(html, url) {
    document.open();
    document.write(html);
    document.close();
    if (url) window.history.replaceState({}, '', url);
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
      ? '填写站点网址后保存，服务器会读取站点状态并立即采集一次价格。'
      : '保存后会重新读取站点状态，并立即采集一次价格。';

    dialog.dataset.siteId = isCreate ? '' : (trigger.getAttribute('data-site-id') || '');

    setFieldValue(dialog, '[data-site-editor-heading]', title);
    setFieldValue(dialog, '[data-site-editor-summary]', summary);
    setFieldValue(dialog, '[data-site-editor-url]', trigger.getAttribute('data-site-url') || '');
    setFieldValue(dialog, '[data-site-editor-rate]', trigger.getAttribute('data-site-rate') || '');
    setFieldValue(dialog, '[data-site-editor-name]', trigger.getAttribute('data-site-name') || '');

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
    setFieldValue(dialog, '[data-login-email-input]', trigger.getAttribute('data-login-email') || '');
    setFieldValue(dialog, '[data-login-code-input]', trigger.getAttribute('data-login-code') || '');

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

  function populateCheckoutDialog(trigger) {
    var dialog = findDialog('checkout');
    if (!dialog) return;
    var planCode = trigger.getAttribute('data-checkout-plan') || 'pro';
    dialog.dataset.checkoutPlan = planCode;
    dialog.querySelectorAll('[data-checkout-option-card]').forEach(function (card) {
      var isCurrentPlan = card.getAttribute('data-checkout-plan-card') === planCode;
      var isPrimary = card.getAttribute('data-checkout-primary') === 'true';
      card.classList.toggle('argus-hidden', !isCurrentPlan || !isPrimary);
    });
    var option = dialog.querySelector('[data-plan-code="' + planCode + '"][data-billing-cycle="year"]');
    if (option) option.checked = true;
    var moreButton = dialog.querySelector('[data-checkout-more]');
    if (moreButton) {
      var hasMoreOptions = !!dialog.querySelector('[data-checkout-option-card][data-checkout-plan-card="' + planCode + '"]:not([data-checkout-primary="true"])');
      moreButton.classList.toggle('argus-hidden', !hasMoreOptions);
    }
    var result = dialog.querySelector('#order-created');
    if (result) result.classList.add('argus-hidden');
  }

  function ensureSharedDialogs() {
    if (document.querySelector('[data-dialog-open="site-editor"]')) {
      ensureDialogMarkup('site-editor', `
        <div class="argus-dialog-backdrop" data-dialog="site-editor" aria-hidden="true">
          <section class="argus-dialog argus-dialog-lg" role="dialog" aria-modal="true" aria-labelledby="site-editor-title">
            <div class="argus-dialog-head"><div><h2 id="site-editor-title" data-site-editor-heading class="argus-serif text-[26px] font-bold text-slate-900">编辑候选AI中转站</h2><p data-site-editor-summary class="mt-2 text-[15px] leading-7 text-slate-500">保存后会重新读取站点状态，并立即采集一次价格。</p></div><button class="argus-icon-btn" data-dialog-close aria-label="关闭">×</button></div>
            <div class="argus-dialog-body">
              <form class="grid gap-5" data-site-editor-form data-static-form="#site-editor-success">
                <div class="argus-field"><label for="site-editor-url">站点网址 <span class="text-red-500">*</span></label><input id="site-editor-url" data-site-editor-url class="argus-input" type="url" required placeholder="https://1tok.xhh.club/"></div>
                <div class="grid gap-5 sm:grid-cols-[0.8fr_1.2fr]">
                  <div class="argus-field"><label for="site-editor-rate">USD 汇率 <span class="font-medium text-slate-400">可不填</span></label><input id="site-editor-rate" data-site-editor-rate class="argus-input" type="number" min="0" step="0.01" placeholder="1.00"><p class="mt-1 text-[13px] text-slate-400">留空时优先使用站点状态接口返回的汇率。</p></div>
                  <div class="argus-field"><label for="site-editor-name">站点名称 <span class="font-medium text-slate-400">可不填</span></label><input id="site-editor-name" data-site-editor-name class="argus-input" type="text" placeholder="留空则使用 system_name"></div>
                </div>
                <p id="site-editor-success" data-site-editor-success class="argus-hidden rounded-[16px] bg-[#eef8f0] px-4 py-3 text-[13px] font-bold leading-6 text-[#2f6a3d]">候选AI中转站档案已更新。</p>
                <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end"><button class="argus-btn argus-btn-secondary" type="button" data-dialog-close>取消</button><button class="argus-btn argus-btn-primary" type="submit">保存并抓取</button></div>
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
                  <div class="argus-field"><label for="login-email">邮箱地址</label><input id="login-email" name="email" data-login-email-input class="argus-input" type="email" autocomplete="email"></div>
                  <button class="argus-btn argus-btn-secondary min-h-[56px] rounded-[16px]" type="button" data-login-send-code data-reveal-target="#login-code-sent">发送验证码</button>
                </div>
                <p id="login-code-sent" data-login-code-sent class="argus-hidden rounded-[16px] bg-[#eef8f0] px-4 py-3 text-[13px] font-bold leading-6 text-[#2f6a3d]">验证码已发送到当前邮箱，10 分钟内有效。</p>                <div class="argus-field"><label for="login-code">验证码</label><input id="login-code" data-login-code-input class="argus-input" type="text" inputmode="numeric" autocomplete="one-time-code"></div>
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

  function isCompareStationUnavailable(checkbox) {
    var row = checkbox.closest('[data-site-row]');
    return checkbox.hasAttribute('data-compare-unavailable') || (row && row.hasAttribute('data-site-disabled'));
  }

  function updateSiteDirectoryCompare(directory, options) {
    options = options || {};
    var limit = Number(directory.getAttribute('data-plan-limit') || '3');
    var checkboxes = Array.prototype.slice.call(directory.querySelectorAll('[data-compare-station]'));
    var toggle = directory.querySelector('[data-compare-toggle]');
    checkboxes.forEach(function (checkbox) {
      if (isCompareStationUnavailable(checkbox)) checkbox.checked = false;
    });
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
      checkbox.disabled = isCompareStationUnavailable(checkbox) || (!checkbox.checked && selected.length >= limit);
      var row = checkbox.closest('[data-site-row]');
      if (row) {
        row.classList.toggle('is-selected', checkbox.checked);
      }
    });

    if (toggle) {
      var availableCount = checkboxes.filter(function (checkbox) {
        return !isCompareStationUnavailable(checkbox);
      }).length;
      var fullCount = Math.min(limit, availableCount);
      toggle.disabled = fullCount === 0;
      toggle.checked = fullCount > 0 && selected.length >= fullCount;
      toggle.indeterminate = selected.length > 0 && selected.length < fullCount;
    }

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

    directory.querySelectorAll('[data-compare-open]').forEach(function (trigger) {
      var minSelected = Number(trigger.getAttribute('data-min-selected') || '2');
      var isDisabled = selected.length < minSelected;
      trigger.setAttribute('aria-disabled', isDisabled ? 'true' : 'false');
      trigger.tabIndex = isDisabled ? -1 : 0;
    });

    directory.querySelectorAll('[data-inline-compare-column], [data-inline-compare-cell]').forEach(function (element) {
      var station = element.getAttribute('data-inline-compare-column') || element.getAttribute('data-inline-compare-cell');
      element.classList.toggle('argus-hidden', selectedIds.indexOf(station) === -1);
    });

    if (options.syncStorage !== false) {
      writeStoredCompareSelection(selectedIds, options.markUpdated !== false);
    }
  }

  function updateComparisonFilter(container) {
    var searchInput = container.querySelector('[data-comparison-search]');
    var quotaSelect = container.querySelector('[data-comparison-quota-select]');
    var vendorSelect = container.querySelector('[data-comparison-vendor-select]');
    var query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    var quota = quotaSelect ? quotaSelect.value : '';
    var vendor = vendorSelect ? vendorSelect.value : '';
    var visibleCount = 0;
    var rows = Array.prototype.slice.call(document.querySelectorAll('[data-comparison-row]'));

    rows.forEach(function (row) {
      var rowSearch = (row.getAttribute('data-comparison-text') || '').toLowerCase();
      var rowQuota = row.getAttribute('data-comparison-quota') || '';
      var rowVendor = row.getAttribute('data-comparison-vendor') || '';
      var matches = (!query || rowSearch.indexOf(query) !== -1) && (!quota || rowQuota === quota) && (!vendor || rowVendor === vendor);
      row.classList.toggle('argus-hidden', !matches);
      if (matches) visibleCount += 1;
    });

    document.querySelectorAll('[data-comparison-visible-count]').forEach(function (target) {
      target.textContent = String(visibleCount);
    });
    document.querySelectorAll('[data-comparison-total-count]').forEach(function (target) {
      target.textContent = String(rows.length);
    });

    var emptyState = document.querySelector('[data-comparison-empty]');
    if (emptyState) emptyState.classList.toggle('argus-hidden', rows.length === 0 || visibleCount > 0);
  }

  function initializeComparisonFilter() {
    var container = document.querySelector('[data-comparison-filter]');
    if (!container) return;
    container.querySelectorAll('[data-comparison-search], [data-comparison-quota-select], [data-comparison-vendor-select]').forEach(function (control) {
      if (control.dataset.comparisonBound) return;
      var eventName = control.matches('[data-comparison-search]') ? 'input' : 'change';
      control.addEventListener(eventName, function () {
        updateComparisonFilter(container);
      });
      control.dataset.comparisonBound = 'true';
    });
    updateComparisonFilter(container);
  }

  function initializeMobileCollapses() {
    var collapses = Array.prototype.slice.call(document.querySelectorAll('[data-mobile-collapse]'));
    if (!collapses.length || !window.matchMedia) return;
    var media = window.matchMedia('(max-width: 640px)');
    var sync = function () {
      collapses.forEach(function (collapse) {
        collapse.open = !media.matches;
      });
    };
    sync();
    if (media.addEventListener) {
      media.addEventListener('change', sync);
    } else if (media.addListener) {
      media.addListener(sync);
    }
  }

  function initializeSiteDirectory() {
    var directory = document.querySelector('[data-site-directory]');
    if (!directory) return;
    var total = directory.querySelectorAll('[data-site-row]').length;
    var limit = Number(directory.getAttribute('data-plan-limit') || '3');
    var searchInput = directory.querySelector('[data-site-search]');
    var compareToggle = directory.querySelector('[data-compare-toggle]');
    var storedSelection = readStoredCompareSelection();

    if (storedSelection !== null) {
      var appliedCount = 0;
      directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
        var shouldCheck = !isCompareStationUnavailable(checkbox) && storedSelection.indexOf(checkbox.value) !== -1 && appliedCount < limit;
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

    if (compareToggle && !compareToggle.dataset.siteBound) {
      compareToggle.addEventListener('change', function () {
        var shouldSelect = compareToggle.checked;
        var selectedCount = 0;
        directory.querySelectorAll('[data-compare-station]').forEach(function (checkbox) {
          if (shouldSelect && !isCompareStationUnavailable(checkbox) && selectedCount < limit) {
            checkbox.checked = true;
            selectedCount += 1;
          } else {
            checkbox.checked = false;
          }
        });
        updateSiteDirectoryCompare(directory);
      });
      compareToggle.dataset.siteBound = 'true';
    }

    directory.querySelectorAll('[data-compare-open]').forEach(function (trigger) {
      if (trigger.dataset.siteBound) return;
      trigger.addEventListener('click', function (event) {
        if (trigger.getAttribute('aria-disabled') === 'true') event.preventDefault();
      });
      trigger.dataset.siteBound = 'true';
    });

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

  function createWechatIconDataUri() {
    var icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><rect width="96" height="96" rx="24" fill="#07C160"/><path fill="#fff" d="M40 28c-14.4 0-26 9.1-26 20.4 0 6.5 3.9 12.4 10 16.1l-2.2 7.2 8.2-4.3c3.1.9 6.5 1.4 10 1.4 14.4 0 26-9.1 26-20.4S54.4 28 40 28Zm-8.8 16.1a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Zm17.6 0a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Z"/><path fill="#fff" fill-opacity=".92" d="M78.5 58.6c0-9.2-9.6-16.7-21.5-16.7-11.9 0-21.5 7.5-21.5 16.7 0 9.2 9.6 16.7 21.5 16.7 2.6 0 5.1-.3 7.4-1l7.1 3.7-1.9-6c5.4-3.1 8.9-8 8.9-13.4Zm-28.7-4.1a2.9 2.9 0 1 1 0-5.8 2.9 2.9 0 0 1 0 5.8Zm14.6 0a2.9 2.9 0 1 1 0-5.8 2.9 2.9 0 0 1 0 5.8Z"/></svg>';
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(icon);
  }

  function initializeWechatQr() {
    var target = document.querySelector('[data-wechat-qr]');
    if (!target || target.dataset.qrReady === 'true') return;
    var qrUrl = target.getAttribute('data-qr-url') || '';
    if (!qrUrl) return;

    if (!window.QRCodeStyling) {
      target.textContent = 'QR';
      return;
    }

    target.textContent = '';
    var qrCode = new window.QRCodeStyling({
      width: 132,
      height: 132,
      type: 'svg',
      data: qrUrl,
      image: createWechatIconDataUri(),
      margin: 4,
      qrOptions: { errorCorrectionLevel: 'H' },
      dotsOptions: { color: '#1a1a1a', type: 'rounded' },
      cornersSquareOptions: { color: '#1a1a1a', type: 'extra-rounded' },
      cornersDotOptions: { color: '#D97757', type: 'dot' },
      backgroundOptions: { color: '#ffffff' },
      imageOptions: { hideBackgroundDots: true, imageSize: 0.28, margin: 4 }
    });
    qrCode.append(target);
    target.dataset.qrReady = 'true';
  }

  document.addEventListener('click', function (event) {
    var logoutTrigger = event.target.closest('[data-logout-submit]');
    if (logoutTrigger && document.body.dataset.logoutUrl) {
      event.preventDefault();
      logoutTrigger.disabled = true;
      postForm(document.body.dataset.logoutUrl, {})
        .then(function () {
          window.location.href = '/';
        })
        .catch(function (error) {
          window.alert(error.message);
          logoutTrigger.disabled = false;
        });
      return;
    }

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
      if (dialogName === 'checkout' && document.body.dataset.authenticated !== 'true') {
        var loginUrl = document.body.dataset.loginUrl || '/account/login.html';
        window.location.assign(loginUrl + '?next=' + encodeURIComponent(window.location.pathname + window.location.search));
        return;
      }
      if (dialogName === 'site-editor') {
        populateSiteEditor(openTrigger);
      } else if (dialogName === 'login') {
        populateLoginDialog(openTrigger);
      } else if (dialogName === 'checkout') {
        populateCheckoutDialog(openTrigger);
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

    var checkoutMoreTrigger = event.target.closest('[data-checkout-more]');
    if (checkoutMoreTrigger) {
      event.preventDefault();
      var checkoutDialog = checkoutMoreTrigger.closest('[data-dialog="checkout"]');
      var checkoutPlan = checkoutDialog ? (checkoutDialog.dataset.checkoutPlan || 'pro') : 'pro';
      if (checkoutDialog) {
        checkoutDialog.querySelectorAll('[data-checkout-option-card][data-checkout-plan-card="' + checkoutPlan + '"]').forEach(function (card) {
          card.classList.remove('argus-hidden');
        });
      }
      checkoutMoreTrigger.classList.add('argus-hidden');
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

    var addAliasTrigger = event.target.closest('[data-add-alias-row]');
    if (addAliasTrigger) {
      event.preventDefault();
      var aliasList = document.querySelector('[data-alias-list]');
      if (!aliasList) return;
      aliasList.insertAdjacentHTML('beforeend', '<div class="grid gap-3 rounded-[18px] border border-[#e6e6e6] bg-white p-4 sm:grid-cols-[1fr_1fr]"><div class="argus-field"><label>来源模型</label><input name="alias_source" class="argus-input" placeholder="source-model"></div><div class="argus-field"><label>目标模型</label><input name="alias_target" class="argus-input" placeholder="target-model"></div><div class="argus-field sm:col-span-2"><label>备注</label><input name="alias_note" class="argus-input" placeholder="归一化说明"></div></div>');
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
    var homeWatchlistForm = event.target.closest('[data-home-watchlist-form]');
    if (homeWatchlistForm) {
      event.preventDefault();
      setHomeWatchlistLoading(homeWatchlistForm, true);
      fetch(homeWatchlistForm.getAttribute('action') || window.location.href, {
        method: homeWatchlistForm.getAttribute('method') || 'POST',
        body: new FormData(homeWatchlistForm),
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': readCookie('csrftoken') }
      }).then(function (response) {
        if (response.redirected) {
          window.location.assign(response.url);
          return null;
        }
        return response.text().then(function (html) {
          if (response.ok) {
            replaceDocumentWithResponse(html, response.url);
            return;
          }
          replaceDocumentWithResponse(html, window.location.href);
        });
      }).catch(function () {
        setHomeWatchlistLoading(homeWatchlistForm, false);
      });
      return;
    }

    var siteEditorForm = event.target.closest('[data-site-editor-form]');
    if (siteEditorForm && document.body.dataset.siteSaveUrl) {
      event.preventDefault();
      var dialog = siteEditorForm.closest('[data-dialog="site-editor"]');
      var submitButton = siteEditorForm.querySelector('[type="submit"]');
      var success = siteEditorForm.querySelector('[data-site-editor-success]');
      if (submitButton) submitButton.disabled = true;
      postForm(document.body.dataset.siteSaveUrl, {
        site_id: dialog ? (dialog.dataset.siteId || '') : '',
        name: (siteEditorForm.querySelector('[data-site-editor-name]') || {}).value || '',
        base_url: (siteEditorForm.querySelector('[data-site-editor-url]') || {}).value || '',
        usd_exchange_rate: (siteEditorForm.querySelector('[data-site-editor-rate]') || {}).value || ''
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
        var nextLink = loginForm.querySelector('[data-login-next]');
        if (nextLink && !loginForm.closest('[data-dialog="login"]')) {
          window.location.assign(nextLink.getAttribute('href') || '/watchlist/sites.html');
          return;
        }
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

    var checkoutForm = event.target.closest('[data-checkout-form]');
    if (checkoutForm && document.body.dataset.checkoutUrl) {
      event.preventDefault();
      var selectedOption = checkoutForm.querySelector('[name="checkout_option"]:checked');
      var submitButton = checkoutForm.querySelector('[type="submit"]');
      var result = checkoutForm.querySelector('#order-created');
      var message = checkoutForm.querySelector('[data-order-message]');
      var paymentLink = checkoutForm.querySelector('[data-order-payment-link]');
      if (submitButton) submitButton.disabled = true;
      postForm(document.body.dataset.checkoutUrl, {
        plan_code: selectedOption ? selectedOption.getAttribute('data-plan-code') : '',
        billing_cycle: selectedOption ? selectedOption.getAttribute('data-billing-cycle') : '',
        payment_method: 'epay'
      }).then(function (payload) {
        var order = payload.order || {};
        showInlineStatus(message, '订单已创建：' + order.trade_no + '，金额 ¥' + order.amount_rmb + '。' + (payload.message || ''), false);
        if (paymentLink) {
          if (payload.payment_url) {
            paymentLink.href = payload.payment_url;
            paymentLink.classList.remove('argus-hidden');
          } else {
            paymentLink.classList.add('argus-hidden');
            paymentLink.removeAttribute('href');
          }
        }
        if (result) result.classList.remove('argus-hidden');
      }).catch(function (error) {
        showInlineStatus(message, error.message, true);
        if (result) result.classList.remove('argus-hidden');
      }).finally(function () {
        if (submitButton) submitButton.disabled = false;
      });
      return;
    }

    var rulesForm = event.target.closest('[data-rules-form]');
    if (rulesForm && document.body.dataset.rulesSaveUrl) {
      event.preventDefault();
      var rulesSubmit = rulesForm.querySelector('[type="submit"]');
      var rulesStatus = rulesForm.querySelector('[data-rules-status]');
      if (rulesSubmit) rulesSubmit.disabled = true;
      postForm(document.body.dataset.rulesSaveUrl, new FormData(rulesForm))
        .then(function (payload) {
          showInlineStatus(rulesStatus, payload.message || '归一化规则已保存。', false);
        })
        .catch(function (error) {
          showInlineStatus(rulesStatus, error.message, true);
        })
        .finally(function () {
          if (rulesSubmit) rulesSubmit.disabled = false;
        });
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
    initializeMobileCollapses();
    initializeSiteDirectory();
    initializeComparisonFilter();
    initializeStoredComparisonPage();
    initializeWechatQr();
    document.querySelectorAll('[data-compare-form]').forEach(function (form) {
      updateCompareForm(form);
    });
    syncCustomComparisonPage();
  });
})();