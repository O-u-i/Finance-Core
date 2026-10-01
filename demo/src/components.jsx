import React, { useEffect, useId, useRef, useState } from 'react';

export function Logo({ small = false }) {
  return <span className="brand"><svg viewBox="0 0 48 48" width={small ? 32 : 44} height={small ? 32 : 44} role="img" aria-label="Finance Core"><path d="M8 8h18v6H14v9h10v6H14v11H8z" fill="currentColor"/><path d="M39 10a16 16 0 1 0 0 28v-7a10 10 0 1 1 0-14z" fill="var(--accent)"/></svg><span>Finance Core<small>Local finance, clearly.</small></span></span>;
}
export function Button({ children, primary, danger, ...props }) { return <button className={`${primary ? 'primary' : ''} ${danger ? 'danger' : ''}`} {...props}>{children}</button>; }
export function Panel({ title, description, action, children, className = '' }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>{children}</section>;
}
export function Field({ label, children, ...props }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label>{children ? React.cloneElement(children, { id }) : <input id={id} {...props}/>}</div>;
}
export function Empty({ children = 'No records yet.' }) { return <div className="empty"><span className="empty-mark" aria-hidden="true">—</span><p>{children}</p></div>; }
export function ResourceForm({ fc, fields, initial = {}, immutable = [], submitLabel = 'Save', onSave }) {
  return <form className="resource-form" onChangeCapture={(event) => fc.markDirty(event.currentTarget)} onSubmit={async (event) => {
    event.preventDefault(); const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    if (await onSave(values)) { form.reset(); fc.clean(form); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">{fields.map(([name, label, type = 'text', options]) => <Field key={name} label={label}>
    {options ? <select name={name} defaultValue={initial[name] ?? options[0]?.value}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : <input name={name} type={type} defaultValue={initial[name] ?? ''} readOnly={immutable.includes(name)} required={!['note', 'subtype', 'payee', 'reference'].includes(name)} inputMode={['amount', 'balance', 'price'].includes(name) ? 'decimal' : undefined}/>}
  </Field>)}</div><Button type="submit" primary>{submitLabel}</Button></fieldset></form>;
}
export function Table({ columns, rows = [], rowKey, caption }) {
  return rows.length ? <div className="table-wrap" tabIndex={0} role="region" aria-label={caption || 'Records'}><table><caption className="sr-only">{caption || 'Records'}</caption><thead><tr>{columns.map(([key, label]) => <th key={key} scope="col">{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={rowKey ? row[rowKey] : index}>{columns.map(([key, , render]) => <td key={key}>{render ? render(row) : String(row[key] ?? '—')}</td>)}</tr>)}</tbody></table></div> : <Empty/>;
}
export function Tabs({ items, value, onChange }) {
  return <nav className="subnav" aria-label="Page sections">{items.map(([key, label]) => <button key={key} aria-current={value === key ? 'page' : undefined} className={value === key ? 'selected' : ''} onClick={() => onChange(key)}>{label}</button>)}</nav>;
}
export function Steps({ labels, current }) {
  return <ol className="stepper" aria-label="Progress">{labels.map((label, index) => <li key={label} className={index <= current ? 'reached' : ''} aria-current={index === current ? 'step' : undefined}><span>{index < current ? '✓' : index + 1}</span>{label}</li>)}</ol>;
}

export function Select({ label, value, onChange, options, disabled = false }) {
  const id = useId(), root = useRef(null), list = useRef(null), trigger = useRef(null);
  const [open, setOpen] = useState(false), [index, setIndex] = useState(0);
  const selected = Math.max(0, options.findIndex((option) => option.value === value));
  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close);
  }, [open]);
  const choose = (i) => { onChange(options[i].value); setOpen(false); trigger.current?.focus(); };
  const keyDown = (event) => {
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' ', 'Escape'].includes(event.key)) event.preventDefault();
    if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); }
    else if (event.key === 'Tab') setOpen(false);
    else if (event.key === 'ArrowDown') setIndex((i) => Math.min(options.length - 1, i + 1));
    else if (event.key === 'ArrowUp') setIndex((i) => Math.max(0, i - 1));
    else if (event.key === 'Home') setIndex(0);
    else if (event.key === 'End') setIndex(options.length - 1);
    else if (event.key === 'Enter' || event.key === ' ') choose(index);
  };
  return <div className="field select-field" ref={root}>
    <label id={`${id}-label`} htmlFor={`${id}-native`}>{label}</label>
    <select className="select-native" id={`${id}-native`} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
    <div className="select-custom"><button type="button" ref={trigger} aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`} disabled={disabled || !options.length} onClick={() => { setIndex(selected); setOpen(!open); }} onKeyDown={(event) => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); setIndex(selected); setOpen(true); } }}><span id={`${id}-value`}>{options[selected]?.label || 'No options'}</span><span aria-hidden="true">⌄</span></button>
    {open && <ul ref={list} id={`${id}-list`} className="select-menu" role="listbox" tabIndex={0} aria-labelledby={`${id}-label`} aria-activedescendant={`${id}-${index}`} onKeyDown={keyDown} onBlur={(event) => { if (!root.current?.contains(event.relatedTarget)) setOpen(false); }}>{options.map((option, i) => <li id={`${id}-${i}`} key={option.value} role="option" aria-selected={value === option.value} className={index === i ? 'highlight' : ''} onPointerMove={() => setIndex(i)} onClick={() => choose(i)}>{option.label}{value === option.value && <span aria-hidden="true">✓</span>}</li>)}</ul>}
    </div>
  </div>;
}
