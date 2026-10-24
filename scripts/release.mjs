import semanticRelease from 'semantic-release';
import {execFileSync} from 'node:child_process';
import {mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const git = (...args) => execFileSync('git', args, {encoding: 'utf8'}).trim();
export const expectedAssets = version => [`gtkbittorrent-${version}-ubuntu-26.04-x86_64.tar.gz`, `gtkbittorrent-${version}-sources.tar.gz`, 'SHA256SUMS'];
export const missingAssets = (version, assets) => expectedAssets(version).filter(name => !assets.some(asset => asset.name === name && asset.size > 0));
export const isCurrent = (head, remote) => head === remote;

async function main() {
  const token = process.env.GITHUB_TOKEN;
  const repository = process.env.GITHUB_REPOSITORY;
  if (!token || !repository) throw new Error('GITHUB_TOKEN y GITHUB_REPOSITORY son obligatorios');
  const head = git('rev-parse', 'HEAD');
  const remote = git('ls-remote', 'origin', 'refs/heads/main').split(/\s/)[0];
  if (!isCurrent(head, remote)) { console.log('Commit detrás de main; la ejecución vigente publicará los cambios pendientes.'); return; }
  git('fetch', 'origin', '--tags');
  const api = process.env.GITHUB_API_URL || 'https://api.github.com';
  async function request(path, options = {}) {
    const response = await fetch(`${api}/repos/${repository}${path}`, { ...options,
      headers: {Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28', ...options.headers}});
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`GitHub ${response.status}: ${await response.text()}`);
    return response.status === 204 ? true : response.json();
  }
  // Repair tags before analyzing newer commits, including an interrupted earlier head.
  const tags = git('tag', '--merged', 'HEAD', '--list', 'v*', '--sort=version:refname').split('\n').filter(tag => /^v\d+\.\d+\.\d+$/.test(tag));
  for (const tag of tags) {
    const version = tag.slice(1);
    let release = await request(`/releases/tags/${tag}`);
    if (release && !release.draft && missingAssets(version, release.assets).length === 0) continue;
    const work = mkdtempSync(join(tmpdir(), 'gtkb-release-'));
    try {
      const source = join(work, 'source');
      git('worktree', 'add', '--detach', source, tag);
      execFileSync('python3', [join(source, 'scripts/package.py'), version], {cwd: source, stdio: 'inherit',
        env: {...process.env, GTKB_RUNTIME: resolve('.deps/prefix'), GTKB_GEMS: resolve('vendor/bundle/ruby/4.0.0')}});
      if (!release) release = await request('/releases', {method: 'POST', body: JSON.stringify({tag_name: tag, name: tag, draft: true,
        body: `Publicación recuperada para ${tag}.\n\n` + git('log', '--format=* %s (%h)', ...(tags.indexOf(tag) ? [`${tags[tags.indexOf(tag)-1]}..${tag}`] : [tag]))})});
      const uploadBase = release.upload_url.replace(/\{.*$/, '');
      // A partial upload is repaired as one coherent set so SHA256SUMS always matches.
      for (const asset of release.assets) if (expectedAssets(version).includes(asset.name)) await request(`/releases/assets/${asset.id}`, {method: 'DELETE'});
      for (const filename of readdirSync(join(source, 'dist')).filter(name => expectedAssets(version).includes(name))) {
        const response = await fetch(`${uploadBase}?name=${encodeURIComponent(filename)}`, {method: 'POST', headers: {
          Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream'}, body: readFileSync(join(source, 'dist', filename))});
        if (!response.ok) throw new Error(`No se pudo adjuntar ${filename}: ${response.status}`);
      }
      if (release.draft) await request(`/releases/${release.id}`, {method: 'PATCH', body: JSON.stringify({draft: false})});
    } finally {
      try { git('worktree', 'remove', '--force', join(work, 'source')); } finally { rmSync(work, {recursive: true, force: true}); }
    }
  }
  // Recheck after potentially lengthy repair work.
  if (!isCurrent(head, git('ls-remote', 'origin', 'refs/heads/main').split(/\s/)[0])) return;
  await semanticRelease();
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
