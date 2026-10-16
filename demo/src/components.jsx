import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { selectedMonth } from './navigation.js';
import { orderedRecords, recordValue } from './records.js';
export const options = values => values.map(value => ({ value, label: value }));

export function Logo({ small = false, markOnly = false }) {
  return <span className={`brand${markOnly ? ' brand-mark' : ''}`}><img src="/branding/logo.svg" width={small ? 119 : 162} height={small ? 30 : 40} alt="FINCR"/>{!markOnly && <span>Finance Core<small>Local finance, clearly.</small></span>}</span>;
}
export function Button({ children, primary, danger, ...props }) { return <button className={`${primary ? 'primary' : ''} ${danger ? 'danger' : ''}`} {...props}>{children}</button>; }
export function MonthPicker({ fc, label = 'As-of month (balances are month-end observations)', value = selectedMonth(fc.route) }) {
  return <Field label={label}><input type="month" value={value} disabled={fc.busy} onChange={event => {
    const month = event.target.value;
    if (!month) return;
    const globalView = ['overview', 'master'].includes(fc.route.view);
    fc.navigate(fc.route.view, globalView ? fc.route.tab : month, fc.route.segment, globalView ? month : '');
  }}/></Field>;
}
export function RejectDialog({ reasons, onClose }) {
  const dialog = useRef(null), title = useId(), description = useId();
  useEffect(() => {
    const node = dialog.current;
    node.showModal();
    return () => { if (node.open) node.close(); };
  }, []);
  return <dialog ref={dialog} className="reject-dialog" aria-labelledby={title} aria-describedby={description} onCancel={onClose} onClose={onClose}>
    <h2 id={title}>CSV import rejected</h2><p id={description}>No drafts were imported. Fix the configuration below in Master data, then check this file again. Your input is retained.</p>
    <ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul><Button primary onClick={onClose}>Return to CSV</Button>
  </dialog>;
}
export function Dialog({ title, children, onClose, dismissible = true }) {
  const dialog = useRef(null), heading = useId();
  useEffect(() => {
    const node = dialog.current, trigger = document.activeElement; node.showModal();
    return () => { if (node.open) node.close(); if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, []);
  return <dialog ref={dialog} className="detail-dialog" aria-labelledby={heading} onCancel={event => { event.preventDefault(); if (dismissible) onClose(); }} onClose={onClose}>
    <div className="dialog-heading"><h2 id={heading}>{title}</h2><Button type="button" disabled={!dismissible} onClick={onClose} aria-label={`Close ${title}`}>Close</Button></div>
    {children}
  </dialog>;
}
export function Help({ children, label = 'Help' }) {
  const trigger = useRef(null), bubble = useRef(null), [position, setPosition] = useState(null), tooltip = useId();
  useLayoutEffect(() => {
    if (!position || !bubble.current) return;
    const rect = bubble.current.getBoundingClientRect();
    if (rect.top < 11 || rect.bottom > innerHeight - 11) setPosition({ width: position.width, left: position.left, top: Math.max(12, innerHeight - rect.height - 12) });
  }, [position]);
  const show = event => {
    if (event.pointerType !== 'mouse') return;
    const rect = trigger.current.getBoundingClientRect(), width = Math.min(320, innerWidth - 24);
    setPosition({ width, left: Math.max(12, Math.min(rect.left, innerWidth - width - 12)),
      ...(rect.bottom + 150 > innerHeight ? { bottom: innerHeight - rect.top + 8 } : { top: rect.bottom + 8 }) });
  };
  return <span ref={trigger} className="help-trigger" role="img" aria-label={`${label}: ${children}`} aria-describedby={position ? tooltip : undefined} onPointerEnter={show} onPointerLeave={() => setPosition(null)}>
    <span aria-hidden="true">?</span>{position && createPortal(<span ref={bubble} id={tooltip} className="help-tooltip" role="tooltip" style={position}>{children}</span>, trigger.current?.closest('dialog[open]') || document.body)}
  </span>;
}
export function Status({ children, state = 'neutral' }) {
  return <span className="record-status" data-state={state}>{children}</span>;
}
export function RecordRow({ title, meta, amount, currency, status, actions, className = '' }) {
  return <article className={`workbench-record ${className}`}>
    <div className="record-identity"><h3>{title}</h3><div className="record-meta">{meta}</div></div>
    <div className="record-primary">{amount != null && <div className="record-amount">{amount}<span className="record-currency">{currency}</span></div>}{status}</div>
    <div className="record-actions">{actions}</div>
  </article>;
}
export function Panel({ title, description, notice, action, children, className = '' }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><div className="panel-title"><h2>{title}</h2>{description && <Help label={typeof title === 'string' ? title : 'Help'}>{description}</Help>}</div>{action}</div>{notice && <p className="notice">{notice}</p>}{children}</section>;
}
export function Field({ label, children, ...props }) {
  const id = useId();
  if (children?.type === 'select') {
    const options = React.Children.toArray(children.props.children).flat().filter(React.isValidElement).map((option) => ({ value: String(option.props.value ?? option.props.children), label: option.props.children }));
    return <Select label={label} {...children.props} options={options} onChange={children.props.onChange ? (value) => children.props.onChange({ target: { value } }) : undefined}/>;
  }
  return <div className="field"><label htmlFor={id}>{label}</label>{children ? React.cloneElement(children, { id }) : <input id={id} {...props}/>}</div>;
}
export function Empty({ children = 'No records yet.' }) { return <div className="empty"><span className="empty-mark" aria-hidden="true">—</span><p>{children}</p></div>; }
export function ResourceForm({ fc, fields, initial = {}, immutable = [], submitLabel = 'Save', onSave }) {
  return <form className="resource-form" onChangeCapture={(event) => fc.markDirty(event.currentTarget)} onSubmit={async (event) => {
    event.preventDefault(); const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    if (await onSave(values)) { form.reset(); fc.clean(form); }
  }}><fieldset disabled={fc.busy || fc.readonly}><div className="form-grid">{fields.map(([name, label, type = 'text', options]) => <Field key={name} label={label}>
    {options ? <select name={name} defaultValue={initial[name] ?? options[0]?.value}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : type === 'textarea' ? <textarea name={name} rows={2} defaultValue={initial[name] ?? ''} maxLength={4000} required={name !== 'note'}/> : <input name={name} type={type} defaultValue={initial[name] ?? ''} readOnly={immutable.includes(name)} required={!['note', 'subtype', 'payee', 'reference', 'linkedAccountId', 'startMonth', 'endMonth', 'successorOf', 'legacyLivingId'].includes(name)} inputMode={['amount', 'balance', 'price', 'purchaseCost', 'ownershipShare'].includes(name) ? 'decimal' : undefined}/>}
  </Field>)}</div><Button type="submit" primary>{submitLabel}</Button></fieldset></form>;
}
export function ListControls({ label = 'Records', columns, sort, setSort, descending, setDescending, query, setQuery }) {
  return <div className="list-controls" role="group" aria-label={`${label} filters`}>
    {query !== undefined && <Field label={`Filter ${label}`}><input type="search" value={query} placeholder="Search records" onChange={event => setQuery(event.target.value)}/></Field>}
    <Select label="Sort by" value={sort} onChange={setSort} options={columns.map(([value, label]) => ({ value, label }))}/>
    <Button type="button" className="sort-direction" aria-label={descending ? 'Sort ascending' : 'Sort descending'} title={descending ? 'Switch to ascending order' : 'Switch to descending order'} onClick={() => setDescending(!descending)}><span aria-hidden="true">{descending ? '↓' : '↑'}</span>{descending ? 'Descending' : 'Ascending'}</Button>
  </div>;
}
export function Table({ columns, rows = [], rowKey, caption = 'Records', controls = true }) {
  const records = Array.isArray(rows) ? rows : [];
  const sortable = columns.filter(column => !['actions', 'details', 'record'].includes(column[0]) && records.some(row => {
    const value = recordValue(row, column); return value != null && ['string', 'number', 'boolean'].includes(typeof value);
  }));
  const [chosen, setSort] = useState(''), [descending, setDescending] = useState(false), [query, setQuery] = useState('');
  const sort = sortable.some(column => column[0] === chosen) ? chosen : sortable[0]?.[0] || '';
  const visible = controls ? orderedRecords(records, sortable, sort, descending, query) : records;
  return <div className="record-list">
    {controls && records.length > 0 && sortable.length > 0 && <ListControls label={caption} columns={sortable} sort={sort} setSort={setSort} descending={descending} setDescending={setDescending} query={query} setQuery={setQuery}/>}
    {visible.length ? <div className="table-wrap" tabIndex={0} role="region" aria-label={caption}><table><caption className="sr-only">{caption}</caption><thead><tr>{columns.map(([key, label]) => <th key={key} scope="col" aria-sort={controls && sort === key ? descending ? 'descending' : 'ascending' : undefined}>{label}</th>)}</tr></thead><tbody>{visible.map((row, index) => <tr key={rowKey ? row[rowKey] : row.id || index}>{columns.map(([key, , render]) => <td key={key}>{render ? render(row) : String(row[key] ?? '—')}</td>)}</tr>)}</tbody></table></div> : <Empty>{records.length ? 'No records match these filters.' : 'No records yet.'}</Empty>}
  </div>;
}
export function Tabs({ items, value, onChange }) {
  return <nav className="subnav" aria-label="Page sections">{items.map(([key, label]) => <button key={key} aria-current={value === key ? 'page' : undefined} className={value === key ? 'selected' : ''} onClick={() => onChange(key)}>{label}</button>)}</nav>;
}
export function Steps({ labels, current }) {
  return <ol className="stepper" aria-label="Progress">{labels.map((label, index) => <li key={label} className={`${index <= current ? 'reached' : ''} ${index === current ? 'current' : ''}`} aria-current={index === current ? 'step' : undefined}><span className="step-number">{index < current ? '✓' : index + 1}</span><span className="step-label">{label}</span>{index < labels.length - 1 && <span className="step-connector" aria-hidden="true"><i/></span>}</li>)}</ol>;
}

export function StepContent({ step, children, className = '' }) {
  const outer = useRef(null), inner = useRef(null), previous = useRef(step);
  useLayoutEffect(() => {
    const node = inner.current;
    const measure = () => { if (outer.current && node) outer.current.style.height = `${node.getBoundingClientRect().height}px`; };
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    let animation;
    if (previous.current !== step) {
      node.focus({ preventScroll: true }); previous.current = step;
      if (!matchMedia('(prefers-reduced-motion: reduce)').matches) animation = node.animate([{ opacity: .85, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 220, easing: 'cubic-bezier(.22,1,.36,1)' });
    }
    return () => { observer.disconnect(); animation?.cancel(); };
  }, [step]);
  return <div className={`step-content ${className}`} ref={outer}><div className="step-page" ref={inner} key={step} tabIndex={-1}>{children}</div></div>;
}

export function Select({ label, value, defaultValue, onChange, options = [], disabled = false, name, required, showTags = true }) {
  const id = useId(), root = useRef(null), list = useRef(null), trigger = useRef(null), native = useRef(null);
  const [localValue, setLocalValue] = useState(defaultValue ?? options[0]?.value ?? '');
  const actual = value ?? localValue;
  const [open, setOpen] = useState(false), [index, setIndex] = useState(0), [position, setPosition] = useState(null), [highlight, setHighlight] = useState(null);
  const selected = options.findIndex((option) => option.value === actual);
  useEffect(() => {
    const form = native.current?.form;
    const reset = () => setLocalValue(defaultValue ?? options[0]?.value ?? '');
    form?.addEventListener('reset', reset);
    return () => form?.removeEventListener('reset', reset);
  }, [defaultValue, options]);
  useLayoutEffect(() => {
    if (!open) return;
    const measure = () => {
      if (innerWidth <= 600) { setOpen(false); native.current?.focus({ preventScroll: true }); return; }
      const rect = trigger.current.getBoundingClientRect(), width = Math.min(Math.max(rect.width, 220), innerWidth - 24);
      const below = innerHeight - rect.bottom - 16, above = rect.top - 16;
      const up = below < Math.min(270, options.length * 44 + 12) && above > below;
      setPosition({ left: Math.max(12, Math.min(rect.left, innerWidth - width - 12)), width, maxHeight: Math.max(88, Math.min(270, up ? above : below)), ...(up ? { bottom: innerHeight - rect.top + 7 } : { top: rect.bottom + 7 }), transformOrigin: up ? 'bottom left' : 'top left' });
    };
    measure(); window.addEventListener('resize', measure); window.addEventListener('scroll', measure, true);
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true); };
  }, [open, options.length]);
  useLayoutEffect(() => {
    if (!open || !position) return;
    const option = list.current?.querySelector(`[data-index="${index}"]`);
    if (option) { setHighlight({ transform: `translateY(${option.offsetTop}px)`, height: option.offsetHeight }); option.scrollIntoView({ block: 'nearest' }); }
  }, [open, index, position, options.length]);
  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const close = (event) => { if (!root.current?.contains(event.target) && !list.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close);
  }, [open, !!position]);
  useEffect(() => {
    const fieldset = root.current?.closest('fieldset');
    const check = () => { if (disabled || fieldset?.disabled) setOpen(false); };
    check(); const observer = new MutationObserver(check); if (fieldset) observer.observe(fieldset, { attributes: true, attributeFilter: ['disabled'] });
    return () => observer.disconnect();
  }, [disabled]);
  const choose = (i) => {
    if (!options[i] || trigger.current?.matches(':disabled')) return;
    const next = options[i].value; setLocalValue(next);
    // Preserve native form submission and delegated dirty tracking for uncontrolled forms.
    if (native.current) { native.current.value = next; native.current.dispatchEvent(new Event('change', { bubbles: true })); }
    setOpen(false); trigger.current?.focus();
  };
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
    <select ref={native} className="select-native" id={`${id}-native`} name={name} required={required} value={actual} disabled={disabled} onChange={(e) => { setLocalValue(e.target.value); onChange?.(e.target.value, options.find((option) => option.value === e.target.value)); }}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
    <div className="select-custom"><button type="button" ref={trigger} aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? `${id}-list` : undefined} disabled={disabled || !options.length} onClick={() => { setIndex(Math.max(0, selected)); setOpen(!open); }} onKeyDown={(event) => { if (['ArrowDown', 'ArrowUp'].includes(event.key)) { event.preventDefault(); setIndex(Math.max(0, selected)); setOpen(true); } }}><span id={`${id}-value`}>{options[selected]?.label || 'Select an option'}</span><svg className={open ? 'select-chevron open' : 'select-chevron'} viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6"/></svg></button>
    {open && position && createPortal(<ul ref={list} id={`${id}-list`} style={position} className="select-menu glide-menu" role="listbox" tabIndex={0} aria-labelledby={`${id}-label`} aria-activedescendant={`${id}-${index}`} onKeyDown={keyDown} onBlur={(event) => { if (!root.current?.contains(event.relatedTarget) && !list.current?.contains(event.relatedTarget)) setOpen(false); }}><li className="select-highlight" aria-hidden="true" role="presentation" style={highlight || { opacity: 0 }}/>{options.map((option, i) => <li data-index={i} id={`${id}-${i}`} key={option.value} role="option" aria-selected={actual === option.value} onPointerMove={() => setIndex(i)} onClick={() => choose(i)}><span>{option.label}</span><span className="option-meta">{showTags && option.tag && <small>{option.tag}</small>}{actual === option.value && <span aria-hidden="true">✓</span>}</span></li>)}</ul>, root.current?.closest('dialog[open]') || document.body)}
    </div>
  </div>;
}
