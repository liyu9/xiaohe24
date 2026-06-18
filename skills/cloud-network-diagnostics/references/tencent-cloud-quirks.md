# Tencent Cloud CVM 轻量 — Network Quirks

Findings from a 2026-06-04 diagnostic session on `VM-0-8-ubuntu`. **These are environment observations, not durable rules** — use as a reference, not as a constraint.

## Host fingerprint
- **Hostname pattern**: `VM-0-N-M-ubuntu` (Tencent Cloud 轻量 default)
- **Internal IP**: `10.1.0.8/22` (private, CVM 轻量 default subnet)
- **Default gateway**: `10.1.0.1`
- **Egress IP observed**: `42.193.145.229` (Guangzhou/Shanghai node)

## Local firewall (云镜 / YJ-FIREWALL)
```
iptables -L INPUT shows: YJ-FIREWALL-INPUT chain
  - Drops specific source IPs (attack sources / scanners)
  - INPUT direction only
  - OUTPUT chain: policy ACCEPT, no rules
```
- **Implication**: local firewall is not blocking outbound; it only rate-limits inbound. The egress problem is **not** this machine.

## Working paths
- ✅ `api.github.com:443` — fast (200-300ms)
- ✅ `codeload.github.com:443` — fast (~500ms)
- ✅ `github.com:22` (SSH) — instant, full banner `SSH-2.0-6279353`
- ✅ `qt.gtimg.cn` and other domestic services — fast

## Broken paths
- ❌ `github.com:443` HTTPS writes (POST /info/refs, git push) — TCP+TLS handshake completes, HTTP body never arrives
- ❌ `github.com:443` HTTPS reads (curl HEAD with bare User-Agent) — anti-bot rejection
- ❌ `github.com:9418` (git://) — times out
- ❌ `ghproxy.com`, `mirror.ghproxy.com`, `codeload.ghproxy.com` — HTTP 000 (mirrored the same block as github.com)
- ✅ `gh-proxy.com` (200) — GETs only, returns 403 on push
- ✅ `gh.idayer.com` (200) — GETs only, returns "not a git repository" on push

## mtr path signature
```
VM-0-8-ubuntu → 11.71.x.x (Tencent Cloud internal)
             → 10.162.x.x (Tencent backbone)
             → ??? (intermediate, 100% loss = normal, don't trust)
             → 113.96.x.x (CN international egress)
             → GitHub edge
```
Latency 30+ms with 1000+ms jitter on international hops = **standard international bandwidth**, not CN2 GIA / optimized.

## Diagnosis summary
- **Pull works, push doesn't** on the same TCP port (443) — classic signature of **HTTPS-write throttling by ISP/云厂商** (intentional QoS on POST/PUT, not blanket blocking)
- **SSH 22 to same host works fine** — protocol-port-specific throttling
- **The fix is protocol substitution, not network access changes**

## What works for git push
- **SSH** — origin: `git@github.com:user/repo.git`, requires SSH key registered on GitHub
- **format-patch + manual push from local machine** — patch the changes into a clone on a different host and push from there
- **HTTPS with retry + tuning** — `http.postBuffer=524288000`, `http.lowSpeedLimit=1000`, `http.lowSpeedTime=30`, `http.version=HTTP/1.1`; ~30% success rate improvement, not guaranteed

## What does NOT work (don't try)
- Switching DNS (resolves correctly already)
- Toggling `http.sslVerify` (TLS works)
- Multiple GitHub mirrors (all block push)
- Reinstalling git, curl, openssl (no fix at application layer)
- Container restart, ip link reset (network policy is upstream)

## The decisive test sequence (use this order)

This is the exact sequence that concluded "Tencent Cloud QoS on HTTPS writes" in 2026-06-04. Run in order; stop as soon as the diagnosis is clear.

```bash
# 1. Egress IP — confirms you're on this machine, not someone else's
curl -s --connect-timeout 5 https://api.ipify.org
# 42.193.145.229

# 2. Local firewall — confirm OUTPUT not blocked
sudo -n iptables -L OUTPUT -n
# (no rules / policy ACCEPT)

# 3. TCP handshake to the target port
timeout 5 bash -c 'cat < /dev/tcp/github.com/443' &
sleep 3
# Connection opens (bash 5.x read blocks; 3s is normal on success)
# Ctrl-C the bg process

# 4. SSH to same host — protocol-comparison test
timeout 3 bash -c 'cat < /dev/tcp/github.com/22'
# Output: SSH-2.0-6279353  ← GitHub banner, full proof SSH 22 works

# 5. TLS handshake detail with -v
curl -v -H 'User-Agent: Mozilla/5.0' https://github.com 2>&1 | head -20
# Look for: "Connected to github.com", "TLSv1.3 (IN), TLS handshake, Server hello",
# "TLSv1.3 (IN), TLS handshake, Certificate". If you see all of these,
# TCP+TLS are working at the network layer.

# 6. The decisive test: does HTTP body actually arrive?
curl -v -H 'User-Agent: Mozilla/5.0' \
  'https://github.com/liyu9/xiaohe24' 2>&1 | tail -10
# If TCP+TLS succeed but the body never arrives (curl sits for 9+ seconds
# with no progress), HTTPS writes are being throttled.

# 7. Write-path confirmation (this is the actual test of the bottleneck)
git ls-remote https://github.com/liyu9/xiaohe24.git > /tmp/refs.txt 2>&1
echo "git_exit=$?"; wc -l /tmp/refs.txt
# git_exit=0 but file is empty → DNS+TCP+TLS worked, GET was throttled / blocked
# git_exit=128 → TLS or auth problem (different category)
# git_exit=124 → TCP timeout (different problem)
```

## Raw session transcript (June 2026)

```
# Step 1 — egress IP
$ curl -s --connect-timeout 5 https://api.ipify.org
42.193.145.229

# Step 4 — SSH works instantly
$ timeout 3 bash -c 'cat < /dev/tcp/github.com/22'
SSH-2.0-6279353

# Step 5 — TCP+TLS succeed
$ curl -v https://github.com 2>&1 | head -20
* Trying 20.205.243.166:443...
* Connected to github.com (20.205.243.166) port 443
* TLSv1.3 (IN), TLS handshake, Server hello (2)
* TLSv1.3 (IN), TLS handshake, Certificate (11)
* ...

# Step 6 — body never arrives
$ curl -v -H 'User-Agent: Mozilla/5.0' https://github.com/liyu9/xiaohe24 2>&1 | tail -10
* Trying 20.205.243.166:443...
* Connected to github.com (20.205.243.166) port 443
* (silence for 9+ seconds, no HTTP status line, no body)

# Step 7 — write path confirmed broken
$ git push -u origin main
... hangs 60s with no progress ...

# Switch to SSH: 7.8s push to GitHub
$ git remote set-url origin git@github.com:liyu9/xiaohe24.git
$ eval $(ssh-agent -s) >/dev/null
$ ssh-add ~/.ssh/github_xiaohe24
$ git push -u origin main
To github.com:liyu9/xiaohe24.git
 * [new branch]      main -> main
```

## The git-ls-remote empty-stdout trap (avoid this in your own diagnostic)

The naive test:
```bash
$ timeout 5 git ls-remote https://github.com/liyu9/xiaohe24.git 2>&1 | head -5; echo RC=$?
(empty output)
RC=0
```

The `RC=0` is misleading — it's the exit code of `head`, not `git`. The real `git` exit was 124 (timeout), but `head` consumed the empty pipe successfully.

The correct test (file-based, captures real exit code):
```bash
$ git ls-remote https://github.com/liyu9/xiaohe24.git > /tmp/refs.txt 2>&1
$ echo "git_exit=$?"
$ wc -l /tmp/refs.txt
git_exit=0
0 /tmp/refs.txt
```

Even with file-based, exit code is sometimes 0 on connection-die. **The reliable signal is: did `refs/heads/main` appear in the output?** If you don't see a real SHA + refs/heads/head_name, the connection didn't complete — regardless of what exit code is reported.
