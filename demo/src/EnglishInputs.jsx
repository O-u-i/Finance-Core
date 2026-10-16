import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';

const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const pad = value => String(value).padStart(2, '0');
function validDate(value, type) {
  const pattern = type === 'month' ? /^\d{4}-(0[1-9]|1[0-2])$/ : /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
  const date = value.slice(0, 10);
  if (!(type === 'datetime-local' ? /^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(value) : pattern.test(value))) return false;
  const parsed = new Date((type === 'month' ? value + '-01' : date) + 'T00:00:00Z');
  return !Number.isNaN(+parsed) && parsed.toISOString().startsWith(type === 'month' ? value : date) && Number(value.slice(0, 4)) > 0;
}

// App-owned ISO controls avoid browser-locale labels without changing stored date strings.
export function DateInput({ type, value, defaultValue = '', onChange, min, max, label, ...props }) {
  const input = useRef(null), popup = useRef(null), popupId = useId();
  const [local, setLocal] = useState(value ?? defaultValue), [error, setError] = useState(''), [position, setPosition] = useState({});
  const actual = local;
  useEffect(() => { if (value !== undefined) setLocal(value); }, [value]);
  const today = new Date().toLocaleDateString('en-CA', { year:'numeric', month:'2-digit', day:'2-digit' });
  const [page, setPage] = useState((validDate(actual, type) ? actual : today).slice(0, 7));
  const format = type === 'month' ? 'YYYY-MM' : type === 'datetime-local' ? 'YYYY-MM-DDTHH:mm' : 'YYYY-MM-DD';
  const message = actual && (!validDate(actual, type) || (min && actual < min) || (max && actual > max))
    ? `Enter a valid ${type === 'month' ? 'month' : 'date'} as ${format}${min ? ', on or after ' + min : ''}${max ? ', on or before ' + max : ''}.` : '';
  useLayoutEffect(() => { input.current?.setCustomValidity(message); if (!message) setError(''); }, [message]);
  useEffect(() => {
    const form = input.current?.form;
    const reset = () => { setLocal(value ?? defaultValue); setError(''); popup.current?.hidePopover(); };
    form?.addEventListener('reset', reset);
    return () => form?.removeEventListener('reset', reset);
  }, [defaultValue,value]);
  const choose = next => {
    const node = input.current;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(node, next);
    node.dispatchEvent(new Event('input', { bubbles: true }));
    popup.current.hidePopover(); node.focus({ preventScroll:true });
  };
  const [year, month] = page.split('-').map(Number);
  const shift = delta => {
    const next = new Date(`${page}-01T12:00:00Z`); next.setUTCMonth(next.getUTCMonth() + delta);
    if (next.getUTCFullYear() >= 1 && next.getUTCFullYear() <= 9999) setPage(next.toISOString().slice(0, 7));
  };
  const days = new Date(`${page}-01T12:00:00Z`); days.setUTCMonth(days.getUTCMonth() + 1, 0);
  const first = new Date(`${page}-01T12:00:00Z`).getUTCDay();
  return <div className="english-date">
    <div className="date-control"><input {...props} ref={input} type="text" data-date-kind={type} value={actual} placeholder={format} autoComplete="off" spellCheck={false}
      aria-invalid={error ? true : undefined} aria-describedby={error ? `${popupId}-error` : undefined}
      onInvalid={event => { event.preventDefault(); setError(message || `Enter ${label || 'a date'} as ${format}.`); }}
      onChange={event => { setLocal(event.target.value); setError(''); onChange?.(event); }}/>
      {type !== 'datetime-local' && <button type="button" className="date-toggle" disabled={props.disabled || props.readOnly} aria-label={`Choose ${label || type}`} popoverTarget={popupId} onClick={() => {
        const rect = input.current.getBoundingClientRect();
        setPage((validDate(actual, type) ? actual : today).slice(0, 7));
        setPosition({ left:Math.max(12, Math.min(rect.left, innerWidth - 332)), top:Math.max(12, Math.min(rect.bottom + 8, innerHeight - 380)) });
      }}><svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true"><path d="M4 4h12v13H4zM4 8h12M7 2v4m6-4v4" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></button>}
    </div>
    {error && <small className="input-error" id={`${popupId}-error`} role="alert">{error}</small>}
    {type !== 'datetime-local' && <div ref={popup} id={popupId} popover="auto" className="date-popover" role="dialog" aria-label={`Choose ${label || type}`} style={position}>
      <div className="calendar-heading"><button type="button" aria-label={type === 'month' ? 'Previous year' : 'Previous month'} onClick={() => shift(type === 'month' ? -12 : -1)}>‹</button><strong aria-live="polite">{type === 'month' ? year : `${months[month - 1]} ${year}`}</strong><button type="button" aria-label={type === 'month' ? 'Next year' : 'Next month'} onClick={() => shift(type === 'month' ? 12 : 1)}>›</button></div>
      {type === 'month' ? <div className="month-grid">{months.map((name, index) => { const next = `${String(year).padStart(4, '0')}-${pad(index + 1)}`; return <button key={name} type="button" disabled={(min && next < min) || (max && next > max)} aria-pressed={actual === next} onClick={() => choose(next)}>{name.slice(0, 3)}</button>; })}</div>
        : <div className="calendar-grid">{['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(day => <span key={day}>{day}</span>)}{Array.from({ length:first }, (_, i) => <span key={'gap' + i}/>)}{Array.from({ length:days.getUTCDate() }, (_, index) => { const next = `${page}-${pad(index + 1)}`; return <button key={next} type="button" disabled={(min && next < min) || (max && next > max)} aria-label={next} aria-pressed={actual === next} onClick={() => choose(next)}>{index + 1}</button>; })}</div>}
      <p>{format}</p><button type="button" onClick={() => { popup.current.hidePopover(); input.current.focus({ preventScroll:true }); }}>Close calendar</button>
    </div>}
  </div>;
}

export function FileInput({ onChange, ...props }) {
  const input = useRef(null), [names, setNames] = useState('');
  useEffect(() => {
    const form = input.current?.form, reset = () => setNames('');
    form?.addEventListener('reset', reset); return () => form?.removeEventListener('reset', reset);
  }, []);
  return <div className="english-file"><input {...props} type="file" className="sr-only" ref={input} onChange={event => { setNames([...event.target.files].map(file => file.name).join(', ')); onChange?.(event); }}/>
    <button type="button" disabled={props.disabled} onClick={() => input.current.click()}>Choose file</button><span role="status">{names || 'No file selected'}</span>
  </div>;
}
