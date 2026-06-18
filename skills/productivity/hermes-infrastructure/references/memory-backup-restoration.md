# Restoring Hermes Memory from Backup

Restoration is intentionally a one-line copy. The complication is "which files go where" and "what if the machine is a fresh install".

## Standard restore (same machine, broken state)

```bash
# 1. Pull latest from remote
cd ~/hermes-memory-backup
git pull origin main

# 2. Copy files into place
cp MEMORY.md ~/.hermes/memories/MEMORY.md
cp USER.md   ~/.hermes/memories/USER.md
cp SOUL.md   ~/.hermes/SOUL.md

# 3. Restart Hermes so it re-reads SOUL.md
# (Hermes loads SOUL.md fresh each message, so restart is only needed for
# the agent to "forget" any prior bad state)
```

## Cold restore (new machine, fresh Hermes install)

Same as above, but you also need:

```bash
# Install Hermes (per the official guide)
# Then create the memories directory
mkdir -p ~/.hermes/memories

# Then the standard restore steps above
```

**Order matters:** install Hermes → create `~/.hermes/memories/` → copy files in → **start the agent for the first time so it sees the files** → verify by asking it "what do you remember about me?".

## Partial restore (rollback one field)

The backup script never splits files — every commit is a snapshot of all three. If you want to roll back, say, MEMORY.md to a specific point:

```bash
cd ~/hermes-memory-backup
git log --oneline -- MEMORY.md
# Pick the commit you want, e.g. abc123
git show abc123:MEMORY.md > ~/.hermes/memories/MEMORY.md
```

The other files (USER.md, SOUL.md) keep their current state. This is the right granularity — don't try to surgically edit a file based on a diff; full-file replacement is more reliable.

## When the backup repo itself is gone

If both the local repo and the remote are gone (disk died, GitHub repo deleted, etc.):

1. **Check ~/.hermes/memories/ on the original machine** — the .lock files don't have content, but the .md files might still be intact even if the repo is dead. Don't `rm -rf` the memories dir even when giving up on the repo.
2. **Check `~/.hermes/logs/hermes-memory-backup/backup.log`** — the log doesn't contain the memory content (good), but it tells you the last successful push, so you know the cutoff of what was lost.
3. **The agent has its own session DB at `~/.hermes/sessions/state.db`** — this is NOT backed up, but a `sessions_search` against the DB can still recover facts from old conversations if the DB is intact. Run `sessions_search(query="<known fact>")` and see if it surfaces.

## Edge case: USER.md or MEMORY.md is empty after restore

This happens when the .md file was empty at backup time (e.g. SOUL.md is empty by default — the system prompt comment says "delete the contents to use the default personality"). An empty file is a valid backup state; restoring an empty file is correct. Don't panic and write a "starter" content into it — that would be a *change* relative to the backup.

## Edge case: backup repo has commits from another machine

The script does `fetch + ff-only merge` so this just works. If the histories have *diverged* (e.g. both machines made commits), the local `git merge --ff-only` will fail and the script logs a warning. Resolve manually:

```bash
cd ~/hermes-memory-backup
git fetch origin
# Pick: keep local, take remote, or merge
git reset --hard origin/main   # nuke local, take remote
# OR
git rebase origin/main         # replay local on top of remote
```
