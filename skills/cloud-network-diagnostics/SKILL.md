---
name: cloud-network-diagnostics
description: Diagnose why an outbound network path (HTTPS, SSH, API call, git push) fails from a cloud server. Use when the user reports "X is unreachable", "can't push to GitHub", "API timeout", "is this URL blocked", or when curl/wget/git returns 000/timeout. Covers multi-layer diagnosis from DNS through TCP/TLS/HTTP, distinguishing local firewall, routing, ISP throttling, and application-level issues.
---

# Cloud Network Diagnostics

When a network path appears broken, the failure could be in any of 7 layers. **Diagnose from outside in** (DNS → route → TCP → TLS → HTTP → application) before assuming a cause.

## When to use

- `git push` fails / times out
- API call returns 000 or hangs
- `curl https://example.com` returns nothing
- "Is this URL blocked?"
- SSH works but HTTPS doesn't (or vice versa)
- Vague "internet is slow" without specifics
- A specific remote (GitHub, GitLab, S3) behaves differently from the public internet

## The 7 layers

1. **DNS** — Is the hostname resolving? `getent hosts <name>`
2. **Local iptables/nftables OUTPUT** — Is the local firewall blocking? `sudo iptables -L -n`
3. **Routing** — Where does the packet go? `ip route show default`
4. **TCP handshake** — Can SYN/SYN-ACK/ACK complete? `bash -c 'cat < /dev/tcp/host/port'`
5. **TLS handshake** — Can TLS negotiation complete? `curl -v https://...` (look for "Server hello", "Certificate")
6. **HTTP request/response** — Does GET return a body? `curl -v -H 'User-Agent: ...'`
7. **Application protocol** — git push, SSH, custom API

Always work top-down. A failure at layer 6 doesn't mean layer 6 is broken — it could be a layer 1-5 issue that the application is sensitive to.

## Distinguishing issue types

| Symptom | Likely cause |
|---|---|
| `getent hosts` returns nothing | DNS misconfigured |
| DNS resolves, TCP fails on all ports | Routing / ISP blackhole |
| TCP works on 22 but not 443 | Local firewall or ISP throttling by port |
| TCP works, TLS fails | TLS interception (corporate proxy, GFW MITM) |
| TLS works, HTTP GET works, POST hangs | Application-layer or QoS throttling on writes |
| All HTTPS works, SSH doesn't | Local firewall rule, not network |
| TCP works, HTTP times out, but `mtr` shows path OK | NAT/conntrack state issue or upstream congestion |
| One mirror works, another 000 | DNS-based filtering, not network-wide block |

## Common pitfalls (READ THESE)

- **`curl -sI` (HEAD) often returns 000 for GitHub** even when GET works — GitHub's edge rejects empty User-Agent. Always use `curl -v` with a real User-Agent (`Mozilla/5.0`) before declaring the path broken.
- **`bash /dev/tcp/host/port` blocks for 3+ seconds on a successful connection** waiting for data. Don't confuse this with timeout — it's bash waiting for the server to send something on the open socket.
- **`mtr -T` (TCP mode) requires root or `CAP_NET_RAW`.** Plain ICMP `mtr` works for most cases without privileges.
- **HTTP/2 multiplexing can mask individual request failures** when one stream hangs in a connection that looks otherwise healthy.
- **HTTPS POST/PUT (writes) is more often throttled than GET (reads)** even on the same TCP connection — this is the most common cause of "git pull works, git push doesn't" or "GET works, POST doesn't" symptoms. A successful TLS handshake does NOT prove POST will work.
- **GitHub public mirror sites — from Tencent Cloud, only 2 of the common 6 are actually reachable, and NONE proxy push.** Reachability matrix (verified 2026-06-04 from `VM-0-8-ubuntu`, exit IP `42.193.145.229`):
  | Mirror | Reachable? | GET proxies? | Push proxies? | Large file (18MB tarball)? |
  |---|---|---|---|---|
  | `ghproxy.com` | ❌ HTTP 000 | — | — | — |
  | `mirror.ghproxy.com` | ❌ HTTP 000 | — | — | — |
  | `codeload.ghproxy.com` | ❌ HTTP 000 | — | — | — |
  | `gh-proxy.com` | ✅ HTTP 200 (~270ms) | ✅ | ❌ 403 | ✅ ~2s for 18MB (12.8 MB/s) |
  | `gh.idayer.com` | ✅ HTTP 200 (~970ms) | ✅ | ❌ "not a git repository" | (untested, assume slower) |
  | `kkgithub.com` | ✅ HTTP 200 (3.4s) | ✅ | ❌ | (untested) |
  | `hub.fastgit.xyz` / `gitclone.com` / `ghps.cc` / `hub.0z.gs` | ❌ HTTP 000 | — | — | — |
  **Stop wasting time on `ghproxy.com`** — it's the most commonly suggested in Chinese-language stackoverflow answers but it has been blocked from Tencent Cloud egress for a long time. The two that actually work for reads are `gh-proxy.com` (faster) and `gh.idayer.com` (slower but stable). **Neither proxies push.** When push is the goal and `github.com:443` is QoS-throttled, go to SSH.
  **New (2026-06-04):** `gh-proxy.com` also serves as a viable mirror for **downloading large release tarballs** (e.g. `gh` CLI binary, ~18MB) when `github.com` / `codeload.github.com` stalls on HTTPS. This is the cleanest path for installing `gh` on a no-sudo Tencent Cloud host: `curl -L 'https://gh-proxy.com/https://github.com/cli/cli/releases/download/vX.Y.Z/gh_X.Y.Z_linux_amd64.tar.gz' -o /tmp/gh.tar.gz` (2 seconds).
- **mtr 100% loss at intermediate hops is normal** for routers that don't reply to ICMP TTL exceeded. Look at the destination hop, not intermediate loss%.
- **`git ls-remote` empty-stdout / `RC=0` trap.** When you run `timeout 5 git ls-remote https://... 2>&1 | head -5; echo RC=$?`, the `RC` printed is the exit status of `head`, NOT `git`. If `git` was killed by timeout (real exit 124), `head` succeeded and you see `RC=0` with empty stdout — which looks like "refs didn't exist" but actually means "the connection died". To check `git`'s real exit code, write to a file first: `git ls-remote ... > /tmp/refs.txt 2>&1; echo "git=$?"; wc -l /tmp/refs.txt`. Empty file + `git=124` = timeout. Empty file + `git=0` = no refs (likely a path typo). This trap bit me while diagnosing Tencent Cloud → GitHub HTTPS-write throttling and led to chasing a dead-end "URL might be wrong" theory for a turn.
- **`curl -sI` (HEAD) on GitHub often returns 000 even when GET works** because GitHub's edge rejects bare-User-Agent HEAD. Always use a real `User-Agent: Mozilla/5.0` header and `curl -v` (verbose) to see TCP/TLS detail. `curl --connect-timeout 5 -L` is the minimum for a sane test.
- **Decision pivot when TCP+TLS work but HTTP body hangs: switch protocols, don't keep debugging.** Once you see "TLS handshake succeeded, no application response for 9+ seconds", the network is functional; the path is being throttled. Stop probing and go to fallbacks: SSH (port 22) for git, or proxy/relay for HTTPS POST. See `github-auth` for the SSH keypair dance (generate keypair → user pastes pubkey → `git remote set-url origin git@github.com:...`).

## When to stop diagnosing and try alternatives

If layers 1-5 all pass and HTTP GET works but POST/PUT doesn't, **the network is functional** — the issue is application-layer throttling. Stop diagnosing and try:

- **Switch to SSH (port 22)** — often exempt from HTTPS QoS throttling; the highest-success fallback for git push
- **Use a different protocol** — git over SSH instead of HTTPS
- **Retry with backoff** — QoS is often probabilistic, 3-5 retries with `git push` may succeed
- **Export patch and apply from a different host** — `git format-patch` / `git am`
- **Use a different egress path** — wireguard/VPN/tunnel to a host with better routing
- **Tune HTTPS** — `http.postBuffer`, `http.lowSpeedLimit`, `http.lowSpeedTime`, `http.version=HTTP/1.1` (modest improvement, not guaranteed)

## Reference

- `references/tencent-cloud-quirks.md` — Specific findings for Tencent Cloud CVM 轻量 (the user's confirmed environment): VM-0-8-ubuntu hostname, YJ-FIREWALL INPUT chain, mirror site reachability matrix, QoS-on-HTTPS-write symptom
- `scripts/diagnose-egress.sh` — Re-runnable script that runs layers 1-7 against a target host (DNS, iptables, routing, egress IP, TCP, TLS+HTTP, mtr). Use this instead of hand-typing the 6 commands.

## Quick commands cheatsheet

```bash
# Layer 1: DNS
getent hosts github.com
dig +short github.com

# Layer 2: Local firewall OUTPUT
sudo iptables -L OUTPUT -n

# Layer 3: Routing
ip route show default
ip -4 addr show

# Layer 4: Egress IP (confirm NAT/who you appear as)
curl https://api.ipify.org

# Layer 5: TCP handshake (note: 3s read delay on success is normal)
time bash -c 'cat < /dev/tcp/github.com/22' &

# Layer 6: TLS + HTTP
curl -v -H 'User-Agent: Mozilla/5.0' https://github.com 2>&1 | head -30

# Layer 7: Path
mtr -n -r -c 5 github.com            # ICMP, no privileges needed
sudo mtr -T -P 443 -n -r -c 5 github.com  # TCP, needs root
```

## Token safety reminder (when git push is the goal)

When the user provides a token (GitHub PAT, API key) to use for push/auth, treat it as a secret:

- Don't echo it in tool arguments if avoidable
- If it ends up in command output, mention it in your reply and recommend revocation
- Suggest `https://github.com/settings/tokens` (or provider equivalent) at end of task
- Clean `git config` URLs of tokens after use (`git remote set-url origin https://github.com/...`)
- A token in `git remote -v` output will be in shell history — clean it
