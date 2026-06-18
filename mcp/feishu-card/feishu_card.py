#!/usr/bin/env python3
"""
feishu_card.py — 飞书 interactive 卡片消息 + 流式更新

功能：
  1) 拿 tenant_access_token（自动缓存 2h）
  2) send_card(receive_id, card_json) → 返回 message_id
  3) update_card(message_id, card_json) → PATCH 更新
  4) CLI 模式：python feishu_card.py send <receive_id> <card.json>
                python feishu_card.py update <message_id> <card.json>

凭证读取（按优先级）：
  1) 环境变量 FEISHU_APP_ID + FEISHU_APP_SECRET
  2) ~/.hermes/feishu_credentials.json（chmod 600）
  3) ~/.hermes/.env 的 FEISHU_APP_ID + FEISHU_APP_SECRET

用法示例：
  python feishu_card.py send ou_xxxxx templates/alert.json
  python feishu_card.py update om_xxxxx templates/alert_updated.json
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# 凭证管理
# ---------------------------------------------------------------------------

CREDS_PATH = Path.home() / ".hermes" / "feishu_credentials.json"
ENV_PATH = Path.home() / ".hermes" / ".env"


def load_credentials():
    """按优先级读 (app_id, app_secret)。"""
    # 1) 环境变量
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret

    # 2) credentials.json
    if CREDS_PATH.exists():
        try:
            data = json.loads(CREDS_PATH.read_text())
            if data.get("app_id") and data.get("app_secret"):
                return data["app_id"], data["app_secret"]
        except (json.JSONDecodeError, OSError):
            pass

    # 3) ~/.hermes/.env
    if ENV_PATH.exists():
        env = {}
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
        if env.get("FEISHU_APP_ID") and env.get("FEISHU_APP_SECRET"):
            return env["FEISHU_APP_ID"], env["FEISHU_APP_SECRET"]

    raise RuntimeError(
        "未找到飞书凭证。请设置环境变量 FEISHU_APP_ID + FEISHU_APP_SECRET，"
        f"或在 {CREDS_PATH} 写入 JSON。\n"
        f"格式：{{'app_id': 'cli_xxx', 'app_secret': 'xxx'}}"
    )


def save_credentials(app_id: str, app_secret: str):
    """保存凭证到 credentials.json（chmod 600）。"""
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDS_PATH.write_text(json.dumps({
        "app_id": app_id,
        "app_secret": app_secret,
    }, ensure_ascii=False, indent=2))
    os.chmod(CREDS_PATH, 0o600)


# ---------------------------------------------------------------------------
# Token 管理（缓存 2h）
# ---------------------------------------------------------------------------

_TOKEN_CACHE = {"token": None, "expires_at": 0}


def get_tenant_token(app_id: str, app_secret: str) -> str:
    """拿 tenant_access_token（缓存 2h，剩 60s 自动续）。"""
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] - 60 > now:
        return _TOKEN_CACHE["token"]

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    if data.get("code") != 0:
        raise RuntimeError(f"拿 token 失败: code={data.get('code')} msg={data.get('msg')}")

    _TOKEN_CACHE["token"] = data["tenant_access_token"]
    _TOKEN_CACHE["expires_at"] = now + data.get("expire", 7200)
    return _TOKEN_CACHE["token"]


# ---------------------------------------------------------------------------
# 飞书 API
# ---------------------------------------------------------------------------

def _request(method: str, url: str, token: str, body: dict = None) -> dict:
    """统一 HTTP 调用，返 JSON。"""
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # 飞书错误：把 body 一起返出来
        try:
            err_body = json.loads(e.read())
        except Exception:
            err_body = {"raw": "<unreadable>"}
        return {"code": e.code, "http_error": True, **err_body}


def send_card(receive_id: str, card: dict, receive_id_type: str = "open_id") -> str:
    """
    发 interactive 卡片到指定会话。
    返回 message_id（用于后续 PATCH 更新）。
    raise RuntimeError 当失败。
    """
    app_id, app_secret = load_credentials()
    token = get_tenant_token(app_id, app_secret)

    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
    body = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    result = _request("POST", url, token, body)

    if result.get("code") != 0:
        raise RuntimeError(
            f"发卡片失败: code={result.get('code')} "
            f"msg={result.get('msg')} "
            f"data={result.get('data', {})}"
        )

    msg_id = result.get("data", {}).get("message_id")
    if not msg_id:
        raise RuntimeError(f"发卡片成功但无 message_id: {result}")
    return msg_id


def update_card(message_id: str, card: dict) -> bool:
    """
    PATCH 更新已发的卡片内容（同 message_id）。
    返回是否成功。
    """
    app_id, app_secret = load_credentials()
    token = get_tenant_token(app_id, app_secret)

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}"
    body = {
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    result = _request("PATCH", url, token, body)

    if result.get("code") != 0:
        raise RuntimeError(
            f"PATCH 失败: code={result.get('code')} "
            f"msg={result.get('msg')} "
            f"data={result.get('data', {})}"
        )
    return True


def reply_card(message_id: str, card: dict) -> str:
    """
    回复指定消息（用 message_id 作为 reply target）。
    返回新 message_id。
    """
    app_id, app_secret = load_credentials()
    token = get_tenant_token(app_id, app_secret)

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    body = {
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
        "root_id": message_id,  # reply 模式
    }
    result = _request("POST", url, token, body)

    if result.get("code") != 0:
        raise RuntimeError(
            f"回复失败: code={result.get('code')} "
            f"msg={result.get('msg')}"
        )

    return result.get("data", {}).get("message_id", "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_card_from_arg(arg: str) -> dict:
    """arg 可以是文件路径（.json）或直接是 JSON 字符串。"""
    path = Path(arg)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    # 尝试当 JSON 字符串
    try:
        return json.loads(arg)
    except json.JSONDecodeError:
        raise RuntimeError(f"参数不是有效文件路径也不是 JSON: {arg}")


def cmd_send(args):
    if len(args) < 2:
        print("用法: feishu_card.py send <receive_id> <card.json|json-string>")
        print("示例: feishu_card.py send ou_xxxxx templates/alert.json")
        sys.exit(1)
    receive_id = args[0]
    card = load_card_from_arg(args[1])
    msg_id = send_card(receive_id, card)
    print(f"✅ 发送成功")
    print(f"   receive_id: {receive_id}")
    print(f"   message_id: {msg_id}")


def cmd_update(args):
    if len(args) < 2:
        print("用法: feishu_card.py update <message_id> <card.json|json-string>")
        sys.exit(1)
    message_id = args[0]
    card = load_card_from_arg(args[1])
    update_card(message_id, card)
    print(f"✅ 更新成功")
    print(f"   message_id: {message_id}")


def cmd_token(args):
    """测试：拿一次 token 并打印（前 20 字符）。"""
    app_id, app_secret = load_credentials()
    token = get_tenant_token(app_id, app_secret)
    print(f"✅ Token 获取成功")
    print(f"   app_id: {app_id[:12]}...")
    print(f"   token: {token[:20]}...")
    print(f"   expires_at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(_TOKEN_CACHE['expires_at']))}")


def cmd_whoami(args):
    """用 token 调 open-apis/auth/v3/user_access_token/info... 不对，应该直接 /im/v1/chats 拿自己的 info。"""
    # 简单实现：调 /open-apis/auth/v3/tenant_access_token 看返回的 tenant_key
    app_id, app_secret = load_credentials()
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_save(args):
    """保存凭证到 credentials.json。"""
    if len(args) < 2:
        print("用法: feishu_card.py save <app_id> <app_secret>")
        sys.exit(1)
    save_credentials(args[0], args[1])
    print(f"✅ 凭证已保存到 {CREDS_PATH}（chmod 600）")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "send":
        cmd_send(rest)
    elif cmd == "update":
        cmd_update(rest)
    elif cmd == "reply":
        if len(rest) < 2:
            print("用法: feishu_card.py reply <message_id> <card.json>")
            sys.exit(1)
        new_id = reply_card(rest[0], load_card_from_arg(rest[1]))
        print(f"✅ 回复成功, new message_id: {new_id}")
    elif cmd == "token":
        cmd_token(rest)
    elif cmd == "whoami":
        cmd_whoami(rest)
    elif cmd == "save":
        cmd_save(rest)
    else:
        print(f"未知命令: {cmd}")
        print("可用: send | update | reply | token | whoami | save")
        sys.exit(1)


if __name__ == "__main__":
    main()
