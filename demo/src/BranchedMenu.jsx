// Adapted from React Bits BranchedMenu (David Haz, 2026), approved 2026-10-16.
// Source: DavidHDev/react-bits@d9085a5d6cb62a1c7512d8fa05a4f966736b575c.
// MIT + Commons Clause; see public/REACT-BITS-LICENSE.txt. No icon dependency.
import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';

export default function BranchedMenu({ items, activeKey, activeSection, defaultOpen, disabled, onNavigate, onSection, label = 'Segment pages' }) {
  const [expanded, setExpanded] = useState(() => new Set(defaultOpen ?? [activeKey])), id = useId();
  const nav = useRef(null), heads = useRef(new Map()), marker = useRef(null);
  const activeHasChildren = (items.find(item => item.key === activeKey)?.children?.length || 0) > 1;
  useEffect(() => {
    if (activeHasChildren) setExpanded(current => current.has(activeKey) ? current : new Set([...current, activeKey]));
  }, [activeKey, activeHasChildren]);
  useLayoutEffect(() => {
    const place = () => {
      const head = heads.current.get(activeKey), line = marker.current;
      if (!line) return;
      if (head) line.style.top = `${head.offsetTop + (head.offsetHeight - 16) / 2}px`;
      line.toggleAttribute('data-on',!!head);
    };
    place();
    const observer = new ResizeObserver(place);
    if (nav.current) observer.observe(nav.current);
    return () => observer.disconnect();
  }, [activeKey,items]);
  const pad = 6, row = 52, trunk = 14, radius = 9, end = 32;
  const rowY = index => pad + index * row + row / 2;
  const branch = index => `M ${trunk} ${rowY(index) - radius} A ${radius} ${radius} 0 0 0 ${trunk + radius} ${rowY(index)} H ${end}`;
  const reach = index => `M ${trunk} 0 V ${rowY(index) - radius} A ${radius} ${radius} 0 0 0 ${trunk + radius} ${rowY(index)} H ${end}`;
  return <nav ref={nav} className="branched-menu" aria-label={label}><span ref={marker} className="branched-menu__marker" aria-hidden="true"/>{items.map((item, index) => {
    const kids = item.children?.length > 1 ? item.children : [], selected = item.key === activeKey;
    const open = kids.length > 0 && expanded.has(item.key);
    const bodyId = `${id}-${index}`, height = pad * 2 + kids.length * row;
    return <div className="branched-menu__section" data-open={open ? '' : undefined} key={item.key}>
      <button ref={node => { if (node) heads.current.set(item.key,node); else heads.current.delete(item.key); }} type="button" className="branched-menu__head" disabled={disabled}
        aria-current={selected ? 'page' : undefined} aria-expanded={kids.length ? open : undefined} aria-controls={kids.length ? bodyId : undefined}
        onClick={() => {
          if (kids.length) setExpanded(current => { const next = new Set(current); if (selected && open) next.delete(item.key); else next.add(item.key); return next; });
          if (!selected || !kids.length) onNavigate(item.key);
        }}>
        <span>{item.label}</span>
      </button>
      {kids.length > 0 && <div id={bodyId} className="branched-menu__body" inert={!open || undefined} aria-hidden={!open}>
        <div className="branched-menu__fold"><div className="branched-menu__tree" style={{ height }}>
          <svg className="branched-menu__lines" width="40" height={height} aria-hidden="true">
            <path d={`M ${trunk} 0 V ${rowY(kids.length - 1) - radius}`}/>
            {kids.map((kid, k) => <path key={kid.key} d={branch(k)}/>)}
            {kids.map((kid, k) => <path key={'active-' + kid.key} className="branched-menu__reach" d={reach(k)} pathLength="1" style={{ strokeDasharray:1, strokeDashoffset:kid.key === activeSection ? 0 : 1 }}/>) }
          </svg>
          {kids.map(kid => <button key={kid.key} type="button" className="branched-menu__item" disabled={disabled} aria-current={kid.key === activeSection ? 'location' : undefined} tabIndex={open ? 0 : -1} onClick={() => onSection(kid.key,kid,item.key)}>{kid.label}</button>)}
        </div></div>
      </div>}
    </div>;
  })}</nav>;
}
