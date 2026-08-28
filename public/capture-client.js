(function () {
  'use strict';

  var API = '/api/capture';
  var LAST_EVENT_KEY = 'aion2_capture_last_event';
  var pollTimer = null;
  var pairingCode = null;

  function injectStyles() {
    var style = document.createElement('style');
    style.textContent = [
      '.tool-btn.capture{color:#b8ffda;border-color:rgba(74,222,128,.35);background:rgba(74,222,128,.08)}',
      '.tool-btn.capture:hover{background:rgba(74,222,128,.16)}',
      '.capture-overlay{position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.62);z-index:1200}',
      '.capture-overlay.show{display:flex}',
      '.capture-box{position:relative;width:min(92vw,480px);padding:22px;border:1px solid var(--border-glow);border-radius:14px;background:var(--bg-card);box-shadow:var(--shadow)}',
      '.capture-box h3{margin:0 32px 10px 0;color:#86efac;font-size:17px}',
      '.capture-close{position:absolute;right:12px;top:10px;border:0;background:transparent;color:var(--text-faint);font-size:22px;cursor:pointer}',
      '.capture-desc{font-size:13px;color:var(--text-dim);line-height:1.7}',
      '.capture-code{margin:18px 0 12px;padding:14px;text-align:center;font:700 28px/1.2 monospace;letter-spacing:7px;color:var(--cyan);background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px}',
      '.capture-status{min-height:20px;margin-top:10px;font-size:12px;color:var(--text-faint)}',
      '.capture-actions{display:flex;gap:8px;margin-top:16px}',
      '.capture-actions button{flex:1;padding:9px;border-radius:8px;border:1px solid var(--border);background:var(--glass-bg);color:var(--text-dim);cursor:pointer}',
      '.capture-actions button.primary{color:#86efac;border-color:rgba(74,222,128,.4);background:rgba(74,222,128,.1)}',
      '.capture-download{display:block;margin-top:14px;padding:10px;text-align:center;text-decoration:none;border:1px solid rgba(34,211,238,.4);border-radius:8px;color:var(--cyan);background:rgba(34,211,238,.08)}'
    ].join('');
    document.head.appendChild(style);
  }

  function injectModal() {
    var overlay = document.createElement('div');
    overlay.id = 'capturePairOverlay';
    overlay.className = 'capture-overlay';
    overlay.innerHTML =
      '<div class="capture-box">' +
        '<button class="capture-close" type="button" aria-label="关闭">×</button>' +
        '<h3>连接数据采集助手</h3>' +
        '<div class="capture-desc">在 Windows 采集助手中输入下方一次性配对码。配对成功后，助手可以按游戏窗口标题匹配角色并提交识别结果。配对码 5 分钟内有效。</div>' +
        '<a class="capture-download" id="captureDownload" href="https://github.com/yuwenzijing/tower2-tracker/releases/download/v1.3.4.1/BuyaliCollector-v1.3.4.1.zip" target="_blank" rel="noopener">下载 Windows 数据采集助手 V1.3.4.1</a>' +
        '<div class="capture-code" id="capturePairCode">------</div>' +
        '<div class="capture-status" id="capturePairStatus"></div>' +
        '<div class="capture-actions">' +
          '<button type="button" id="captureRefreshCode">重新生成</button>' +
          '<button type="button" class="primary" id="captureDone">完成</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
    if (location.hostname === 'test.buyali.xyz') {
      var testDownload = overlay.querySelector('#captureDownload');
      testDownload.removeAttribute('href');
      testDownload.removeAttribute('target');
      testDownload.textContent = 'V1.3.4.1 测试包仅提供本地测试';
      testDownload.style.cursor = 'default';
    }
    overlay.querySelector('.capture-close').onclick = closeCapturePairing;
    overlay.querySelector('#captureDone').onclick = closeCapturePairing;
    overlay.querySelector('#captureRefreshCode').onclick = createPairingCode;
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) closeCapturePairing();
    });
  }

  function status(message, error) {
    var el = document.getElementById('capturePairStatus');
    if (!el) return;
    el.textContent = message || '';
    el.style.color = error ? 'var(--red)' : 'var(--text-faint)';
  }

  async function syncToken() {
    var passphrase = typeof getSyncPassphrase === 'function' ? getSyncPassphrase() : null;
    if (!passphrase) throw new Error('请先设置云同步口令');
    return await hashPassphrase(passphrase);
  }

  async function createPairingCode() {
    status('正在生成配对码…');
    try {
      if (typeof syncPush === 'function') await syncPush();
      var token = await syncToken();
      var response = await fetch(API + '/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Sync-Token': token },
        body: JSON.stringify({ client: location.hostname === 'test.buyali.xyz' ? 'web-v1.3.4.1-test' : 'web-v1.3.4.1' })
      });
      var result = await response.json();
      if (!response.ok) throw new Error(result.error || ('HTTP ' + response.status));
      pairingCode = result.code;
      document.getElementById('capturePairCode').textContent = result.code.replace(/(\d{3})(\d{3})/, '$1 $2');
      status('等待采集助手完成配对…');
    } catch (error) {
      pairingCode = null;
      document.getElementById('capturePairCode').textContent = '------';
      status(error.message || String(error), true);
    }
  }

  window.openCapturePairing = function () {
    var overlay = document.getElementById('capturePairOverlay');
    overlay.classList.add('show');
    createPairingCode();
  };

  function closeCapturePairing() {
    var overlay = document.getElementById('capturePairOverlay');
    if (overlay) overlay.classList.remove('show');
  }

  function latestEventId() {
    return parseInt(localStorage.getItem(LAST_EVENT_KEY) || '0', 10) || 0;
  }

  function rememberEvent(id) {
    localStorage.setItem(LAST_EVENT_KEY, String(id));
  }

  async function pollCaptureEvents() {
    var passphrase = typeof getSyncPassphrase === 'function' ? getSyncPassphrase() : null;
    if (!passphrase || document.hidden) return;
    try {
      var token = await hashPassphrase(passphrase);
      var response = await fetch(API + '/events?after=' + latestEventId(), {
        headers: { 'X-Sync-Token': token }
      });
      if (!response.ok) return;
      var result = await response.json();
      (result.events || []).forEach(applyCaptureEvent);
    } catch (error) {
      console.warn('capture event poll failed', error);
    }
  }

  function applyCaptureEvent(event) {
    if (!event || !event.id || event.id <= latestEventId()) return;
    var baseRevision = typeof getSyncBaseRevision === 'function' ? getSyncBaseRevision() : null;
    var localRevision = DATA && DATA._lastModified;
    var eventRevision = event.data && event.data._lastModified;
    if (baseRevision && localRevision && localRevision !== baseRevision && eventRevision !== localRevision) {
      rememberEvent(event.id);
      if (typeof syncOnLoad === 'function') syncOnLoad();
      return;
    }
    if (typeof syncDebounceTimer !== 'undefined' && syncDebounceTimer) {
      clearTimeout(syncDebounceTimer);
      syncDebounceTimer = null;
    }
    if (event.type === 'applied' && event.data) {
      pushUndo({ transactionId: event.transactionId, source: 'capture' });
      DATA = event.data;
      if (DATA.accounts) DATA.accounts.forEach(ensureAccDefaults);
      dungeonCostHigh = DATA._dungeonCostHigh || false;
      localStorage.setItem('aion2_aion_tracker_v2', JSON.stringify(DATA));
      if (typeof setSyncBaseRevision === 'function') setSyncBaseRevision(DATA._lastModified);
      if (typeof updateSyncStatus === 'function') updateSyncStatus('synced');
      render();
      showToast('采集数据已写入：' + (event.characterName || '当前角色'));
    } else if (event.type === 'reverted' && event.data) {
      var topMeta = undoMetaStack.length ? undoMetaStack[undoMetaStack.length - 1] : null;
      if (topMeta && topMeta.transactionId === event.transactionId) {
        undoStack.pop();
        undoMetaStack.pop();
      }
      DATA = event.data;
      if (DATA.accounts) DATA.accounts.forEach(ensureAccDefaults);
      dungeonCostHigh = DATA._dungeonCostHigh || false;
      localStorage.setItem('aion2_aion_tracker_v2', JSON.stringify(DATA));
      if (typeof setSyncBaseRevision === 'function') setSyncBaseRevision(DATA._lastModified);
      if (typeof updateSyncStatus === 'function') updateSyncStatus('synced');
      render();
      showToast('采集数据已撤回');
    }
    rememberEvent(event.id);
  }

  injectStyles();
  injectModal();
  pollTimer = setInterval(pollCaptureEvents, 2000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) pollCaptureEvents();
  });
  (async function bootstrapCaptureSync() {
    await pollCaptureEvents();
    if (typeof syncOnLoad === 'function') await syncOnLoad();
  })();
})();
