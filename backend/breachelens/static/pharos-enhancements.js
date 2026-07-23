(() => {
  'use strict';

  const fmtBytesLocal = (bytes) => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  };

  function ensureEnhancementStyles() {
    if (document.getElementById('pharosEnhancementStyles')) return;
    const style = document.createElement('style');
    style.id = 'pharosEnhancementStyles';
    style.textContent = `
      .pharos-path-row { display:grid; grid-template-columns:1fr auto; gap:8px; }
      .pharos-preview { margin-top:10px; padding:12px; border:1px solid var(--border); border-radius:var(--radius-sm); background:var(--bg); font-size:12px; color:var(--text-muted); }
      .pharos-preview strong { color:var(--text); }
      .pharos-preview ul { margin:8px 0 0 18px; }
      .pharos-preview.good { border-color:rgba(52,211,153,.3); background:rgba(52,211,153,.05); }
      .pharos-preview.bad { border-color:rgba(248,113,113,.3); background:rgba(248,113,113,.05); color:var(--danger); }
      .pharos-inline-actions { display:flex; align-items:center; gap:8px; margin-top:8px; }
    `;
    document.head.appendChild(style);
  }

  function enhanceSourceModal() {
    ensureEnhancementStyles();
    const pathInput = document.getElementById('srcPath');
    if (!pathInput || pathInput.dataset.pharosEnhanced === '1') return;
    pathInput.dataset.pharosEnhanced = '1';
    pathInput.placeholder = 'C:\\Users\\you\\Documents\\datasets';

    const wrapper = document.createElement('div');
    wrapper.className = 'pharos-path-row';
    pathInput.parentNode.insertBefore(wrapper, pathInput);
    wrapper.appendChild(pathInput);

    const browse = document.createElement('button');
    browse.type = 'button';
    browse.className = 'btn btn-ghost';
    browse.textContent = 'Browse…';
    browse.onclick = pickFolder;
    wrapper.appendChild(browse);

    const actions = document.createElement('div');
    actions.className = 'pharos-inline-actions';
    actions.innerHTML = `
      <button type="button" class="btn btn-ghost btn-sm" id="previewSourceBtn">Preview scan</button>
      <span id="sourcePreviewStatus" style="font-size:11px;color:var(--text-dim)">Choose a folder to see what Pharos will index.</span>
    `;
    wrapper.parentNode.appendChild(actions);

    const preview = document.createElement('div');
    preview.id = 'sourcePreview';
    preview.className = 'pharos-preview';
    preview.style.display = 'none';
    actions.parentNode.appendChild(preview);

    document.getElementById('previewSourceBtn').onclick = previewSource;
    pathInput.addEventListener('change', previewSource);
  }

  async function pickFolder() {
    const status = document.getElementById('sourcePreviewStatus');
    if (status) status.textContent = 'Opening Windows folder picker…';
    try {
      const result = await api('/api/sources/pick', { method: 'POST' });
      if (!result.supported) throw new Error(result.error || 'Folder picker unavailable');
      if (result.path) {
        document.getElementById('srcPath').value = result.path;
        await previewSource();
      } else if (status) {
        status.textContent = 'Folder selection cancelled.';
      }
    } catch (error) {
      toast(error.message, 'error');
      if (status) status.textContent = 'You can still paste an absolute folder path.';
    }
  }

  async function previewSource() {
    const path = document.getElementById('srcPath')?.value.trim();
    const exts = document.getElementById('srcExts')?.value.trim();
    const preview = document.getElementById('sourcePreview');
    const status = document.getElementById('sourcePreviewStatus');
    if (!path || !preview) return;

    preview.style.display = 'block';
    preview.className = 'pharos-preview';
    preview.textContent = 'Scanning folder…';
    if (status) status.textContent = 'Checking subfolders and supported files…';

    try {
      const result = await api('/api/sources/preview', {
        method: 'POST',
        body: JSON.stringify({
          path,
          allowed_extensions: exts,
          authorized: true,
          start_indexing: false,
        }),
      });
      preview.className = 'pharos-preview good';
      preview.innerHTML = `
        <strong>${result.files_count.toLocaleString()} supported files</strong> · ${fmtBytesLocal(result.size_bytes)}
        <div style="margin-top:4px">${result.canonical_path}</div>
        ${result.sample_files.length ? `<ul>${result.sample_files.map(name => `<li>${escapeHtml(name)}</li>`).join('')}</ul>` : '<div style="margin-top:8px">No matching files found.</div>'}
      `;
      if (status) status.textContent = result.files_count ? 'Ready to add and index.' : 'No supported files found.';
      return result;
    } catch (error) {
      preview.className = 'pharos-preview bad';
      preview.textContent = error.message;
      if (status) status.textContent = 'Folder cannot be scanned.';
      throw error;
    }
  }

  const originalOpenSourceModal = window.openSourceModal;
  window.openSourceModal = function openSourceModalEnhanced() {
    originalOpenSourceModal?.();
    setTimeout(enhanceSourceModal, 0);
  };

  window.addSource = async function addSourceEnhanced() {
    const path = document.getElementById('srcPath')?.value.trim();
    const mode = document.getElementById('srcMode')?.value;
    const exts = document.getElementById('srcExts')?.value.trim();
    const authorized = document.getElementById('srcAuth')?.checked;
    const button = document.getElementById('addSourceBtn');

    if (!path) return toast('Choose a folder first', 'error');
    if (!authorized) return toast('Confirm that you are authorized to process this folder', 'error');

    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span> Scanning…';
    try {
      const preview = await previewSource();
      if (!preview.files_count) throw new Error('No supported files were found in this folder');
      const result = await api('/api/sources', {
        method: 'POST',
        body: JSON.stringify({
          path,
          storage_mode: mode,
          allowed_extensions: exts,
          authorized: true,
          start_indexing: true,
        }),
      });
      closeSourceModal();
      toast(`Indexing started · ${result.files_found} files found`, 'success');
      showPage('indexing');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = 'Add & index';
    }
  };

  const observer = new MutationObserver(() => {
    if (document.getElementById('sourceModal')?.classList.contains('open')) {
      enhanceSourceModal();
    }
  });
  observer.observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['class'] });

  document.addEventListener('DOMContentLoaded', () => {
    document.title = 'Pharos — Local Intelligence';
    document.querySelectorAll('.sidebar-brand .name, .login-brand h1').forEach((node) => {
      node.innerHTML = node.innerHTML.replace(/BreachLens/g, 'Pharos');
    });
  });
})();
