import {analyzeCommits as conventional} from '@semantic-release/commit-analyzer';

export async function analyzeCommits(config, context) {
  if (!context.commits.length) return null;
  return await conventional({preset: 'conventionalcommits'}, context) || 'patch';
}
