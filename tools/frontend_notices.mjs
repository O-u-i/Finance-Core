import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const packages = { react: '19.3.0', 'react-dom': '19.3.0', scheduler: '0.28.0' };
const sections = Object.entries(packages).map(([name, version]) => {
  const pkg = JSON.parse(readFileSync(`node_modules/${name}/package.json`, 'utf8'));
  if (pkg.version !== version || pkg.license !== 'MIT') throw new Error(`Unreviewed dependency: ${name}`);
  return `${name} ${version}\n${readFileSync(`node_modules/${name}/LICENSE`, 'utf8').trim()}\n`;
});
const sidebar = 'React Bits BranchedMenu · source revision d9085a5d6cb62a1c7512d8fa05a4f966736b575c\n'
  + 'https://github.com/DavidHDev/react-bits/tree/d9085a5d6cb62a1c7512d8fa05a4f966736b575c\n'
  + 'Adapted for controlled FC page/section navigation, keyboard buttons, reduced motion and desktop layout. No Hugeicons dependency.\n'
  + readFileSync('public/REACT-BITS-LICENSE.txt', 'utf8').trim() + '\n';
if (!sidebar.includes('MIT + Commons Clause') || !sidebar.includes('Copyright (c) 2026 David Haz')) throw new Error('Reviewed sidebar license missing.');
const notice = `Finance Core frontend third-party notices\n\n${[...sections, sidebar].join('\n---\n\n')}`;
if (process.argv.includes('--check')) {
  const version = JSON.parse(readFileSync('package.json', 'utf8')).version;
  const root = `dist/v${version}`;
  if (readFileSync(join(root, 'THIRD-PARTY-NOTICES.txt'), 'utf8') !== notice) throw new Error('Distribution notices are missing or stale.');
  const inspect = (dir) => {
    for (const item of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, item.name);
      if (item.isDirectory()) inspect(path);
      else if (/\.(ttf|woff2?|sqlite3?|csv|env)$|AGENTS|\.rules$/.test(item.name)) throw new Error(`Unexpected distribution file: ${item.name}`);
    }
  };
  inspect(root);
  for (const name of readdirSync(join(root, 'assets')).filter(name => name.endsWith('.js'))) {
    const bundle = readFileSync(join(root, 'assets', name), 'utf8');
    if (bundle.includes('/api/v2') || bundle.includes('localStorage') || bundle.includes('sessionStorage')) throw new Error(`Legacy route or browser storage in runtime chunk: ${name}`);
  }
  if (readFileSync(join(root, 'REACT-BITS-LICENSE.txt'), 'utf8') !== readFileSync('public/REACT-BITS-LICENSE.txt', 'utf8')) throw new Error('Sidebar distribution license missing.');
  console.log('Frontend distribution: pinned React MIT and approved React Bits MIT + Commons Clause notices present; no legacy routes, browser storage or font/data/rule assets.');
} else {
  writeFileSync('public/THIRD-PARTY-NOTICES.txt', notice, 'utf8');
  console.log('Pinned frontend dependency notices generated.');
}
