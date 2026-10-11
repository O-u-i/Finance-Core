import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const packages = { react: '19.3.0', 'react-dom': '19.3.0', scheduler: '0.28.0' };
const sections = Object.entries(packages).map(([name, version]) => {
  const pkg = JSON.parse(readFileSync(`node_modules/${name}/package.json`, 'utf8'));
  if (pkg.version !== version || pkg.license !== 'MIT') throw new Error(`Unreviewed dependency: ${name}`);
  return `${name} ${version}\n${readFileSync(`node_modules/${name}/LICENSE`, 'utf8').trim()}\n`;
});
const notice = `Finance Core frontend third-party notices\n\n${sections.join('\n---\n\n')}`;
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
  const bundle = readFileSync(join(root, 'assets/app.js'), 'utf8');
  if (bundle.includes('/api/v2') || bundle.includes('localStorage') || bundle.includes('sessionStorage')) throw new Error('Legacy route or browser storage in runtime.');
  console.log('Frontend distribution: pinned MIT notices present; no legacy routes, browser storage or font/data/rule assets.');
} else {
  writeFileSync('public/THIRD-PARTY-NOTICES.txt', notice, 'utf8');
  console.log('Pinned frontend dependency notices generated.');
}
