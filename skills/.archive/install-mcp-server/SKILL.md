---
name: install-mcp-server
description: 在 Hermes Agent 里安装和配置 stdio/HTTP MCP server 的完整工作流——从查官方文档、装包、注册、调试、到真调验证端到端。基于 Hermes v0.15.1 `mcp_servers` schema。
---

# Hermes MCP Server 安装工作流

在 Hermes 里装一个新 MCP server 的**完整**步骤（含全部 8 个坑）。

## 1. 拿官方文档（先搜，再下手）

**永远**先搜：
- mcp server 自身的 README / 官方文档（GitHub / npm / PyPI / 官网）
- 找 `mcpServers` 配置示例、`env` 变量名、`command` + `args` 模板

**Hermes 官方参考**（**必看**）：
- `mcp-config-reference.md`（schema）
- `use-mcp-with-hermes.md`（stdio 模式示例）
- `user-guide/features/mcp.md` L145 `${VAR}` 替换 + L232 30s auto-reload 窗口

## 2. 装包到 venv（**不**用 `/tmp`，**不**用 uv 默认源）

### 坑 1：uv 装包默认源超时
`uv pip install` 走 `https://pypi.org/simple`，**中国服务器**经常 60s+ 超时。**解法**：用 `pip` 走 `mirrors.tencentyun.com`：
```bash
# 检查 pip 镜像源
grep index-url /etc/pip.conf  # 通常已有 mirrors.tencentyun.com
# 装到 venv
uv venv ~/.hermes/mcp/<server-name>/venv
# 注意：uv venv 不带 pip，要用 uv pip install
uv pip install --python ~/.hermes/mcp/<server-name>/venv/bin/python \
  --index-url http://mirrors.tencentyun.com/pypi/simple \
  <server-package>
# 或用 pip
~/.hermes/mcp/<server-name>/venv/bin/python -m ensurepip
~/.hermes/mcp/<server-name>/venv/bin/python -m pip install <server-package>
```

### 坑 2：`/tmp` 装包重启丢
**永远**装到 `~/.hermes/mcp/<server-name>/`（**不**用 `/tmp`）。

### 坑 3：pip `--target` 装包 server 启动找不到
`pip install --target /some/path` 后，server 用 `#!/usr/bin/python3` 启动时**不**会用 `sys.path` 找包。
**解法**：装到 venv，server 用 venv 的 python；或写 wrapper：
```bash
#!/bin/bash
exec /home/ubuntu/.hermes/mcp/<name>/venv/bin/python -c \
  "from <package>.server import main; main()" "$@"
```

## 3. 写 wrapper 脚本

```bash
#!/bin/bash
# 路径写绝对路径
exec /home/ubuntu/.hermes/mcp/<name>/venv/bin/python -c \
  "from <package>.server import main; main()" "$@
```
chmod +x，**测一遍**（无输出 = server 正常等 stdin）。

## 4. 配置 `mcp_servers` 块

### 坑 4：`hermes mcp add` 触发 30s auto-reload
**user-guide/features/mcp.md L232** 明确：在运行中的 Hermes session 里 `hermes mcp add` 触发 30s 连接窗口，**装包 + 启 server 不够**。
**解法**：用 `hermes config set mcp_servers.<name>.<key> <value>` 手动加字段，**不**用 `mcp add`。或先 `hermes mcp add`（保存 disabled），再 `hermes config set` 调优。

### 坑 4a：`hermes mcp add` CLI 自带限制
- `--preset` **只**支持 `codex`（v0.15.1），**不**支持 minimax / 第三方
- `--args` **不**支持 `-y` 这种**前缀 flag**（npx 风格），会报 `unrecognized arguments: -y`；uvx 调 minimax-coding-plan-mcp **不需要** `-y`，去掉
- 加了 `--env KEY=VALUE` 是直接展开，**没**走 `${VAR}` 替换；想保持 yaml 干净**直接** `hermes config set mcp_servers.<name>.env.KEY ${KEY}`（**最里层**的 env key 大写带点**有 bug**，见坑 6）
- 连接测试超时不重试：测试失败 server 是 disabled，**不**自动重试；改完 wrapper / venv 后**手** `hermes mcp test <name>` 再来一次
- 验证：实测 minimax-coding-plan-mcp 用 `hermes mcp add MiniMax --command uvx --args minimax-coding-plan-mcp --env ...` 触发 41s 超时（装包 + 启 server 超 30s 窗口），改 `hermes config set` + 手 yaml 写**不**超时

### 坑 5：std 不继承 shell env
`mcp_servers.<name>.env` 是**唯一**传给 stdio server 的环境变量。**父 shell 的 env 传不过去**。
**用 `${VAR}` 引用**：`~/.hermes/.env` 里的 `MINIMAX_API_KEY` 自动解析（user-guide/features/mcp.md L145）。

### 坑 6：全大写带点的 key 走不通 `hermes config set`
`hermes config set mcp_servers.<name>.env.MINIMAX_API_KEY 'value'` 会触发 ValueError "Invalid environment variable name"。**绕开**：
- 多层 key 用 `hermes config set mcp_servers.<name>.command ...` 等**最外层**字段
- **最里层**的 env 变量值**直接用 sed 改 yaml**（不通过 Hermes 工具）

### 完整 yaml 模板
```yaml
mcp_servers:
  <name>:
    command: /home/ubuntu/.hermes/mcp/<name>/run-server.sh
    connect_timeout: 120    # 默认 60s，装包+启 server 不够
    timeout: 60
    enabled: true
    env:
      API_KEY: ${API_KEY}        # ← 走 ~/.hermes/.env
      API_HOST: ${API_HOST}
    tools:                       # 可选白名单
      include: [tool_a, tool_b]  # 限流 + 防止意外计费
      resources: false
      prompts: false
```

## 5. 验证（**4 步全部要过**）

```bash
# ① config 合法
hermes config check       # 应过，config version 24+

# ② MCP server 列表显示
hermes mcp list            # 应显示 ✓ enabled

# ③ 连接测试
hermes mcp test <name>     # 应 "Connected (<毫秒>ms)" + "Tools discovered: N"

# ④ 端到端实调（最关键，**绕开 hermes CLI 直接 JSON-RPC stdio**）
```python
# scripts/test_mcp_stdio.py — 复制改 server 路径就能用
import json, subprocess, os, time, fcntl, sys

# 1) 准备 env（**必**显式传，**不**继承父 shell）
env = os.environ.copy()
env['API_KEY'] = 'your-key-here'
env['API_HOST'] = 'https://api.example.com'

# 2) JSON-RPC 4 条消息：initialize → notifications/initialized → tools/list → tools/call
msgs = [
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2024-11-05","capabilities":{},
        "clientInfo":{"name":"test","version":"1.0"}
    }},
    {"jsonrpc":"2.0","method":"notifications/initialized"},
    {"jsonrpc":"2.0","id":2,"method":"tools/list"},
    {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
        "name":"main_tool","arguments":{...}
    }}
]
input_bytes = '\n'.join(json.dumps(m) for m in msgs).encode() + b'\n'

# 3) 启 server 子进程
proc = subprocess.Popen(
    ['/home/ubuntu/.hermes/mcp/<name>/run-server.sh'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=env, bufsize=0
)

# 4) **非阻塞 fd 读**（fastmcp 异步，subprocess.communicate() 抓不全）
fd = proc.stdout.fileno()
flags = fcntl.fcntl(fd, fcntl.F_GETFL)
fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
proc.stdin.write(input_bytes); proc.stdin.close()

# 5) 轮询：拿满 3 条响应（id 1+2+3），或 3-5s 无新数据 → break
all_out = b''
deadline = time.time() + 30
last_data = time.time()
while time.time() < deadline:
    time.sleep(0.2)
    try:
        c = proc.stdout.read(65536)
        if c: all_out += c; last_data = time.time()
    except (BlockingIOError, IOError):
        pass
    if all_out.decode('utf-8', errors='replace').count('"jsonrpc"') >= 3:
        time.sleep(1.5)  # 等 web_search 真返回
    if time.time() - last_data > 4 and all_out: break

proc.kill()
try: proc.wait(timeout=2)
except: pass

# 6) 解析
for line in all_out.decode('utf-8', errors='replace').strip().split('\n'):
    try:
        d = json.loads(line)
        if d.get('id') == 3:
            text = d.get('result', {}).get('content', [{}])[0].get('text', '')
            inner = json.loads(text)  # 内层 JSON
            print(json.dumps(inner, ensure_ascii=False, indent=2))
    except: pass
```

**关键坑**（实战 2026-06-04 minimax-coding-plan-mcp 验证）：

- `subprocess.communicate()` **会丢** web_search 那种**慢响应**（server 异步，process 退出前 flush 不完）。**必须**用非阻塞 fd 轮询
- 收到 `"jsonrpc"` 出现 **3 次** = 3 条响应（initialize / tools/list / tools/call），**不**是 1 条
- 加 `time.sleep(1.5)` 等 `web_search` 真调完（fastmcp 异步，**响应可能分批**到）
```

## 6. 已知 MCP server 清单（**已实测**）

| Server | 端点 / 端点类型 | 状态 |
|---|---|---|
| `MiniMax` (minimax-coding-plan-mcp) | stdio + 调 `https://api.minimaxi.com/v1/coding_plan/search` | ✅ 已配，已实调 |

## 7. 安全 / 持久化

- venv + wrapper 全部放 `~/.hermes/mcp/<name>/`（**不**用 `/tmp`）
- 凭证在 `~/.hermes/.env`（chmod 600），**不**写进 yaml
- yaml 用 `${VAR}` 引用，自动解析
- `tools.include` 白名单限制暴露的工具（防止意外计费工具被 LLM 调）

## 8. 调试速查

| 症状 | 根因 | 解法 |
|---|---|---|
| `Connection closed` < 10s | server 启动报错（包找不到 / env 缺） | 用 stderr 看；用 venv python 跑确认 |
| `Connection timed out` 30s+ | 装包慢（uv 默认源超时） | 改 pip 走腾讯云镜像 |
| `hermes mcp test` 找不到 tools | server 启了但 schema 没暴露 | 看 server 源码 `@mcp.tool()` 装饰器；`hermes mcp test` 返的 stdout 应列 tool 名 |
| `tools/call` 收到但内容空 | server 异步输出，subprocess communicate() 没 flush | 改用非阻塞 fd 读 + 轮询 |
| env 变量 server 收到 None | std 不继承父 env | `mcp_servers.<name>.env` 显式传 + `${VAR}` 引用 |
