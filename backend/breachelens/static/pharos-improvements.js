(() => {
  'use strict';

  const DEFAULT_EXTENSIONS = '.txt,.csv,.tsv,.log,.jsonl,.json,.sql,.lst,.dat';
  let previewTimer = null;

  function safe(value) {
    const text = value == null ? '' : String(value);
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function statusBadge(status) {
    if (status === 'indexed') return 'badge-success';
    if (status === 'indexing' || status === 'running' || status === 'cancelling') return 'badge-accent';
    if (status === 'indexed_with_errors') return 'badge-warning';
    if (status === 'error' || status === 'failed') return 'badge-danger';
    return 'badge-muted';
  }

  function sourceModal() {
    return document.getElementById('sourceModal');
  }

  function ensureSourceEnhancements() {
    const modal = sourceModal();
    const pathInput = document.getElementById('srcPath');
    const extensionsInput = document.getElementById('srcExts');
    if (!modal || !pathInput || !extensionsInput || modal.dataset.pharosEnhanced === '1') return;

    modal.dataset.pharosEnhanced = '1';
    pathInput.placeholder = 'C:\\Users\\you\\Documents\\datasets';
    extensionsInput.value = DEFAULT_EXTENSIONS;

    const pathField = pathInput.closest('.field');
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex;gap:8px;align-items:center;';
    pathInput.parentNode.insertBefore(wrapper, pathInput);
    wrapper.appendChild(pathInput);

    const browse = document.createElement('button');
    browse.type = 'button';
    browse.id = 'browseSourceBtn';
    browse.className = 'btn btn-ghost';
    browse.textContent = 'Browse';
    browse.style.whiteSpace = 'nowrap';
    browse.addEventListener('click', browseSourceFolder);
    wrapper.appendChild(browse);

    const hint = document.createElement('div');
    hint.style.cssText = 'font-size:10px;color:var(--text-dim);margin-top:6px;line-height:1.5;';
    hint.textContent = 'Choose a local folder. Pharos scans supported files recursively and skips hidden folders, symlinks, and oversized files.';
    pathField.appendChild(hint);

    const preview = document.createElement('div');
    preview.id = 'sourcePreview';
    preview.style.cssText = 'display:none;margin:12px 0;padding:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);font-size:11px;line-height:1.55;';
    extensionsInput.closest('.field').after(preview);

    const addButton = document.getElementById('addSourceBtn');
    if (addButton) addButton.textContent = 'Add & scan';

    const schedulePreview = () => {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(() => previewSourceFolder(false), 350);
    };
    pathInput.addEventListener('change', schedulePreview);
    pathInput.addEventListener('blur', schedulePreview);
    extensionsInput.addEventListener('change', schedulePreview);
  }

  async function browseSourceFolder() {
    ensureSourceEnhancements();
    const button = document.getElementById('browseSourceBtn');
    if (button) {
      button.disabled = true;
      button.innerHTML = '<span class="spinner"></span> Opening…';
    }
    try {
      const result = await api('/api/system/pick-folder', { method: 'POST' });
      if (!result.selected) return;
      document.getElementById('srcPath').value = result.path;
      await previewSourceFolder(true);
    } catch (error) {
      toast(error.message || 'Could not open folder picker', 'error');
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = 'Browse';
      }
    }
  }

  async function previewSourceFolder(showErrors = true) {
    ensureSourceEnhancements();
    const path = document.getElementById('srcPath')?.value.trim();
    const extensions = document.getElementById('srcExts')?.value.trim() || DEFAULT_EXTENSIONS;
    const preview = document.getElementById('sourcePreview');
    if (!path || !preview) return null;

    preview.style.display = 'block';
    preview.innerHTML = '<span class="spinner"></span> Checking folder…';
    try {
      const result = await api('/api/sources/scan-preview', {
        method: 'POST',
        body: JSON.stringify({ path, allowed_extensions: extensions }),
      });
      document.getElementById('srcPath').value = result.canonical_path;

      const extensionSummary = Object.entries(result.extension_counts || {})
        .map(([extension, count]) => `.${safe(extension)} <strong>${fmt(count)}</strong>`)
        .join(' · ') || 'none';
      const samples = (result.sample_files || []).map(file => `<div class="mono" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${safe(file)}</div>`).join('');
      const warnings = (result.warnings || []).map(message => `<div style="color:var(--warning);">⚠ ${safe(message)}</div>`).join('');
      const empty = result.files_count === 0
        ? '<div style="color:var(--danger);font-weight:600;margin-top:8px;">No supported readable files were found. Check the extensions or choose another folder.</div>'
        : '';

      preview.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
          <strong>${fmt(result.files_count)} matching file${result.files_count === 1 ? '' : 's'}</strong>
          <span class="mono" style="color:var(--text-muted);">${fmtBytes(result.size_bytes)}</span>
        </div>
        <div style="color:var(--text-muted);margin-top:4px;">${extensionSummary}</div>
        ${result.skipped_large_files ? `<div style="color:var(--warning);margin-top:4px;">${fmt(result.skipped_large_files)} oversized file(s) skipped</div>` : ''}
        ${warnings}
        ${empty}
        ${samples ? `<details style="margin-top:8px;"><summary style="cursor:pointer;color:var(--text-muted);">Sample files</summary><div style="margin-top:6px;">${samples}</div></details>` : ''}
      `;
      return result;
    } catch (error) {
      preview.innerHTML = `<div style="color:var(--danger);">${safe(error.message)}</div>`;
      if (showErrors) toast(error.message, 'error');
      return null;
    }
  }

  window.openSourceModal = function openSourceModalEnhanced() {
    const modal = sourceModal();
    if (!modal) return;
    modal.classList.add('open');
    ensureSourceEnhancements();
    const preview = document.getElementById('sourcePreview');
    if (preview) {
      preview.style.display = 'none';
      preview.innerHTML = '';
    }
    setTimeout(() => document.getElementById('srcPath')?.focus(), 0);
  };

  window.addSource = async function addSourceEnhanced() {
    ensureSourceEnhancements();
    const path = document.getElementById('srcPath').value.trim();
    const storageMode = document.getElementById('srcMode').value;
    const extensions = document.getElementById('srcExts').value.trim() || DEFAULT_EXTENSIONS;
    const authorized = document.getElementById('srcAuth').checked;
    const button = document.getElementById('addSourceBtn');

    if (!path) return toast('Choose a folder first', 'error');
    if (!authorized) return toast('Confirm that you are authorized to process this folder', 'error');

    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span> Checking…';
    try {
      const preview = await previewSourceFolder(true);
      if (!preview || preview.files_count === 0) return;

      button.innerHTML = '<span class="spinner"></span> Starting scan…';
      const result = await api('/api/sources', {
        method: 'POST',
        body: JSON.stringify({
          path: preview.canonical_path,
          storage_mode: storageMode,
          allowed_extensions: extensions,
          authorized: true,
          auto_index: true,
        }),
      });

      closeSourceModal();
      document.getElementById('srcAuth').checked = false;
      toast(result.job_id ? 'Folder added — indexing started' : (result.warning || 'Folder added'), result.warning ? 'error' : 'success');
      showPage(result.job_id ? 'indexing' : 'sources');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = 'Add & scan';
    }
  };

  window.removeSource = async function removeSource(id, name) {
    if (!confirm(`Remove “${name}” from Pharos?\n\nThe original files will not be deleted. Only Pharos index data is removed.`)) return;
    try {
      await api(`/api/sources/${id}`, { method: 'DELETE' });
      toast('Source removed', 'success');
      renderSources();
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  window.renderSources = async function renderSourcesEnhanced() {
    const main = document.getElementById('mainContent');
    try {
      const sources = await api('/api/sources');
      main.innerHTML = `
        <div class="page-header">
          <h2>Sources</h2>
          <p>Choose folders, preview supported files, and scan them into the local index.</p>
          <div class="actions"><button class="btn" onclick="openSourceModal()">+ Add & scan folder</button></div>
        </div>
        <div class="alert alert-warning">
          <span>⚠</span>
          <div><strong>Authorized datasets only.</strong> Pharos reads local files but never uploads them. You remain responsible for having permission to process each source.</div>
        </div>
        <div class="card" style="padding:0;">
          <div class="table-wrap">
            <table>
              <thead><tr><th>Folder</th><th>Status</th><th>Files</th><th>Records</th><th>Size</th><th>Last indexed</th><th></th></tr></thead>
              <tbody>
                ${sources.map(source => `
                  <tr>
                    <td style="max-width:340px;">
                      <div style="font-weight:600;">${safe(source.display_name || source.path)}</div>
                      <div class="mono" style="font-size:10px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${safe(source.path)}">${safe(source.path)}</div>
                      ${source.last_error ? `<div style="font-size:10px;color:var(--warning);margin-top:4px;white-space:normal;">${safe(source.last_error)}</div>` : ''}
                    </td>
                    <td><span class="badge ${statusBadge(source.status)}">${safe(source.status)}</span></td>
                    <td class="mono tnum">${fmt(source.files_count)}</td>
                    <td class="mono tnum">${fmt(source.records_count)}</td>
                    <td class="mono tnum">${fmtBytes(source.size_bytes)}</td>
                    <td style="color:var(--text-muted)">${fmtRelative(source.last_indexed_at)}</td>
                    <td>
                      <div style="display:flex;gap:6px;justify-content:flex-end;">
                        <button class="btn btn-ghost btn-sm" onclick="reindexSource(${source.id})">Scan</button>
                        <button class="btn btn-ghost btn-sm" onclick="removeSource(${source.id}, ${JSON.stringify(source.display_name || source.path).replace(/"/g, '&quot;')})" style="color:var(--danger);">Remove</button>
                      </div>
                    </td>
                  </tr>
                `).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);padding:28px;">No folders yet. Click “Add & scan folder” to begin.</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>
      `;
    } catch (error) {
      main.innerHTML = `<div class="error-msg">${safe(error.message)}</div>`;
    }
  };

  window.showJobErrors = async function showJobErrors(jobId) {
    try {
      const errors = await api(`/api/index/jobs/${jobId}/errors`);
      if (!errors.length) return toast('No file-level errors for this job', 'success');
      const text = errors.slice(0, 20).map(item => `${item.severity.toUpperCase()}: ${item.file_path}\n${item.message}`).join('\n\n');
      alert(text);
    } catch (error) {
      toast(error.message, 'error');
    }
  };

  window.renderIndexing = async function renderIndexingEnhanced() {
    const main = document.getElementById('mainContent');
    try {
      const [status, jobs] = await Promise.all([
        api('/api/index/status'),
        api('/api/index/jobs'),
      ]);

      let statusHtml = '';
      if (status) {
        const completed = (status.files_processed || 0) + (status.files_skipped || 0);
        const percentage = status.files_total > 0 ? Math.min(100, Math.round(completed / status.files_total * 100)) : 0;
        statusHtml = `
          <div class="card">
            <div class="card-title">
              <span class="spinner"></span>
              Active job — #${status.job_id}
              <span class="badge ${statusBadge(status.status)}" style="margin-left:auto;">${safe(status.status)}</span>
            </div>
            <div class="mono" style="font-size:11px;color:var(--text-muted);margin-bottom:8px;max-width:760px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${safe(status.current_file || '')}">${safe(status.current_file || 'Scanning folders…')}</div>
            <div class="progress-bar"><div class="fill" style="width:${percentage}%"></div></div>
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-top:6px;">
              <span class="mono tnum">${completed}/${status.files_total} files (${percentage}%) · ${status.files_skipped || 0} unchanged</span>
              <span class="mono tnum">ETA ${status.eta_secs ? Math.round(status.eta_secs) + 's' : '—'}</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px;">
              <div style="text-align:center;padding:10px;background:var(--bg);border-radius:5px;"><div style="font-size:10px;color:var(--text-muted);">NEW RECORDS</div><div class="mono tnum" style="font-size:16px;font-weight:600;">${fmt(status.records_indexed)}</div></div>
              <div style="text-align:center;padding:10px;background:var(--bg);border-radius:5px;"><div style="font-size:10px;color:var(--text-muted);">RECORDS/SEC</div><div class="mono tnum" style="font-size:16px;font-weight:600;">${fmt(Math.round(status.lines_per_sec || 0))}</div></div>
              <div style="text-align:center;padding:10px;background:var(--bg);border-radius:5px;"><div style="font-size:10px;color:var(--text-muted);">MB/SEC</div><div class="mono tnum" style="font-size:16px;font-weight:600;">${Number(status.mb_per_sec || 0).toFixed(1)}</div></div>
              <div style="text-align:center;padding:10px;background:var(--bg);border-radius:5px;"><div style="font-size:10px;color:var(--text-muted);">WARNINGS</div><div class="mono tnum" style="font-size:16px;font-weight:600;color:${status.errors > 0 ? 'var(--warning)' : 'var(--text)'};">${status.errors || 0}</div></div>
            </div>
          </div>
        `;
      }

      main.innerHTML = `
        <div class="page-header">
          <h2>Indexing</h2>
          <p>Live folder scanning, file processing, and diagnostic history.</p>
          <div class="actions">${status ? '<button class="btn btn-danger" onclick="cancelIndexing()">Cancel current</button>' : ''}</div>
        </div>
        ${statusHtml}
        <div class="card" style="padding:0;">
          <div class="card-title" style="padding:20px 20px 0;">Job history</div>
          <div class="table-wrap" style="margin-top:10px;">
            <table>
              <thead><tr><th>Job</th><th>Status</th><th>Processed</th><th>Unchanged</th><th>New records</th><th>Issues</th><th>Started</th></tr></thead>
              <tbody>
                ${jobs.map(job => `
                  <tr>
                    <td class="mono">#${job.id}</td>
                    <td><span class="badge ${statusBadge(job.status)}">${safe(job.status)}</span></td>
                    <td class="mono tnum">${fmt(job.files_processed || 0)}</td>
                    <td class="mono tnum">${fmt(job.files_skipped || 0)}</td>
                    <td class="mono tnum">${fmt(job.records_indexed || 0)}</td>
                    <td>${job.errors_count ? `<button class="btn btn-ghost btn-sm" onclick="showJobErrors(${job.id})" style="color:var(--warning);">${job.errors_count} · details</button>` : '<span style="color:var(--text-dim);">0</span>'}${job.error_message ? `<div style="font-size:10px;color:var(--danger);max-width:280px;white-space:normal;">${safe(job.error_message)}</div>` : ''}</td>
                    <td style="color:var(--text-muted)">${fmtRelative(job.started_at)}</td>
                  </tr>
                `).join('') || '<tr><td colspan="7" style="text-align:center;color:var(--text-dim);padding:24px;">No indexing jobs yet</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>
      `;

      if (status) {
        setTimeout(() => {
          if (document.querySelector('[data-page="indexing"]')?.classList.contains('active')) renderIndexing();
        }, 1500);
      }
    } catch (error) {
      main.innerHTML = `<div class="error-msg">${safe(error.message)}</div>`;
    }
  };

  ensureSourceEnhancements();
})();
