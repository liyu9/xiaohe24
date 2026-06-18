# Security Checklist Before Pushing Memory to a Public Repo

The user often wants to back up to a *private* repo and that's fine. But if they ask for a public repo (or you're tempted to "just use the public one for simplicity"), work through this checklist first.

## What lives in the default backup set

| File | Default PII risk |
|---|---|
| `MEMORY.md` | High. Agents commonly write hostnames, IP addresses, internal API keys, environment quirks, and "user X said this" notes. These leak infrastructure details. |
| `USER.md` | Very high. By design contains user preferences, role, location, contact info. |
| `SOUL.md` | Low. Usually persona / tone instructions. |

## Scan for secrets before pushing publicly

```bash
# Crude but effective: grep for things that look like credentials
cd ~/hermes-memory-backup
grep -nE 'sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]+|github_pat_[a-zA-Z0-9]+|AKIA[0-9A-Z]{16}|xox[baprs]-[0-9a-zA-Z-]+|-----BEGIN [A-Z ]+PRIVATE KEY-----' \
  MEMORY.md USER.md SOUL.md
# Empty output = no obvious secrets. Anything that hits = scrub before push.
```

If you find credentials, redact them with `[REDACTED]` in the .md file, commit the redaction *before* pushing, and rotate the actual credential at the provider. Don't try to be clever with encoding — redaction + rotation is the only correct response.

## Scan for PII before pushing publicly

```bash
# Look for things that identify the user or their infrastructure
grep -nE '\b[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b' MEMORY.md USER.md SOUL.md
grep -nE '\b(腾讯云|阿里云|aws|gcp|azure|home network|wifi|password|密码|身份证|手机|email|@\w+\.\w+)\b' MEMORY.md USER.md SOUL.md
# Empty output = safe to push publicly. Anything that hits = decide case-by-case.
```

## What to do if PII is found

Three options, in order of preference:

1. **Switch the repo to private.** GitHub private repos are free for personal use. This is almost always the right answer — there's no upside to making memory backups public, and the downside is unbounded.
2. **Scrub and rotate.** Replace the PII with `[REDACTED:<type>]` markers in the .md files, commit the redaction, then rotate the actual credential. Use a fresh repo so the old (PII-containing) commits aren't reachable via history rewrite.
3. **Don't back up USER.md.** The script can be configured to skip USER.md via the `SOURCE_FILES` array. MEMORY.md is usually safe to publish with light scrubbing (it's the agent's notes, not the user's). USER.md is the most sensitive.

## Token hygiene for the SSH key

- **Generate per-host, per-purpose.** This backup's SSH key is a write-only GitHub key. Don't reuse your user SSH key.
- **Passphrase: empty** (this is the trade-off for cron compatibility). Compromise mitigation: if the host is compromised, rotate the key at https://github.com/settings/keys immediately. The blast radius is "push to one specific repo", not "full GitHub account".
- **Fine-grained GitHub key.** When adding the SSH key to GitHub, you can scope it to a single repo. (Note: GitHub's per-repo scoping is more reliable for OAuth tokens than for SSH deploy keys; for SSH, the practical scoping is "use a dedicated key for this one repo, don't reuse elsewhere".)
- **Revoke on deprecation.** When you stop using the backup, delete the key at https://github.com/settings/keys. Don't leave orphan write-keys lying around.

## Audit log: who has the private key

Track in the agent's MEMORY.md:

```markdown
## Memory backup key (ssh ed25519)
- Path: ~/.ssh/hermes_backup
- Registered: 2026-06-04 at https://github.com/settings/keys
- Title: "hermes-backup-VM-0-8-ubuntu"
- Permissions: read+write to <user>/<repo> only
- Last rotated: never
```

This makes it possible to know "is the deployed key still authorized?" during incident response.

## When the user is on a cloud VM

Cloud VMs (Tencent Cloud, Aliyun, AWS) have a non-zero risk of being snapped or imaged for debugging/operations. **An unencrypted SSH private key on such a VM is exposed to the cloud provider's operators.** Mitigations:
- Use a key with write-only-to-one-repo scope (limits blast radius)
- Rotate the key quarterly
- Consider encrypting the key at rest with a passphrase + ssh-agent in your interactive shell, accepting that cron will need a re-prompt (or a separate key for cron)

For most personal-Hermes-on-personal-VM use cases, the empty-passphrase + dedicated-key approach is the right trade-off. The threat model isn't nation-state; it's "I lose the laptop".
