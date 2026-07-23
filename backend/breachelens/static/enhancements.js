(() => {
  function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
  }

  function installSourceTools() {
    const pathInput = document.getElementById('srcPath');
    const addButton = document.getElementById('addSourceBtn');
    if (!pathInput || !addButton || document.getElementById('pharosBrowseBtn')) return;

    pathInput.placeholder = 'C:\\Users\\you\\Documents\\dataset';

    const browse = document.createElement('button');
    browse.id = 'pharosBrowseBtn';
    browse.type = 'button';
    browse.className = 'btn btn-ghost';
    browse.textContent = 'Browse…';
    browse.style.marginTop = '8px';
    pathInput.insertAdjacentElement('afterend', browse);

    const preview = document.createElement('div');
    preview.id = 'pharosScanPreview';
    preview.style.cssText = 'display:none;padding:10px;margin:10px 0;border:1px solid var(--border);border-radius:5px;font-size:12px;color:var(--text-muted)';
    addButton.parentElement.insertAdjacentElement('beforebegin', preview);

    async function previewFolder() {
      const path = pathInput.value.trim();
      const exts = document.getElementById('srcExts').value.trim();
      if (!path) throw new Error('Choose a folder first');
      preview.style.display = 'block';
      preview.textContent = 'Checking folder…';
      const result = await api('/api/sources/preview', {
        method: 'POST',
        body: JSON.stringify({ path, allowed_extensions: exts })
      });
      pathInput.value = result.canonical_path;
      const warnings = result.errors.length ? ` · ${result.errors.length} access warning(s)` : '';
      preview.innerHTML = `<strong style="color:var(--text)">${result.matching_files.toLocaleString()} matching files</strong> · ${formatSize(result.total_size_bytes)} · ${result.folders_visited.toLocaleString()} folders${warnings}`;
      return result;
    }

    browse.addEventListener('click', async () => {
      try {
        const result = await api('/api/sources/pick-folder', { method: 'POST', body: '{}' });
        if (result.selected && result.path) {
          pathInput.value = result.path;
          await previewFolder();
        }
      } catch (error) {
        toast(error.message, 'error');
      }
    });

    addButton.textContent = 'Add & scan';
    window.addSource = async function addSourceAndScan() {
      const mode = document.getElementById('srcMode').value;
      const exts = document.getElementById('srcExts').value.trim();
      const auth = document.getElementById('srcAuth').checked;
      if (!auth) return toast('Must confirm authorization', 'error');
      addButton.disabled = true;
      try {
        const scan = await previewFolder();
        if (!scan.matching_files) throw new Error('No matching files found. Check the extension list and folder permissions.');
        const source = await api('/api/sources', {
          method: 'POST',
          body: JSON.stringify({
            path: scan.canonical_path,
            storage_mode: mode,
            allowed_extensions: exts,
            authorized: true
          })
        });
        await api(`/api/index/start/${source.id}`, { method: 'POST' });
        closeSourceModal();
        toast('Folder added · indexing started', 'success');
        showPage('indexing');
      } catch (error) {
        toast(error.message, 'error');
      } finally {
        addButton.disabled = false;
      }
    };
  }

  const originalOpen = window.openSourceModal;
  window.openSourceModal = function enhancedOpenSourceModal() {
    originalOpen();
    setTimeout(installSourceTools, 0);
  };

  document.addEventListener('DOMContentLoaded', installSourceTools);
})();
