const SOURCES = [
  './public/tci_latest.json',
  './tci_latest.json',
  'https://raw.githubusercontent.com/umidxalimovich1991-dotcom/tci-data-engine/main/public/tci_latest.json'
];

const el = id => document.getElementById(id);
const fmt = n => n === null || n === undefined || Number.isNaN(Number(n)) ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 4 });
const pct = n => n === null || n === undefined || Number.isNaN(Number(n)) ? '—' : `${(Number(n) * 100).toFixed(2)}%`;

async function loadData(){
  el('statusText').textContent = 'Ma’lumot yuklanmoqda...';
  let data = null;
  let used = '';
  for(const url of SOURCES){
    try{
      const r = await fetch(`${url}?v=${Date.now()}`, { cache: 'no-store' });
      if(!r.ok) throw new Error(r.statusText);
      data = await r.json();
      used = url;
      break;
    }catch(e){}
  }
  if(!data){
    el('statusText').textContent = 'JSON topilmadi. public/tci_latest.json borligini tekshir.';
    return;
  }
  render(data, used);
}

function render(data, used){
  const rows = Array.isArray(data.constituents) ? data.constituents : [];
  el('tciValue').textContent = fmt(data.tci_value ?? data.base_value);
  el('dailyReturn').textContent = pct(data.daily_return);
  el('countValue').textContent = data.constituents_count ?? rows.length;
  el('activeValue').textContent = rows.filter(r => r.price !== null && r.price !== undefined).length;
  el('dateValue').textContent = data.date || '—';
  el('updatedValue').textContent = data.updated_at ? new Date(data.updated_at).toLocaleString() : '—';
  el('statusText').textContent = `Manba: ${used}`;

  el('tbody').innerHTML = rows.map((r, i) => {
    const d = Number(r.daily_return || 0);
    const cls = d > 0 ? 'pos' : d < 0 ? 'neg' : '';
    return `<tr>
      <td>${i + 1}</td>
      <td class="ticker">${r.ticker || '—'}</td>
      <td class="price">${fmt(r.price)}</td>
      <td class="${cls}">${r.daily_return == null ? '—' : pct(r.daily_return)}</td>
      <td class="source" title="${r.source || ''}">${r.source || '—'}</td>
    </tr>`;
  }).join('');
}

el('reloadBtn').addEventListener('click', loadData);
loadData();
