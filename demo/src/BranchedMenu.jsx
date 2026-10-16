// Adapted from React Bits BranchedMenu (David Haz, 2026), approved 2026-10-16.
// Source: DavidHDev/react-bits@d9085a5d6cb62a1c7512d8fa05a4f966736b575c.
// MIT + Commons Clause; see public/REACT-BITS-LICENSE.txt. No icon dependency.
import React, { useEffect, useId, useState } from 'react';

export default function BranchedMenu({ items, activeKey, activeSection, defaultOpen, disabled, onNavigate, onSection, label = 'Segment pages' }) {
  const [expanded, setExpanded] = useState(() => new Set(defaultOpen ?? [activeKey])), id = useId();
  const activeHasChildren = !!items.find(item => item.key === activeKey)?.children?.length;
  useEffect(() => {
    if (activeHasChildren) setExpanded(current => current.has(activeKey) ? current : new Set([...current, activeKey]));
  }, [activeKey, activeHasChildren]);
  const pad = 6, row = 52, trunk = 14, radius = 9, end = 32;
  const rowY = index => pad + index * row + row / 2;
  const branch = index => `M ${trunk} ${rowY(index) - radius} A ${radius} ${radius} 0 0 0 ${trunk + radius} ${rowY(index)} H ${end}`;
  const reach = index => `M ${trunk} 0 V ${rowY(index) - radius} A ${radius} ${radius} 0 0 0 ${trunk + radius} ${rowY(index)} H ${end}`;
  return <nav className="branched-menu" aria-label={label}>{items.map((item, index) => {
    const kids = item.children || [], selected = item.key === activeKey;
    const open = kids.length > 0 && expanded.has(item.key);
    const bodyId = `${id}-${index}`, height = pad * 2 + kids.length * row;
    return <div className="branched-menu__section" data-open={open ? '' : undefined} key={item.key}>
      <button type="button" className="branched-menu__head" disabled={disabled}
        aria-current={selected ? 'page' : undefined} aria-expanded={kids.length ? open : undefined} aria-controls={kids.length ? bodyId : undefined}
        onClick={() => {
          if (kids.length) setExpanded(current => { const next = new Set(current); if (open) next.delete(item.key); else next.add(item.key); return next; });
          if (!kids.length || (!selected && !open)) onNavigate(item.key);
        }}>
        <span className="branched-menu__marker" aria-hidden="true"/><span>{item.label}</span>
      </button>
      {kids.length > 0 && <div id={bodyId} className="branched-menu__body" hidden={!open}>
        <div className="branched-menu__tree" style={{ height }}>
          <svg className="branched-menu__lines" width="40" height={height} aria-hidden="true">
            <path d={`M ${trunk} 0 V ${rowY(kids.length - 1) - radius}`}/>
            {kids.map((kid, k) => <path key={kid.key} d={branch(k)}/>)}
            {kids.map((kid, k) => <path key={'active-' + kid.key} className="branched-menu__reach" d={reach(k)} pathLength="1" style={{ strokeDasharray:1, strokeDashoffset:kid.key === activeSection ? 0 : 1 }}/>) }
          </svg>
          {kids.map(kid => <button key={kid.key} type="button" className="branched-menu__item" disabled={disabled} aria-current={kid.key === activeSection ? 'location' : undefined} tabIndex={open ? 0 : -1} onClick={() => onSection(kid.key,kid,item.key)}>{kid.label}</button>)}
        </div>
      </div>}
    </div>;
  })}</nav>;
}
