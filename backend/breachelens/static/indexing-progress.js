async function indexingV2(){
  const m=$('#main');
  try{
    const [s,j]=await Promise.all([api('/api/index/status'),api('/api/index/jobs')]);
    const pct=s?Math.max(0,Math.min(100,Number(s.progress_percent??0))):0;
    const phase=s?String(s.phase||s.status||'indexing').replaceAll('_',' '):'';
    const currentPct=s&&s.current_file_size?Math.min(100,(s.current_file_bytes/s.current_file_size)*100):0;
    const diagnostics=(x)=>(Number(x.warnings_count||0)+Number(x.errors_count||0));
    const eta=s&&s.eta_secs!=null?`${Math.max(0,Math.round(s.eta_secs))}s ETA`:'Calculating ETA…';
    m.innerHTML=`<div class="head"><div><h1>Indexing</h1><p>Streaming, bounded-memory parsing, clean replacement, and live diagnostics.</p></div>${s?'<button class="btn bad" onclick="cancelIndex()">Cancel</button>':''}</div>
      ${s?`<div class="card">
        <div class="row"><div class="grow"><b>${esc(s.current_file||phase)}</b><div class="muted">${esc(phase)}${s.current_line?` · line ${fmt(s.current_line)}`:''}</div></div><strong>${pct.toFixed(pct<1?2:1)}%</strong></div>
        <div class="progress" style="margin:12px 0"><div style="width:${pct}%"></div></div>
        <div class="row muted" style="font-size:12px;margin-bottom:12px"><span>${bytes(s.bytes_processed)} / ${bytes(s.bytes_total)}</span><span class="grow"></span><span>${Number(s.mb_per_sec||0).toFixed(2)} MB/s · ${fmt(Math.round(s.lines_per_sec||0))} records/s · ${eta}</span></div>
        ${s.current_file_size?`<div class="muted" style="font-size:12px;margin-bottom:6px">Current file: ${bytes(s.current_file_bytes)} / ${bytes(s.current_file_size)} (${currentPct.toFixed(1)}%)</div>`:''}
        <div class="grid stats">
          <div class="metric"><span>Completed</span><strong>${s.files_processed}/${s.files_total}</strong></div>
          <div class="metric"><span>Failed</span><strong>${s.files_failed||0}</strong></div>
          <div class="metric"><span>Skipped</span><strong>${s.files_skipped}</strong></div>
          <div class="metric"><span>Records</span><strong>${fmt(s.records_indexed)}</strong></div>
          <div class="metric"><span>Warnings</span><strong>${s.warnings||0}</strong></div>
          <div class="metric"><span>Errors</span><strong>${s.errors||0}</strong></div>
        </div>
      </div>`:''}
      <div class="card tablewrap"><table class="table"><thead><tr><th>Job</th><th>Status</th><th>Completed</th><th>Failed</th><th>Records</th><th>Warnings</th><th>Errors</th><th>Started</th></tr></thead><tbody>${j.map(x=>`<tr><td>#${x.id}</td><td><span class="pill">${esc(x.status)}</span></td><td>${x.files_processed}/${x.files_total}</td><td>${x.files_failed||0}</td><td>${fmt(x.records_indexed)}</td><td>${x.warnings_count||0}</td><td>${diagnostics(x)?`<button class="btn ghost small" onclick="jobErrors(${x.id})">${x.errors_count||0} errors · ${x.warnings_count||0} warnings</button>`:'0'}</td><td>${rel(x.started_at)}</td></tr>`).join('')}</tbody></table></div>`;
    if(s)setTimeout(()=>{const b=$('[data-page=indexing]');if(b&&b.classList.contains('active'))indexingV2()},1000);
  }catch(e){m.innerHTML=`<div class="alert bad">${esc(e.message)}</div>`}
}

async function jobErrorsV2(id){
  try{
    const rows=await api('/api/index/jobs/'+id+'/errors');
    openModal(`<h2>Job #${id} diagnostics</h2>${rows.map(x=>`<div class="alert ${x.severity==='error'?'bad':'warn'}"><b>${esc(x.severity.toUpperCase())}</b> · ${esc(x.file_path)}${x.line_number?` · line ${x.line_number}`:''}<br>${esc(x.message)}</div>`).join('')||'<p>No diagnostics.</p>'}<button class="btn ghost" onclick="closeModal()">Close</button>`);
  }catch(e){toast(e.message)}
}

renders.indexing=indexingV2;
window.indexing=indexingV2;
window.jobErrors=jobErrorsV2;
