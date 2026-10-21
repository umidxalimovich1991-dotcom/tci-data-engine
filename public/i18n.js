// Interface translations. Market data and issuer names remain unchanged.
const translations = {
 uz: ['Bosh sahifa','Bozor','Portfel','Yangiliklar','Bozordan qidirish...','TCI bozoriga xush kelibsiz','O‘zbekiston fond bozorini kuzating va TCI indeksini tahlil qiling.','Bozor ma’lumotlari','TCI indeksi','Bugungi bozor','Faol aksiyalar','O‘sish reytingi','TCI dinamikasi','Indeks tarixi','Bozor yetakchilari','Eng ko‘p o‘sgan','Eng ko‘p tushgan','Bozor sharhi','TCI savati — O‘zbekiston aksiyalari','Aksiyalarni qidirish...','Kompaniya','Tiker','Narx','O‘zgarish','Hajm','TCI ulushi','O‘sish balli','Kelajak o‘sish tahlili','Ma’lumotlar asosidagi tahliliy ko‘rsatkichlar.'],
 ru: ['Главная','Рынок','Портфель','Новости','Поиск по рынку...','Добро пожаловать в TCI Market','Следите за фондовым рынком Узбекистана и анализируйте индекс TCI.','Рыночные данные','Индекс TCI','Рынок сегодня','Активные акции','Рейтинг роста','Динамика TCI','История индекса','Лидеры рынка','Лидеры роста','Лидеры падения','Обзор рынка','Корзина TCI — акции Узбекистана','Поиск акций...','Компания','Тикер','Цена','Изменение','Объём','Вес в TCI','Оценка роста','Перспективы роста','Аналитические показатели на основе доступных данных.'],
 en: ['Dashboard','Market','Portfolio','News','Search market...','Welcome to TCI Market','Track Uzbekistan’s stock market and analyze the TCI index.','Market data','TCI Index','Today’s Market','Active Stocks','Growth Score','TCI Performance','Index history','Market Movers','Top Gainers','Top Losers','Market Overview','TCI basket — Uzbekistan stocks','Search stocks...','Company','Ticker','Price','Change','Volume','TCI Weight','Growth Score','Future Growth Radar','Analytics based on available market data.']
};
const selectors=['nav a:nth-child(1)','nav a:nth-child(2)','nav a:nth-child(3)','nav a:nth-child(4)','#search','.hero h1','.hero p.muted','.updated','.card.primary span','.card.orange span','.card.purple span','.card.dark span','.chart-panel h2','.chart-panel .muted','.movers-panel h2','.tab[data-tab="gainers"]','.tab[data-tab="losers"]','.table-panel h2','.table-panel .muted','#tableSearch',...Array.from({length:7},(_,i)=>'.table-panel th:nth-child('+(i+1)+')'),'.insight h2','.insight p.muted'];
function setLanguage(lang){
 const dict=translations[lang]||translations.uz;
 selectors.forEach((sel,i)=>{const node=document.querySelector(sel);if(!node)return;if(node.tagName==='INPUT')node.placeholder=dict[i];else if(sel==='.updated'){node.childNodes[0].textContent=dict[i]+'\n        ';}else node.textContent=dict[i];});
 document.documentElement.lang=lang;localStorage.setItem('tci_language',lang);
 document.querySelector('#language').value=lang;
}
document.querySelector('#language').addEventListener('change',e=>setLanguage(e.target.value));
setLanguage(['uz','ru','en'].includes(localStorage.getItem('tci_language'))?localStorage.getItem('tci_language'):'uz');
