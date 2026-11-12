const state = {page:'dashboard', routes:[], vehicles:[], trips:[], dashboard:null, formType:'count'};
const $ = selector => document.querySelector(selector);
const $$ = selector => Array.from(document.querySelectorAll(selector));
const fmt = n => Number(n || 0).toLocaleString('ru-RU');
const html = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shortDate = s => {const p=String(s).split('-'); return p.length===3 ? `${p[2]}.${p[1]}` : s;};
const longDate = s => {const p=String(s).split('-'); return p.length===3 ? `${p[2]}.${p[1]}.${p[0]}` : s;};
const localDate = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
let toastTimeout;

function showToast(message, error=false){
  const target=$('#toast');target.textContent=message;target.className=error?'show error':'show';
  clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>target.className='',3300);
}
async function request(path, options={}){
  const headers=Object.assign({'Accept':'application/json'},options.headers||{});
  if(options.body)headers['Content-Type']='application/json';
  if(options.method==='POST'&&sessionStorage.getItem('transport_admin_token'))headers['X-Admin-Token']=sessionStorage.getItem('transport_admin_token');
  const res=await fetch(path,{...options,headers});
  let body;
  try{body=await res.json();}catch(e){throw Error('Server javobi o‘qilmadi.');}
  if(res.status===403&&options.method==='POST'&&!options.retried){
    const token=prompt('Ma’lumot kiritish parolini yozing:');
    if(token){sessionStorage.setItem('transport_admin_token',token);return request(path,{...options,retried:true});}
  }
  if(!res.ok)throw Error(body.error||'Xatolik yuz berdi.');
  return body;
}
function currentQuery(){
  const p=new URLSearchParams({from:$('#dateFrom').value,to:$('#dateTo').value});
  if($('#routeFilter').value)p.set('route_id',$('#routeFilter').value);
  return p.toString();
}
async function loadData(){
  try{
    const [routes,vehicles,trips,dashboard]=await Promise.all([
      request('/api/routes'),request('/api/vehicles'),request('/api/trips'),request('/api/dashboard?'+currentQuery())
    ]);
    Object.assign(state,{routes,vehicles,trips,dashboard});
    renderRouteOptions();renderDashboard();renderRoutes();renderTrips();
  }catch(e){showToast(e.message,true);}
}
function renderRouteOptions(){
  const element=$('#routeFilter'), old=element.value;
  element.innerHTML='<option value="">Barcha yo‘nalishlar</option>'+state.routes.map(r=>`<option value="${r.id}">${html(r.code)} — ${html(r.name)}</option>`).join('');
  if(state.routes.some(r=>String(r.id)===old))element.value=old;
}
function renderDashboard(){
  const d=state.dashboard;if(!d)return;
  $('#kpiPassengers').textContent=fmt(d.summary.passengers);
  $('#kpiTrips').textContent=fmt(d.summary.trips);
  $('#kpiOccupancy').textContent=d.summary.occupancy+'%';
  $('#kpiPeak').textContent=d.summary.peak_hour;
  $('#periodLabel').textContent=`${longDate(d.dates.from)} – ${longDate(d.dates.to)}`;
  renderDaily(d.daily);renderHourly(d.hourly);renderRouteChart(d.routes);renderRecent(d.recent);
}
function renderDaily(days){
  const el=$('#dailyChart');
  if(!days.length){el.innerHTML='<p class="empty">Bu davr uchun qaydlar mavjud emas.</p>';return;}
  const max=Math.max(1,...days.map(x=>x.passengers));
  const list=days.length>16?days.filter((x,i)=>i%Math.ceil(days.length/16)===0||i===days.length-1):days;
  el.innerHTML=list.map(x=>`<div class="bar-col" title="${html(longDate(x.date))}: ${fmt(x.passengers)}"><span class="bar-num">${fmt(x.passengers)}</span><span class="bar-track"><span class="bar-fill" style="height:${Math.round(x.passengers*100/max)}%"></span></span><span class="bar-label">${shortDate(x.date)}</span></div>`).join('');
}
function renderHourly(hours){
  const el=$('#hourlyChart');
  if(!hours.length){el.innerHTML='<p class="empty">Soatlar bo‘yicha ma’lumot yo‘q.</p>';return;}
  const max=Math.max(1,...hours.map(x=>x.passengers));
  el.innerHTML=hours.map(x=>`<div class="hour-line"><span class="hour-title">${html(x.hour)}</span><div class="hour-track"><div class="hour-fill" style="width:${Math.round(x.passengers*100/max)}%"></div></div><span class="hour-value">${fmt(x.passengers)}</span></div>`).join('');
}
function renderRouteChart(routes){
  const el=$('#routeChart');
  if(!routes.length){el.innerHTML='<p class="empty">Ma’lumot topilmadi.</p>';return;}
  const max=Math.max(1,...routes.map(x=>x.passengers));
  el.innerHTML=routes.map(x=>`<div class="route-line"><div class="route-line-top"><strong>${html(x.code)} · ${html(x.name)}</strong><span>${fmt(x.passengers)}</span></div><div class="route-track"><div class="route-fill" style="--fill:${html(x.color)};width:${Math.round(x.passengers*100/max)}%"></div></div></div>`).join('');
}
function status(s){return s==='yakunlangan'?'<span class="status">Yakunlangan</span>':'<span class="status pending">Rejada</span>';}
function renderRecent(rows){
  $('#recentTable').innerHTML=rows.length?rows.map(t=>`<tr><td>${html(shortDate(t.date))} · ${html(t.time)}</td><td class="table-route">${html(t.code)} · ${html(t.route)}</td><td>${html(t.vehicle)}</td><td>${fmt(t.boarding)}</td><td>${status(t.status)}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">Qatnov topilmadi.</td></tr>';
}
function renderRoutes(){
  $('#routeCards').innerHTML=state.routes.length?state.routes.map(r=>`<article class="route-card"><div class="route-card-top"><span class="route-number">${html(r.code)}</span><span class="status">${r.active?'Faol':'To‘xtatilgan'}</span></div><h3>${html(r.name)}</h3><p>${html(r.origin)} – ${html(r.destination)}</p>${r.stops.map(s=>`<div class="route-stop"><span class="stop-dot"></span><span class="stop-name">${html(s.name)}</span></div>`).join('')}<div class="route-card-foot"><span>${r.stops.length} ta bekat</span><span>${r.vehicles} ta transport</span></div></article>`).join(''):'<p class="empty">Yo‘nalishlar hali kiritilmagan.</p>';
}
function renderTrips(){
  $('#allTripsTable').innerHTML=state.trips.length?state.trips.map(t=>`<tr><td>${html(longDate(t.service_date))}</td><td>${html(t.departure_time)}</td><td class="table-route">${html(t.code)} · ${html(t.route)}</td><td>${html(t.vehicle)}</td><td>${fmt(t.passengers)}</td><td>${status(t.status)}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">Qatnovlar ro‘yxati bo‘sh.</td></tr>';
}
function switchPage(page){
  state.page=page;
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  $$('.page').forEach(p=>p.classList.toggle('hidden',p.id!==page+'Page'));
  $('#filters').style.display=page==='dashboard'?'flex':'none';
  const titles={dashboard:['Umumiy tahlil','Yo‘lovchilar oqimi va qatnovlar bo‘yicha umumiy ma’lumotlar.'],routes:['Yo‘nalishlar','Yo‘nalishlar, bekatlar va transportlar haqida ma’lumot.'],trips:['Qatnovlar','Transport qatnovlari va yo‘lovchilar hisobini boshqarish.']};
  $('#pageTitle').textContent=titles[page][0];
  $('#pageDescription').textContent=titles[page][1];
  $('#newEntry').textContent=page==='dashboard'?'+ Ma’lumot kiritish':page==='routes'?'+ Yo‘nalish':'+ Qatnov';
}
function optionList(items,value='id',title='name'){
  return items.map(x=>`<option value="${html(x[value])}">${html(x[title])}</option>`).join('');
}
function field(name,label,type='text',options='',value=''){
  const input=type==='select'?`<select name="${name}" id="f_${name}" required>${options}</select>`:`<input id="f_${name}" name="${name}" type="${type}" value="${html(value)}" ${type==='number'?'min="0" step="1"':''} required>`;
  return `<div class="form-row"><label for="f_${name}">${label}</label>${input}</div>`;
}
function routeOptions(){return state.routes.map(x=>`<option value="${x.id}">${html(x.code)} · ${html(x.name)}</option>`).join('');}
function vehicleOptions(routeId){return state.vehicles.filter(v=>!routeId||Number(v.route_id)===Number(routeId)).map(v=>`<option value="${v.id}">${html(v.fleet_no)} · ${v.capacity} o‘rin</option>`).join('');}
async function changeTripStops(){
  const tripId=$('#f_trip_id')?.value;
  if(!tripId)return;
  try{
    const stops=await request('/api/counts?trip_id='+encodeURIComponent(tripId));
    const sel=$('#f_stop_id');
    sel.innerHTML=stops.map(s=>`<option value="${s.stop_id}">${html(s.name)}</option>`).join('');
    sel.dataset.stops=JSON.stringify(stops);
    fillExistingCount();
  }catch(e){showToast(e.message,true);}
}
function fillExistingCount(){
  const el=$('#f_stop_id');if(!el||!el.dataset.stops)return;
  const stop=JSON.parse(el.dataset.stops).find(s=>String(s.stop_id)===el.value);
  if(stop){$('#f_boarded').value=stop.boarded;$('#f_alighted').value=stop.alighted;}
}
function openForm(type){
  state.formType=type;
  const titles={route:'Yangi yo‘nalish',vehicle:'Yangi transport',trip:'Yangi qatnov',count:'Yo‘lovchilar hisobi'};
  $('#dialogTitle').textContent=titles[type];
  let fields='';
  if(type==='route'){
    fields=field('code','Yo‘nalish raqami')+field('name','Yo‘nalish nomi')+field('origin','Boshlang‘ich bekat')+field('destination','Oxirgi bekat');
  }else if(type==='vehicle'){
    fields=field('route_id','Yo‘nalish','select',routeOptions())+field('fleet_no','Transport raqami')+field('capacity','O‘rindiq va yo‘lovchi sig‘imi','number','','40');
  }else if(type==='trip'){
    fields=field('route_id','Yo‘nalish','select',routeOptions())+field('vehicle_id','Transport','select',vehicleOptions(state.routes[0]?.id))+field('service_date','Sana','date','',localDate(new Date()))+field('departure_time','Jo‘nash vaqti','time','','08:00');
  }else{
    fields=field('trip_id','Qatnov','select',state.trips.map(t=>`<option value="${t.id}">${html(t.service_date)} · ${html(t.code)} · ${html(t.departure_time)}</option>`).join(''))+field('stop_id','Bekat','select','')+field('boarded','Chiqqan yo‘lovchilar','number','','0')+field('alighted','Tushgan yo‘lovchilar','number','','0');
  }
  $('#formFields').innerHTML=fields;
  $('#entryDialog').showModal();
  if(type==='trip')$('#f_route_id').addEventListener('change',e=>$('#f_vehicle_id').innerHTML=vehicleOptions(e.target.value));
  if(type==='count'){
    $('#f_trip_id').addEventListener('change',changeTripStops);
    $('#f_stop_id').addEventListener('change',fillExistingCount);
    changeTripStops();
  }
}
async function submitForm(event){
  event.preventDefault();
  const type=state.formType;
  const values=Object.fromEntries(new FormData($('#entryForm')).entries());
  const path={route:'/api/routes',vehicle:'/api/vehicles',trip:'/api/trips',count:'/api/counts'}[type];
  try{
    const result=await request(path,{method:'POST',body:JSON.stringify(values)});
    $('#entryDialog').close();showToast(result.message);
    await loadData();
  }catch(e){showToast(e.message,true);}
}
function initialize(){
  const now=new Date(),start=new Date(now);
  start.setDate(now.getDate()-6);
  $('#dateFrom').value=localDate(start);
  $('#dateTo').value=localDate(now);
  $('#currentDate').textContent=now.toLocaleDateString('uz-UZ',{day:'numeric',month:'long',year:'numeric'});
  $$('.nav-item').forEach(btn=>btn.addEventListener('click',()=>switchPage(btn.dataset.page)));
  $$('[data-goto]').forEach(btn=>btn.addEventListener('click',()=>switchPage(btn.dataset.goto)));
  $('#applyFilter').addEventListener('click',loadData);
  $('#exportCsv').addEventListener('click',()=>window.location.href='/api/export.csv?'+currentQuery());
  $('#newEntry').addEventListener('click',()=>openForm(state.page==='routes'?'route':state.page==='trips'?'trip':'count'));
  $('#addRoute').addEventListener('click',()=>openForm('route'));
  $('#addVehicle').addEventListener('click',()=>openForm('vehicle'));
  $('#addTrip').addEventListener('click',()=>openForm('trip'));
  $('#addCount').addEventListener('click',()=>openForm('count'));
  $('#entryForm').addEventListener('submit',submitForm);
  $('#closeDialog').addEventListener('click',()=>$('#entryDialog').close());
  $('#cancelDialog').addEventListener('click',()=>$('#entryDialog').close());
  loadData();
}
document.addEventListener('DOMContentLoaded',initialize);
