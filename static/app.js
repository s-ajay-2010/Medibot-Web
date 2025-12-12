
const API = (p) => `/api/${p}`;

async function postJSON(path, body){
  const res = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  return res.json();
}
async function getJSON(path){ const res = await fetch(path); return res.json(); }


document.getElementById('btnChat').onclick = async ()=>{
  const txt = document.getElementById('chatInput').value.trim();
  if(!txt) return alert('Type a message');
  const r = await postJSON(API('chat'), {message: txt});
  document.getElementById('chatOut').innerText = r.reply || JSON.stringify(r);
};


document.getElementById('btnSummary').onclick = async ()=>{
  const r = await getJSON(API('daily_summary'));
  document.getElementById('chatOut').innerText = r.summary || JSON.stringify(r);
};


document.getElementById('btnSumm').onclick = async ()=>{
  const t = document.getElementById('reportText').value.trim();
  if(!t) return alert('Paste text');
  const r = await postJSON(API('summarize'), {text: t});
  document.getElementById('summOut').innerText = r.summary || JSON.stringify(r);
};


document.getElementById('btnUpload').onclick = async ()=>{
  const f = document.getElementById('imageFile').files[0];
  if (!f) return alert("Choose image first");

  const fd = new FormData();
  fd.append("image", f);

  const res = await fetch("/api/upload_image", {
    method: "POST",
    body: fd
  });

  const j = await res.json();

  document.getElementById("localOut").innerText =
    j.local_description || "No local analysis";

  document.getElementById("geminiOut").innerText =
    j.gemini_description || "No Gemini output";
};



document.getElementById('btnAnalyzeLocal').onclick = async ()=>{
  const path = document.getElementById('localPath').value.trim();
  if (!path) return alert("Enter path");

  const r = await fetch('/api/analyze_local', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path})
  });
  const j = await r.json();

  document.getElementById("localOut").innerText =
    j.local_description || "N/A";
  document.getElementById("geminiOut").innerText =
    j.gemini_description || "N/A";
};



document.getElementById('btnAddRem').onclick = async ()=>{
  const name = document.getElementById('remName').value, time = document.getElementById('remTime').value;
  if(!name || !time) return alert('fill');
  const r = await postJSON(API('reminder'), {name, time});
  refreshRem();
};

async function refreshRem(){
  const r = await getJSON(API('reminders'));
  const ul = document.getElementById('remList'); ul.innerHTML = '';
  (r.reminders||[]).forEach(x=>{ let li=document.createElement('li'); li.innerText = `${x.name} at ${x.time}`; ul.appendChild(li); });
}
refreshRem();

document.getElementById('btnAddNote').onclick = async ()=>{
  const txt = document.getElementById('noteText').value.trim();
  if(!txt) return alert('type note');
  const r = await postJSON(API('notes'), {content: txt});
  refreshNotes();
};
async function refreshNotes(){
  const r = await getJSON(API('notes'));
  const ul = document.getElementById('noteList'); ul.innerHTML='';
  (r.notes||[]).forEach(n=>{ let li=document.createElement('li'); li.innerText = `${n.content}`; ul.appendChild(li); });
}
refreshNotes();

document.getElementById('btnAddWater').onclick = async ()=>{
  const date = new Date().toISOString().slice(0,10);
  const cur = await getJSON(API('water') + '?date=' + encodeURIComponent(date));
  let count = (cur.count || 0) + 1;
  await postJSON(API('water'), {date, count});
  document.getElementById('waterCount').innerText = count;
};
(async ()=>{ 
  const date = new Date().toISOString().slice(0,10);
  const cur = await getJSON(API('water') + '?date=' + encodeURIComponent(date));
  document.getElementById('waterCount').innerText = (cur.count || 0);
})();
