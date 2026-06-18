# GitHub Token Hygiene Reference

When the user pastes a GitHub PAT (or you install one), the token becomes a long-lived credential. The leak vector is **not** the local filesystem (chmod 600 is enough) — it's the **chat transcript** in the platform they pasted it from. Once a token is in chat, the only mitigation is revocation at the source.

## What this file is

A condensed checklist for the agent to run **immediately after any GitHub auth succeeds**, and a one-page walkthrough to send the user when they need to create a new token.

## Post-auth checklist (run these and include in the report)

```bash
# 1. Confirm login
gh auth status

# 2. List scopes — fine-grained shows nothing, classic shows the legacy list
gh auth status 2>&1 | grep -i scope

# 3. List all repos the token can see (public + private)
gh repo list <user> --json name,isPrivate,description --limit 50

# 4. List the user's SSH keys (classic `admin:public_key` scope can read these)
gh api /user/keys --jq '.[].title'

# 5. Confirm the token is revocable at https://github.com/settings/tokens
echo "User should visit https://github.com/settings/tokens and verify the token's scopes and expiration match what they intended."
```

The first two lines are mandatory. The rest is the visibility report that goes into the completion message so the user can spot "wait, it can see my private notes??" before something bad happens.

## Fine-grained token creation walkthrough (give the user this verbatim)

Browser → **https://github.com/settings/personal-access-tokens/new**

1. Click **"Fine-grained token"** → **"Generate new token"**
2. **Token name**: anything memorable, e.g. `hermes-xiaohe24-backup`
3. **Expiration**: 7 days (shortest in the dropdown; you can re-issue)
4. **Resource owner**: pick the user/org that owns the repos
5. **Repository access**:
   - **Only select repositories** → pick the one(s) you actually need
   - **DO NOT** choose "All repositories" — this widens the blast radius to every repo you can see
6. **Permissions → Repository permissions**:
   - **Contents**: Read and write (for `git push` and `gh release create`)
   - **Issues**: Read and write (only if you need `gh issue`)
   - **Pull requests**: Read and write (only if you need `gh pr`)
   - **Metadata**: Read-only (auto-selected, keep it)
   - **Everything else**: leave at "No access"
7. Click **Generate token** → **copy the token immediately** (shown once)

**Do NOT** use a classic token unless the workflow truly needs account-level scopes. Classic defaults include `admin:public_key` and `admin:repo_hook`, which the user almost never needs and which dramatically widen the leak blast radius.

## Why the "fine-grained" recommendation matters

| | Classic | Fine-grained |
|---|---|---|
| Scopes | ~10 broad legacy scopes | ~30 fine-grained permissions |
| `admin:public_key` (edit your SSH keys) | Default ON | **Cannot be granted** (account-level, not per-repo) |
| `admin:repo_hook` (edit your webhooks) | Default ON | Per-repo, off by default |
| `delete_repo` | Default ON | Per-repo, off by default |
| `repo` (read+write all public+private) | One flag | Per-repo permission |
| Per-repo scoping | No (all repos OR none) | Yes (1..n specific repos) |
| Audit visibility in GH settings | Token name only | Token name + exact repos + exact permissions |
| Expiration options | None / 7 / 30 / 60 / 90 / custom | Same |

The classic-vs-fine-grained gap is **the single most impactful security choice** when creating a GitHub PAT. Recommend fine-grained by default.

## Revocation walkthrough (give the user this when a token is burned)

1. Visit https://github.com/settings/tokens
2. Find the token by its name and the "Last used" timestamp
3. Click **Delete** (red button on the right)
4. Confirm

After deletion, any cron job / backup script / agent using the token will fail with `401 Bad credentials` on the next run. This is the desired behavior — better to break loudly than to keep using a leaked token.

## Auto-revocation cadence

If the user has a long-running cron job (e.g., `xiaohe24-backup` running twice daily), set a calendar reminder to **rotate the token every 60 days** (or shorter, depending on threat model). Fine-grained tokens can be set to expire automatically; classic tokens cannot.

## What to NEVER do

- **Don't store the token in `~/.hermes/memories/MEMORY.md`** (it's a long-lived readable file that gets backed up to the user's `xiaohe24`-style remote repos).
- **Don't paste the token back into chat** to "confirm" it (the chat transcript is the leak).
- **Don't put it in `~/.bashrc`** (leaks to every subprocess the user spawns).
- **Don't commit it to any git repo**, including private ones (git history is forever).
- **Don't share it across multiple machines** unless they share a threat model (one trusted laptop + one untrusted shared server is not "sharing"; it's "exposure").

## When the user says "I already pasted it in chat, what now?"

Honest answer: **the chat transcript is the leak surface**; you cannot scrub it. The only mitigation is:

1. **Revoke the token immediately** at https://github.com/settings/tokens
2. Generate a replacement
3. Send the replacement via a **different channel** than the original (e.g., if they pasted it in Feishu, send the new one in a file attachment or a different platform)
4. If the token was used in any file (`~/.hermes/.env`, cron prompt, etc.), **edit the file to use the new token** AND revoke the old one in the same operation
