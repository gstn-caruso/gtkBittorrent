import {analyzeCommits as conventional} from '@semantic-release/commit-analyzer';
import {releaseContext} from './release-history.mjs';

export async function analyzeCommits(config, context) {
  context = releaseContext(config, context);
  if (!context.commits.length) return null;
  return await conventional({preset: 'conventionalcommits'}, context) || 'patch';
}
