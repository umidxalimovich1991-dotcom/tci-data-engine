const state={data:null,tab:'gainers'};let chart;
const $=id=>document.getElementById(id);
async function loadData(){
  try{
    const r=await fetch('./tci_latest.json?ts='+Date.now());
    if(!r.ok)throw new Error('HTTP '+r.status);
    state.data=await r.json(); render();
  }catch(e){
    $('marketStatus').textContent='Offline';$('updated').textContent='Data unavailable';
    $('stocks').innerHTML='<tr><td colspan="7">TCI data yuklanmadi. GitHub Actions orqali data yangilanganini tekshiring.</td></tr>';
  }
}
function stocks(){return state.data?.stocks||state.data?.constituents||state.data?.data||[]}
function val(o,...keys){for(const k of keys)if(o&&o[k]!=null)return o[k];return null}
function num(v){const n=Number(v);return Number.isFinite(n)?n:null}
function change(s){return num(val(s,'change_pct','changePercent','change','pct_change'))||0}
function price(s){return num(val(s,'price','last','close','last_price'))}
function ticker(s){return val(s,'ticker','symbol','code','id')||'—'}
function name(s){return val(s,'name','company','company_name')||ticker(s)}
function render(){
 const d=state.data||{}, ss=stocks();
 const idx=val(d,'index_value','tci_value','value','index')||val(d.index,'value');
 const ch=val(d,'index_change_pct','change_pct','changePercent')||val(d.index,'change_pct');
 $('indexValue').textContent=idx!=null?Number(idx).toLocaleString('en-US',{maximumFractionDigits:2}):'—';
 $('indexChange').textContent=ch!=null?`${Number(ch)>=0?'▲':'▼'} ${Number(ch).toFixed(2)}%`:'—';
 $('stockCount').textContent=ss.length||'—'; $('marketStatus').textContent='Online';
 const sorted=[...ss].sort((a,b)=>change(b)-change(a)); const top=sorted[0];
 $('topScore').textContent=top?(val(top,'growth_score','score')??'—'):'—';$('topStock').textContent=top?name(top):'—';
 $('updated').textContent=val(d,'updated_at','last_updated','timestamp')||new Date().toLocaleString();
 renderMovers();renderTable(ss);renderScores(ss);renderChart(d,ss);
}
function renderMovers(){const ss=[...stocks()].sort((a,b)=>change(b)-change(a));const arr=state.tab==='gainers'?ss.slice(0,6):ss.reverse().slice(0,6);$('movers').innerHTML=arr.map(s=>`<div class="mover"><div><div class="ticker">${name(s)}</div><small class="muted">${ticker(s)}</small></div><div><strong>${price(s)!=null?Number(price(s)).toLocaleString(): '—'}</strong><br><span class="${change(s)>=0?'positive':'negative'}">${change(s)>=0?'+':''}${change(s).toFixed(2)}%</span></div></div>`).join('')||'<p class="muted">Data mavjud emas.</p>'}
function renderTable(ss){const q=($('tableSearch').value||'').toLowerCase();const rows=ss.filter(s=>(name(s)+' '+ticker(s)).toLowerCase().includes(q));$('stocks').innerHTML=rows.map(s=>`<tr><td><strong>${name(s)}</strong></td><td>${ticker(s)}</td><td>${price(s)!=null?Number(price(s)).toLocaleString():'—'}</td><td class="${change(s)>=0?'positive':'negative'}">${change(s)>=0?'+':''}${change(s).toFixed(2)}%</td><td>${val(s,'volume','trading_volume')??'—'}</td><td>${val(s,'weight','tci_weight')!=null?Number(val(s,'weight','tci_weight')).toFixed(2)+'%':'—'}</td><td><strong>${val(s,'growth_score','score')??'—'}</strong></td></tr>`).join('')||'<tr><td colspan="7">Aksiya topilmadi.</td></tr>'}
function renderScores(ss){const top=[...ss].sort((a,b)=>(num(val(b,'growth_score','score'))||0)-(num(val(a,'growth_score','score'))||0)).slice(0,6);$('scores').innerHTML=top.map(s=>{const score=num(val(s,'growth_score','score'))||0;return `<div class="score"><strong>${ticker(s)} — ${score}/100</strong><span class="muted">${name(s)}</span><div class="score-bar"><i style="width:${Math.max(0,Math.min(100,score))}%"></i></div></div>`}).join('')||'<p class="muted">Growth Score hali mavjud emas.</p>'}
function renderChart(d,ss){const hist=val(d,'history','historical','index_history')||[];let labels=hist.map(x=>val(x,'date','timestamp','time')), values=hist.map(x=>num(val(x,'value','index_value','close')));if(!values.length){values=ss.map((_,i)=>num(val(d,'index_value','tci_value','value'))||1000);labels=ss.map((_,i)=>String(i+1))}if(chart)chart.destroy();chart=new Chart($('indexChart'),{type:'line',data:{labels,datasets:[{data:values,borderWidth:2,fill:true,tension:.35,pointRadius:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{grid:{color:'#f0f2f5'}}}}})}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.tab=b.dataset.tab;renderMovers()}));
$('refresh').addEventListener('click',loadData);$('tableSearch').addEventListener('input',()=>renderTable(stocks()));$('search').addEventListener('input',e=>{$('tableSearch').value=e.target.value;renderTable(stocks())});loadData();
