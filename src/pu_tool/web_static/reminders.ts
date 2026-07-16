import { Calendar } from 'fullcalendar';
import dayGridPlugin from 'fullcalendar/daygrid';
import listPlugin from 'fullcalendar/list';
import zhCnLocale from 'fullcalendar/locales/zh-cn';
import 'fullcalendar/skeleton.css';

type Reminder = Record<string, unknown>;
const root = document.querySelector<HTMLElement>('#app-root');
let timer: number | undefined;
let calendar: Calendar | null = null;
let loading = false;
let generation = 0;

const make = <K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, attrs: Record<string, string> = {}) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
};
async function requestJSON(url: string): Promise<Reminder[]> {
  const response = await fetch(url);
  if (!response.ok) throw new Error((await response.text()) || response.statusText);
  const data: unknown = await response.json();
  if (!Array.isArray(data)) throw new Error('Invalid reminders response');
  return data.filter((item): item is Reminder => !!item && typeof item === 'object');
}
function parseTime(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const stringValue = String(value);
  const numberValue = typeof value === 'number' || /^[+-]?\d+(?:\.\d+)?$/.test(stringValue) ? Number(value) : Date.parse(stringValue);
  if (!Number.isFinite(numberValue)) return null;
  return numberValue < 1e11 ? numberValue * 1000 : numberValue;
}
function destroyCalendar() { if (calendar) { calendar.destroy(); calendar = null; } }
function render(items: Reminder[]) {
  if (!root) return;
  destroyCalendar();
  const sorted = [...items].sort((a, b) => (parseTime(a.start_time) ?? Infinity) - (parseTime(b.start_time) ?? Infinity));
  root.replaceChildren(make('h1', '提醒'), make('p', '时间按浏览器本地时区显示。'));
  root.append(make('p', sorted.length ? '共 ' + sorted.length + ' 条提醒。' : '暂无提醒。', { 'aria-live': 'polite' }));
  const host = make('div', undefined, { class: 'reminders-calendar', 'aria-label': '提醒日历' });
  root.append(host);
  const cards = make('div', undefined, { class: 'cards' });
  const events: Array<Record<string, unknown>> = [];
  sorted.forEach((item, index) => {
    const start = parseTime(item.start_time); const end = parseTime(item.end_time);
    const card = make('article', undefined, { class: 'card', 'data-reminder-index': String(index), tabindex: '-1' });
    const title = String(item.title || '未命名活动');
    card.append(make('h2', title));
    const status = end !== null && end < Date.now() ? '已结束' : start !== null && start <= Date.now() ? '进行中' : '即将开始';
    const when = start === null ? '时间未知' : new Date(start).toLocaleString() + (end === null ? '' : ' - ' + new Date(end).toLocaleTimeString());
    card.append(make('div', '状态：' + status + '；时间：' + when + '；地点：' + String(item.location || '未提供')));
    if (start !== null) events.push({ id: String(index), title, start: new Date(start), ...(end !== null ? { end: new Date(end) } : {}), extendedProps: { location: item.location, activity_type: item.activity_type } });
    cards.append(card);
  });
  root.append(cards);
  if (events.length) {
    calendar = new Calendar(host, { plugins: [dayGridPlugin, listPlugin], locales: [zhCnLocale], locale: 'zh-cn', initialView: window.innerWidth < 700 ? 'listMonth' : 'dayGridMonth', headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,listMonth' }, events, eventClick: (info) => { const card = root.querySelector<HTMLElement>('[data-reminder-index="' + info.event.id + '"]'); card?.scrollIntoView({ behavior: 'smooth', block: 'center' }); card?.focus(); } });
    calendar.render();
  }
}
async function load() {
  if (!root || loading) return;
  loading = true; const current = ++generation; root.setAttribute('aria-busy', 'true');
  try { const data = await requestJSON('/api/reminders'); if (current === generation) render(data); }
  catch { if (current === generation) { destroyCalendar(); const retry = make('button', '重试'); retry.onclick = load; root.replaceChildren(make('p', '提醒加载失败，请重试。', { role: 'alert' }), retry); } }
  finally { if (current === generation) { loading = false; root.setAttribute('aria-busy', 'false'); } }
}
if (root) { void load(); timer = window.setInterval(() => void load(), 60000); const visibility = () => { if (document.visibilityState === 'visible') void load(); }; document.addEventListener('visibilitychange', visibility); window.addEventListener('beforeunload', () => { if (timer !== undefined) window.clearInterval(timer); destroyCalendar(); document.removeEventListener('visibilitychange', visibility); }); }
