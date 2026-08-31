#!/usr/bin/env node
// Merge-queue substitute: merges the wave's PR branches onto origin/main in an
// integration/wave-N branch and pushes it so CI tests the combination.
// Usage: node scripts/integration-check.mjs <wave> <pr-number...>
import { execSync } from 'node:child_process'

const run = (cmd) => execSync(cmd, { stdio: 'pipe', encoding: 'utf-8' }).trim()

const [wave, ...prs] = process.argv.slice(2)
if (!wave || prs.length === 0) {
  console.error('usage: node scripts/integration-check.mjs <wave> <pr-number...>')
  process.exit(1)
}

const branch = `integration/wave-${wave}`
run('git fetch origin main --prune')
run(`git checkout -B ${branch} origin/main`)

for (const pr of prs) {
  const head = run(`gh pr view ${pr} --json headRefName -q .headRefName`)
  console.log(`merging PR #${pr} (${head})`)
  try {
    run(`git fetch origin ${head}`)
    run(`git merge --no-ff --no-edit origin/${head}`)
  } catch (err) {
    console.error(`CONFLICT merging PR #${pr}: ${err.stderr || err.message}`)
    run('git merge --abort')
    process.exit(2)
  }
}

run(`git push -f -u origin ${branch}`)
console.log(`pushed ${branch}; CI runs on push (integration/** trigger).`)
console.log(`watch: gh run watch $(gh run list --branch ${branch} -L 1 --json databaseId -q '.[0].databaseId')`)
