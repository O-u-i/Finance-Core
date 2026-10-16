// Adapted from the user-supplied React Bits LineSidebar (David Haz, 2026).
// Source: DavidHDev/react-bits@1eeb6f105c68b964289d85dabbe84a1d551f3797.
// MIT + Commons Clause; see public/REACT-BITS-LICENSE.txt.
import React, { useCallback, useEffect, useRef } from 'react';

export default function LineSidebar({ items, activeKey, disabled, onNavigate }) {
  const list = useRef(null), nodes = useRef([]), targets = useRef([]), current = useRef([]);
  const frame = useRef(null), last = useRef(0), active = useRef(activeKey), reduced = useRef(false);
  active.current = activeKey;
  const runFrame = useCallback(now => {
    const dt = Math.min((now - last.current) / 1000, .05);
    last.current = now;
    const k = reduced.current ? 1 : 1 - Math.exp(-dt / .1);
    let moving = false;
    nodes.current.forEach((node, index) => {
      if (!node) return;
      const target = Math.max(targets.current[index] || 0, node.dataset.key === active.current ? 1 : 0);
      const value = (current.current[index] || 0) + (target - (current.current[index] || 0)) * k;
      const settled = Math.abs(target - value) < .0015;
      current.current[index] = settled ? target : value;
      node.style.setProperty('--effect', current.current[index].toFixed(4));
      if (!settled) moving = true;
    });
    frame.current = moving ? requestAnimationFrame(runFrame) : null;
  }, []);
  const start = useCallback(() => {
    if (frame.current != null) cancelAnimationFrame(frame.current);
    last.current = performance.now(); frame.current = requestAnimationFrame(runFrame);
  }, [runFrame]);
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => { reduced.current = media.matches; start(); };
    update(); media.addEventListener('change', update);
    return () => { media.removeEventListener('change', update); if (frame.current != null) cancelAnimationFrame(frame.current); frame.current = null; };
  }, [start]);
  useEffect(() => { targets.current = []; start(); }, [activeKey, items.length, start]);
  return <nav className="line-sidebar" aria-label="Segment pages"><ul ref={list} className="line-sidebar__list" onPointerMove={event => {
    if (disabled || reduced.current || event.pointerType !== 'mouse') return;
    const pointer = event.clientY - list.current.getBoundingClientRect().top;
    nodes.current.forEach((node, index) => {
      if (!node) return;
      const p = Math.max(0, 1 - Math.abs(pointer - node.offsetTop - node.offsetHeight / 2) / 80);
      targets.current[index] = p * p * (3 - 2 * p);
    }); start();
  }} onPointerLeave={() => { targets.current = []; start(); }}>
    {items.map((item, index) => <li key={item.key} data-key={item.key} ref={node => { nodes.current[index] = node; }} className="line-sidebar__item" style={{ '--effect': item.key === activeKey ? 1 : 0 }}>
      <button type="button" disabled={disabled} aria-current={activeKey === item.key ? 'page' : undefined} onClick={() => onNavigate(item.key)}>
        <span className="line-sidebar__marker" aria-hidden="true"/><span className="line-sidebar__label">{item.label}</span>
      </button>
    </li>)}
  </ul></nav>;
}
