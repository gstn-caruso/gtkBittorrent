import {generateNotes as conventional} from '@semantic-release/release-notes-generator';
import {releaseContext} from './release-history.mjs';

export async function generateNotes(config, context) {
  context = releaseContext(config, context);
  const types = ['feat', 'fix', 'perf', 'revert', 'docs', 'style', 'refactor', 'test', 'build', 'ci', 'chore'];
  const notes = await conventional({
    preset: 'conventionalcommits',
    presetConfig: {types: types.map(type => ({type, section: type, hidden: false}))},
  }, context);
  const others = context.commits.filter(commit => !types.some(type => commit.message.startsWith(`${type}:`) || commit.message.startsWith(`${type}(`) || commit.message.startsWith(`${type}!:`)));
  return notes + (others.length ? '\n### Otros cambios\n\n' + others.map(commit => `* ${commit.message.split('\n')[0]} (${commit.hash.slice(0, 7)})`).join('\n') + '\n' : '');
}
