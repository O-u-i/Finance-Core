import React, { useEffect, useRef, useState } from 'react';
import { downloadPrivate } from '../api.js';
import { Button, Field, Panel, Table } from '../components.jsx';

export function SegmentExport({ fc, segment }) {
  if (fc.migrationRequired) return <Panel title="Legacy ledger export" description="Schema 2 retains its existing exports. Unified segment history requires explicit migration; legacy backup remains global in Settings.">
    <Button disabled={fc.busy} onClick={() => downloadPrivate(fc, '/export', 'finance-core-legacy-export.json')}>Export legacy JSON</Button>
    <Button disabled={fc.busy} onClick={() => downloadPrivate(fc, '/export/journal-entries.csv', 'finance-core-legacy-postings.csv', true)}>Export legacy postings CSV</Button>
  </Panel>;
  return <Panel title={`${segment === 'living' ? 'Living' : 'Investment'} export`} description="Segment exports preserve full records and observation correction history. They are not restore-capable Vault backups; the unified backup is in global Settings.">
    <div className="actions">
      <Button disabled={fc.busy} onClick={() => downloadPrivate(fc, `/segments/${segment}/export`, `${segment}-export.json`)}>Export segment JSON</Button>
      <Button disabled={fc.busy} onClick={() => downloadPrivate(fc, `/segments/${segment}/export.csv`, `${segment}-export.csv`, true)}>Export segment CSV</Button>
    </div>
  </Panel>;
}

export function LivingData({ fc }) {
  const [input, setInput] = useState(''), [preview, setPreview] = useState(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  const changed = value => {
    generation.current++; setInput(value); setPreview(null); fc.markDirty('living-csv');
  };
  const readFile = async event => {
    const file = event.target.files[0], ticket = ++generation.current;
    if (!file) return;
    try {
      const value = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      if (ticket === generation.current) changed(value);
    } catch {
      if (ticket === generation.current) fc.setNotice({ error: true, text: 'Choose a UTF-8 CSV file.' });
    }
  };
  const validate = async () => {
    const ticket = generation.current;
    const result = await fc.run((api, wid) => api.ledger(wid, '/import/living-monthly/validate', {
      method: 'POST', body: input, headers: { 'Content-Type': 'text/csv' },
    }), 'CSV preview validated; no data written.', { write: false, reload: false });
    if (result && ticket === generation.current) setPreview(result.data);
  };
  const importPending = async () => {
    if (!confirm('Import these rows as pending monthly observations?')) return;
    const result = await fc.ledger('/import/living-monthly', { method: 'POST', body: preview },
      'Imported pending observations. Confirm each one after review.');
    if (result) { fc.clean('living-csv'); setPreview(null); setInput(''); }
  };
  return <>
    <Panel title="Import monthly observations" description="CSV only creates pending observations. It never creates Journal entries or confirms balances.">
      <p><code>subjectId,month,kind,currency,amount,incoming,outgoing,source</code></p>
      <fieldset disabled={fc.busy || fc.readonly}>
        <Field label="Monthly CSV file"><input type="file" accept=".csv,text/csv" onChange={readFile}/></Field>
        <Field label="CSV input"><textarea rows={8} value={input} onChange={event => changed(event.target.value)}/></Field>
        <Button disabled={!input.trim()} onClick={validate}>Validate preview</Button>
        {preview && <>
          <Table rows={preview} columns={[
            ['subjectId','Subject'], ['month','Month'], ['kind','Kind'], ['amount','Amount'],
            ['incoming','Incoming'], ['outgoing','Outgoing'], ['currency','Currency'], ['confirmed','Confirmed'],
          ]}/>
          <Button primary onClick={importPending}>Import pending rows</Button>
        </>}
      </fieldset>
    </Panel>
    <SegmentExport fc={fc} segment="living"/>
  </>;
}
