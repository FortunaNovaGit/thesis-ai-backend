(function(){
  'use strict';
  if(typeof ThesisAIAdmin === 'undefined') return;
  const $ = (s,root=document)=>root.querySelector(s);
  const $$ = (s,root=document)=>Array.from(root.querySelectorAll(s));
  const app = $('#thesis-ai-app');
  if(!app) return;

  const prompt = $('#thesis-ai-prompt');
  const renderer = $('#thesis-ai-renderer');
  const allowPlugins = $('#thesis-ai-allow-plugins');
  const allowSetup = $('#thesis-ai-allow-setup');
  const count = $('#thesis-ai-prompt-count');
  const autosave = $('#thesis-ai-autosave');
  const errorBox = $('#thesis-ai-build-error');
  const preflightBtn = $('#thesis-ai-preflight');
  const preflightResult = $('#thesis-ai-preflight-result');
  let saveTimer = null;
  let polling = !!ThesisAIAdmin.hasActiveBuild;

  function post(data){
    return fetch(ThesisAIAdmin.ajaxUrl, {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
      body:new URLSearchParams(data).toString()
    }).then(r=>r.json());
  }

  function updateCounter(){ if(prompt && count) count.textContent = (prompt.value || '').length + '/6000'; }
  function scheduleSave(){
    updateCounter();
    if(!prompt || !renderer) return;
    clearTimeout(saveTimer);
    if(autosave){autosave.textContent='Зберігаємо чернетку…';autosave.className='tai-autosave is-saving';}
    saveTimer=setTimeout(async()=>{
      try{
        const json=await post({
          action:'thesis_ai_save_ui_state',nonce:ThesisAIAdmin.uiNonce,
          prompt:prompt.value,renderer:renderer.value,
          allow_approved_plugins:allowPlugins&&allowPlugins.checked?'1':'',
          allow_site_setup:allowSetup&&allowSetup.checked?'1':''
        });
        if(autosave){autosave.textContent=json.success?'Чернетка збережена':'Не вдалося зберегти';autosave.className='tai-autosave '+(json.success?'is-saved':'');}
      }catch(e){ if(autosave){autosave.textContent='Чернетка зберігається при запуску';autosave.className='tai-autosave';} }
    },700);
  }
  [prompt,renderer,allowPlugins,allowSetup].filter(Boolean).forEach(el=>el.addEventListener(el===prompt?'input':'change',scheduleSave));
  updateCounter();

  const stageToStep = stage => {
    stage=(stage||'').toLowerCase();
    if(['completed','quality','verification'].includes(stage)) return 4;
    if(['local_execution','executing','repair','repairing'].includes(stage)) return 3;
    if(['implementation_plan','plan_ready','ready'].includes(stage)) return 2;
    if(stage==='design') return 1;
    return 0;
  };
  const stageLabels={
    queued:'Запит у черзі',starting:'Запускаємо агентів',orchestrator:'Аналіз запиту',architecture:'Архітектура та capabilities',design:'Структура, контент і SEO',implementation_plan:'План WordPress-дій',plan_ready:'План готовий',ready:'План готовий',local_execution:'Створюємо сайт у WordPress',verification:'Перевіряємо результат',quality:'QA та безпека',repair:'Автоматичне виправлення',completed:'Готово'
  };
  function updateSteps(stage){
    const current=stageToStep(stage);
    $$('#thesis-ai-steps li').forEach((li,i)=>{
      li.classList.remove('done','active','waiting');
      li.classList.add(i<current?'done':(i===current?'active':'waiting'));
      const bubble=li.querySelector('span'); if(bubble) bubble.textContent=i<current?'✓':String(i+1);
    });
    const map={orchestrator:0,architect:0,design:1,builder:3,quality:4};
    $$('#thesis-ai-agents .tai-agent').forEach(card=>{
      const idx=map[card.dataset.agent]??0;
      card.classList.remove('done','active','waiting');
      card.classList.add(current>idx?'done':(current===idx?'active':'waiting'));
      const status=card.querySelector('.tai-agent-copy span');
      if(status) status.textContent=current>idx?'Готово':(current===idx?'Працює':'Очікує');
    });
  }
  function updatePlannedPages(build){
    const list=$('#thesis-ai-planned-pages'); if(!list||!build) return;
    const pages=build.bundle&&build.bundle.application_spec&&Array.isArray(build.bundle.application_spec.pages)?build.bundle.application_spec.pages:[];
    if(!pages.length) return;
    list.innerHTML='';
    pages.forEach(page=>{
      const li=document.createElement('li'); const mark=document.createElement('span'); mark.className='tai-checkmark'; mark.textContent='✓';
      const text=document.createElement('span'); text.textContent=page.name||page.title||page.slug||'Сторінка'; li.append(mark,text); list.appendChild(li);
    });
  }
  function renderEvents(events){
    const root=$('#thesis-ai-events'); if(!root||!Array.isArray(events)) return;
    root.innerHTML='';
    if(!events.length){root.innerHTML='<div class="tai-empty">Подій ще немає.</div>';return;}
    events.slice(0,12).forEach(ev=>{
      const row=document.createElement('div'); const type=['info','success','warning','error'].includes(ev.type)?ev.type:'info'; row.className='tai-event '+type;
      const time=document.createElement('time'); try{time.textContent=new Date(ev.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});}catch(e){time.textContent='—';}
      const dot=document.createElement('span');dot.className='tai-event-dot'; const tag=document.createElement('span');tag.className='tai-event-type';tag.textContent=type.toUpperCase(); const p=document.createElement('p');p.textContent=ev.message||'';
      row.append(time,dot,tag,p);root.appendChild(row);
    });
  }
  function updateBuild(build,events){
    if(!build) return;
    const progress=Math.max(0,Math.min(100,parseInt(build.progress||0,10)));
    const bar=$('#thesis-ai-progress-bar'); if(bar) bar.style.width=progress+'%';
    const num=$('#thesis-ai-progress-number'); if(num) num.textContent=progress+'%';
    const stage=build.stage||build.status||'running'; app.dataset.stage=stage; updateSteps(stage);
    const stageEl=$('#thesis-ai-build-stage'); if(stageEl) stageEl.textContent=stageLabels[stage]||stage;
    const detail=$('#thesis-ai-build-detail'); if(detail) detail.textContent=build.detail||'';
    const pill=$('#thesis-ai-build-pill'); if(pill) pill.textContent=(build.status==='completed'||build.reload)?'Завершено':'У процесі';
    updatePlannedPages(build); renderEvents(events);
    if(errorBox){errorBox.hidden=true;errorBox.textContent='';}
  }

  async function poll(){
    if(!polling) return;
    try{
      const json=await post({action:'thesis_ai_build_status',nonce:ThesisAIAdmin.statusNonce});
      if(json.success){
        const payload=json.data||{}; const build=payload.build||{}; updateBuild(build,payload.events||[]);
        if(build.reload||build.status==='completed'){
          polling=false; setTimeout(()=>window.location.reload(),650); return;
        }
      }else{
        const payload=json.data||{};
        if(errorBox){errorBox.hidden=false;errorBox.textContent=payload.message||ThesisAIAdmin.labels.pollError;}
        if(payload.active_build && payload.active_build.job_id){ updateBuild(payload.active_build,payload.events||[]); }
        else { polling=false; setTimeout(()=>window.location.reload(),1200); return; }
      }
    }catch(e){ if(errorBox){errorBox.hidden=false;errorBox.textContent=ThesisAIAdmin.labels.pollError+' '+e.message;} }
    if(polling) setTimeout(poll,Math.max(1000,parseInt(ThesisAIAdmin.pollMs||1400,10)));
  }
  if(polling) setTimeout(poll,650);

  if(preflightBtn){
    preflightBtn.addEventListener('click',async()=>{
      preflightBtn.disabled=true; const old=preflightBtn.textContent; preflightBtn.textContent=ThesisAIAdmin.labels.preflightRunning;
      try{
        const json=await post({action:'thesis_ai_preflight',nonce:ThesisAIAdmin.preflightNonce});
        if(preflightResult){
          preflightResult.hidden=false;
          preflightResult.textContent=json.success?`${ThesisAIAdmin.labels.preflightDone}: ${json.data.pages||0} сторінок · ${json.data.plugins||0} plugins · ${json.data.themes||0} themes`:(json.data&&json.data.message?json.data.message:'Preflight failed');
        }
      }catch(e){ if(preflightResult){preflightResult.hidden=false;preflightResult.textContent='Preflight error: '+e.message;} }
      preflightBtn.disabled=false;preflightBtn.textContent=old;
    });
  }
})();
