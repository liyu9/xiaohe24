---
name: github-auth
description: "GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Authentication, Git, gh-cli, SSH, Setup]
    related_skills: [github-pr-workflow, github-code-review, github-issues, github-repo-management]
---

# GitHub Authentication Setup

This skill sets up authentication so the agent can work with GitHub repositories, PRs, issues, and CI. It covers two paths:

- **`git` (always available)** — uses HTTPS personal access tokens or SSH keys
- **`gh` CLI (if installed)** — richer GitHub API access with a simpler auth flow

## Detection Flow

When a user asks you to work with GitHub, run this check first:

```bash
# Check what's available
git --version
gh --version 2>/dev/null || echo "gh not installed"

# Check if already authenticated
gh auth status 2>/dev/null || echo "gh not authenticated"
git config --global credential.helper 2>/dev/null || echo "no git credential helper"
```

**Decision tree:**
1. If `gh auth status` shows authenticated → you're good, use `gh` for everything
2. If `gh` is installed but not authenticated → use "gh auth" method below
3. If `gh` is not installed → use "git-only" method below (no sudo needed)

---

## Method 1: Git-Only Authentication (No gh, No sudo)

This works on any machine with `git` installed. No root access needed.

### Option A: HTTPS with Personal Access Token (Recommended)

This is the most portable method — works everywhere, no SSH config needed.

**Step 1: Create a personal access token**

Tell the user to go to: **https://github.com/settings/tokens**

- Click "Generate new token (classic)"
- Give it a name like "hermes-agent"
- Select scopes:
  - `repo` (full repository access — read, write, push, PRs)
  - `workflow` (trigger and manage GitHub Actions)
  - `read:org` (if working with organization repos)
- Set expiration (90 days is a good default)
- Copy the token — it won't be shown again

**Step 2: Configure git to store the token**

```bash
# Set up the credential helper to cache credentials
# "store" saves to ~/.git-credentials in plaintext (simple, persistent)
git config --global credential.helper store

# Now do a test operation that triggers auth — git will prompt for credentials
# Username: <their-github-username>
# Password: <paste the personal access token, NOT their GitHub password>
git ls-remote https://github.com/<their-username>/<any-repo>.git
```

After entering credentials once, they're saved and reused for all future operations.

**Alternative: cache helper (credentials expire from memory)**

```bash
# Cache in memory for 8 hours (28800 seconds) instead of saving to disk
git config --global credential.helper 'cache --timeout=28800'
```

**Alternative: set the token directly in the remote URL (per-repo)**

```bash
# Embed token in the remote URL (avoids credential prompts entirely)
git remote set-url origin https://<username>:<token>@github.com/<owner>/<repo>.git
```

**Step 3: Configure git identity**

```bash
# Required for commits — set name and email
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

**Step 4: Verify**

```bash
# Test push access (this should work without any prompts now)
git ls-remote https://github.com/<their-username>/<any-repo>.git

# Verify identity
git config --global user.name
git config --global user.email
```

### Option B: SSH Key Authentication

Good for users who prefer SSH or already have keys set up.

**Step 1: Check for existing SSH keys**

```bash
ls -la ~/.ssh/id_*.pub 2>/dev/null || echo "No SSH keys found"
```

**Step 2: Generate a key if needed**

```bash
# Generate an ed25519 key (modern, secure, fast)
ssh-keygen -t ed25519 -C "their-email@example.com" -f ~/.ssh/id_ed25519 -N ""

# Display the public key for them to add to GitHub
cat ~/.ssh/id_ed25519.pub
```

Tell the user to add the public key at: **https://github.com/settings/keys**
- Click "New SSH key"
- Paste the public key content
- Give it a title like "hermes-agent-<machine-name>"

**Step 3: Test the connection**

```bash
ssh -T git@github.com
# Expected: "Hi <username>! You've successfully authenticated..."
```

**Step 4: Configure git to use SSH for GitHub**

```bash
# Rewrite HTTPS GitHub URLs to SSH automatically
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

**Step 5: Configure git identity**

```bash
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

---

## Method 2: gh CLI Authentication

If `gh` is installed, it handles both API access and git credentials in one step.

### Installing gh without sudo (egress-restricted hosts)

`apt install gh` requires sudo AND the GitHub CLI apt repo (not in default Ubuntu). On a cloud VM with no sudo, install gh to `~/.local/bin/` from the GitHub release tarball.

**Direct download from `github.com` is often QoS-throttled** on egress-restricted hosts (Tencent Cloud CVM, etc.) — `codeload.github.com` can hand out 200 on the homepage but stall 30+ seconds on the actual binary. **Use a known-good mirror.** From a Tencent Cloud CVM, `gh-proxy.com` returns a 18MB tarball in ~2 seconds (verified 2026-06-04):

```bash
# Download (mirror if direct path is throttled)
GH_VER="2.81.0"
mkdir -p ~/.local/bin
curl -fL -o /tmp/gh.tar.gz --connect-timeout 8 \
  "https://gh-proxy.com/https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_linux_amd64.tar.gz" \
  || curl -fL -o /tmp/gh.tar.gz --connect-timeout 8 \
       "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_linux_amd64.tar.gz"

# Extract and install to user bin
cd /tmp && tar xzf gh.tar.gz
install -m 0755 gh_${GH_VER}_linux_amd64/bin/gh ~/.local/bin/gh
~/.local/bin/gh --version   # confirm

# Clean up
rm -rf /tmp/gh.tar.gz /tmp/gh_${GH_VER}_linux_amd64
```

Verify `~/.local/bin` is on PATH (it usually is for non-root users; if `which gh` is empty, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`).

### Interactive Browser Login (Desktop)

```bash
gh auth login
# Select: GitHub.com
# Select: HTTPS
# Authenticate via browser
```

### Token-Based Login (Headless / SSH Servers)

```bash
echo "<THEIR_TOKEN>" | gh auth login --with-token

# Set up git credentials through gh
gh auth setup-git
```

### Verify

```bash
gh auth status
```

**Where to put the token long-term on a Hermes host:**

- `~/.hermes/.env` (chmod 600) — Hermes's standard secrets file. Add `GH_TOKEN=ghp_...` and the next process startup reads it. Already `source`-d by Hermes's gateway, so env-var-based tools (`gh`, `curl` with `$GH_TOKEN`) Just Work after a session restart.
- DO NOT add to shell rc files (`~/.bashrc`) — leaks to child processes of unrelated tools.
- DO NOT leave it in the cron job's prompt string — visible in `cron list` / session logs.
- `gh auth status` reports `Logged in to <user> (GH_TOKEN)` when sourced from `GH_TOKEN` env, which is fine for automation.

---

## Using the GitHub API Without gh

When `gh` is not available, you can still access the full GitHub API using `curl` with a personal access token. This is how the other GitHub skills implement their fallbacks.

### Setting the Token for API Calls

```bash
# Option 1: Export as env var (preferred — keeps it out of commands)
export GITHUB_TOKEN="<token>"

# Then use in curl calls:
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user
```

### Extracting the Token from Git Credentials

If git credentials are already configured (via credential.helper store), the token can be extracted:

```bash
# Read from git credential store
grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|'
```

### Helper: Detect Auth Method

Use this pattern at the start of any GitHub workflow:

```bash
# Try gh first, fall back to git + curl
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  echo "AUTH_METHOD=gh"
elif [ -n "$GITHUB_TOKEN" ]; then
  echo "AUTH_METHOD=curl"
elif [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
  export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
  echo "AUTH_METHOD=curl"
elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
  export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
  echo "AUTH_METHOD=curl"
else
  echo "AUTH_METHOD=none"
  echo "Need to set up authentication first"
fi
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git push` asks for password | GitHub disabled password auth. Use a personal access token as the password, or switch to SSH |
| `remote: Permission to X denied` | Token may lack `repo` scope — regenerate with correct scopes |
| `fatal: Authentication failed` | Cached credentials may be stale — run `git credential reject` then re-authenticate |
| `ssh: connect to host github.com port 22: Connection refused` | Try SSH over HTTPS port: add `Host github.com` with `Port 443` and `Hostname ssh.github.com` to `~/.ssh/config` |
| Credentials not persisting | Check `git config --global credential.helper` — must be `store` or `cache` |
| Multiple GitHub accounts | Use SSH with different keys per host alias in `~/.ssh/config`, or per-repo credential URLs |
| `gh: command not found` + no sudo | Use git-only Method 1 above — no installation needed |

---

## Egress-blocked environments: when the agent can reach `api.github.com` but not `github.com`

This is a real pattern on hardened / corporate / GFW-ed hosts: the API subdomain (`api.github.com:443`) and the raw-download subdomain (`codeload.github.com:443`) are reachable, but the apex `github.com:443`, `github.com:22` (SSH), and `github.com:9418` (git://) are all RST'd or dropped. DNS resolves fine, so the failure is at the TCP/transport layer, not DNS.

**Quick diagnostic** (run before asking the user for a token — saves them typing if push is going to die anyway):

```bash
for host in github.com api.github.com codeload.github.com qt.gtimg.cn; do
  printf '%-22s ' "$host:"
  curl -sI -o /dev/null -w 'HTTP %{http_code}  TIME %{time_total}s  IP %{remote_ip}\n' \
    --connect-timeout 5 "https://$host" 2>&1
done
```

Interpretation:
- `HTTP 000` or `TIME > 3s` on `github.com` while `api.github.com` returns 200 → egress-blocked
- All `HTTP 000` → full network outage (different problem)
- All `HTTP 200` → auth/credential problem, not network — go back to the decision tree above

**If egress is blocked, four fallbacks (in order of effort):**

1. **HTTP/HTTPS proxy** — ask the user for `http://host:port` (and creds). Configure git:
   ```bash
   git config --global http.proxy  http://user:pass@host:port
   git config --global https.proxy http://user:pass@host:port
   # SOCKS5 also works: socks5://host:1080
   ```
   Then retry `git push`. This is the only path that actually pushes from the agent.

2. **SSH over HTTPS port 443** — if `:443` to `ssh.github.com` is reachable (it usually is, even when apex is blocked):
   ```bash
   # ~/.ssh/config
   Host github.com
       Hostname ssh.github.com
       Port 443
       User git
   ```
   Then use `git@github.com:owner/repo.git` as the remote URL. Requires SSH key already authorized (see Method 1B above).

3. **Local tarball handoff** — `git push` is impossible from the agent, but the user can push from their own machine. Package the local repo (with full git history) and hand it to them:
   ```bash
   tar czf /tmp/<repo>-backup-<date>.tar.gz -C /parent <repo>/
   ```
   Send the file to the user via Feishu / attachment. They untar, `git remote add origin …`, and `git push` themselves.

4. **GitHub mirror sites** (`ghproxy.com`, `gh-proxy.com`, `gh.idayer.com`, `kkgithub.com`, etc.) — **DO NOT skip fallbacks 1–3 for this**. Mirrors are an attractive nuisance: they DO work for `git clone` (read), so the global-`insteadOf` rewrite trick
   ```bash
   git config --global url."https://gh-proxy.com/https://github.com".insteadOf "https://github.com"
   ```
   will succeed for fetches/clones, lulling the agent into thinking push will work. **It will not.** Empirically (June 2026):
   - `ghproxy.com` / `mirror.ghproxy.com` / `codeload.ghproxy.com` — only mirror `codeload.github.com` GETs; push returns 403.
   - `gh-proxy.com` — same: 403 on push despite 200 on `curl -I` for the homepage.
   - `gh.idayer.com` — passes the request through but returns `not a git repository` on `/info/refs` (it doesn't speak git smart-http).
   - `kkgithub.com` — homepage 200, push behavior untested but unlikely to differ.
   - The asymmetry is structural: these mirrors are CDN caches of `codeload.github.com` tarballs, not transparent reverse proxies for `git-receive-pack`. **There is no public GitHub mirror that proxies push as of this writing.**

   Don't waste cycles configuring mirrors for a push — go straight to fallbacks 1, 2, or 3.

**Diagnostic traps (learned the hard way):**

- `curl -I https://mirror.site` returning `HTTP 200` does NOT mean push will work. Always end the diagnostic with an actual `git ls-remote https://mirror.site/https://github.com/<owner>/<repo>.git` and check it returns real refs (not 403 / "not a git repository" / empty).
- The "TIME 0.6s" `curl` returns for an unreachable host can be a false-positive. `curl` sometimes reports the TCP-RST round-trip time as a fast success. Force `--connect-timeout 5` AND check the exit code AND check `HTTP 000` explicitly. `HTTP 000` = connection died, regardless of how fast the death was.
- `timeout 5 git ls-remote git://github.com/...` with `RC=0` and empty stdout is a trap — the timeout fired (RC should be 124) but a subshell piped through `head` masked it. Use `; echo RC=$?` *after* the pipe, not in the same chain, or you'll think it succeeded.
- **Classic vs fine-grained: the `admin:public_key` blast radius.** GitHub classic PATs default to scope `repo` + `admin:public_key` + `admin:repo_hook` + `workflow` (and more). `admin:public_key` lets the bearer **add, edit, and delete the user's own SSH keys at https://github.com/settings/keys** — i.e., an attacker can plant their own SSH key and silently gain permanent account access. Fine-grained tokens cannot have `admin:public_key` (it's an account-level scope, not per-repo), so the blast radius collapses to a single repository. **Default recommendation: fine-grained, 1 repo, `Contents: Read and write` only, 7-day expiration.** Only fall back to classic if the workflow genuinely needs account-level operations (which is rare). See `references/token-hygiene.md` for the user-facing walkthrough.
- **The classic token "I have permissions I never use" trap.** Right after `gh auth login` with a classic token, run `gh auth status | grep -i scope` and you may see 5+ scopes the user never consciously authorized. List the actual permissions in plain text in the completion report, and recommend the fine-grained replacement.
- **The "fine-grained can't `issue delete`" trade-off.** Fine-grained's `Issues: Read and write` does NOT include delete. If the workflow needs to delete issues/comments, fine-grained won't work — but in that case the workflow should reconsider whether deleting issues is the right action. Classic PATs include `repo` which DOES include issue delete.
- **The "private repos silently accessible" pattern.** When authenticating with `repo` scope, `gh repo list <user> --json ...` returns BOTH public and private repos. The agent may not have been told about the user's private repos. **Treat the presence of private repos in the listing as a privacy alarm**: list them in the verification report, recommend scoping down to single-repo, and warn that the token can read all of them.
- **The "HTTPS write is throttled but HTTPS read + SSH are fine" host assumption.** On hosts with QoS-throttled egress to `github.com:443` for `POST/PUT/PATCH/DELETE` (e.g., some Tencent Cloud CVM egress paths), `gh` POST operations against small payloads (<1KB) still succeed because the QoS triggers on bulk transfer, but `git push` over HTTPS of a multi-commit diff stalls at 60s. **Verify the host's HTTPS-write capability separately from HTTPS-read.** See the cloud-network-diagnostics skill for the probe.
- **`GH_TOKEN` env-var beats `gh auth login`.** On a headless host, the user can't complete `gh auth login`'s browser flow. `export GH_TOKEN=ghp_...` is the no-browser equivalent, and `gh` honors it automatically. Put it in `~/.hermes/.env` (chmod 600) and the next process startup picks it up. Do NOT put it in `~/.bashrc` (leaks to unrelated subprocesses).
- **`gh` doesn't auto-install.** Don't burn 60s trying `apt install gh` or downloading a 100MB .deb from `cli.github.com/releases` (also slow on egress-blocked hosts). If `which gh` is empty, go git-only immediately.
- `gh` doesn't auto-install. Don't burn 60s trying `apt install gh` or downloading a 100MB .deb from `cli.github.com/releases` (also slow on egress-blocked hosts). If `which gh` is empty, go git-only immediately.
- **The "token's true blast radius is wider than the user knows" reporting duty.** After any successful GitHub auth, before declaring done, run `gh api /user/keys --jq '.[].title'` and `gh repo list <user> --json name,isPrivate` and include the results in the completion report. The owner is a 产品经理 with private Obsidian / prompt-engineering repos and does not expect the agent to silently enumerate them. Make the blast radius visible.

## References

- `references/token-hygiene.md` — full token-creation walkthrough (fine-grained vs classic), revocation flow, "what to NEVER do" list, and the script for post-auth visibility reporting. Read this **before any GitHub auth completes** so the completion report includes the right blast-radius disclosures.

**Common clarifying question to ask:** "这台机器到 `github.com` 的 443/22/9418 都不通，但 `api.github.com` 通 — 你那边 (a) 有 HTTP 代理可以配吗，(b) 我打包成 tar 发你本机自己推，还是 (c) 改用 SSH 走 443 端口？"

**Token hygiene when push fails:** if the user pasted a PAT into chat, **immediately remind them to revoke it** at https://github.com/settings/tokens after the failed attempt, regardless of which fallback you ultimately use. The token is in chat history (server-side) and the agent cannot scrub it. The right PAT settings for this kind of work are: fine-grained, scope = single public repo, permission = `Contents: Read and write` only, expiration = 7 days.
