"""mitmproxy addon：假 KG 应答（见 docs/kg-mock.md）。

- `/gksl/v1/lookup/...` 回一份「已注册、服务地址就绪」的报文
- `/service/umc/leafcert` 回 mitmproxy 自己的证书（让 pinning 客户端也能过）
- 其它请求：离线时直连失败则回 200 空体，避免客户端卡死
"""

from __future__ import annotations

import json
import logging
import os

from mitmproxy import http

log = logging.getLogger("kg_mock")

REQLOG = os.environ.get("KG_REQLOG", "/tmp/kgreq.log")


def _dump(kind: str, flow: "http.HTTPFlow") -> None:
    try:
        body = flow.request.get_text(strict=False) or ""
        with open(REQLOG, "a", encoding="utf-8") as f:
            f.write(f"{kind} {flow.request.method} {flow.request.pretty_host}{flow.request.path}\n")
            if body:
                f.write(f"  body: {body[:6000]}\n")
    except Exception:  # noqa: BLE001
        pass

LOOKUP_BODY = {
    "clientDownloadUrl": ["https://umc-cdn.secb2b.com:443"],
    "kslUrl": ["https://eu-segd-api.secb2b.com:443"],
    "serviceInfo": {
        "registered": True,
        "serviceIdentifier": "KG",
        "serviceUrl": ["https://gsl.samsunggsl.com:443"],
    },
}


MOCK = os.environ.get("KG_MOCK", "1") != "0"

CA_PATH = os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem")
CA_PEM = open(CA_PATH).read() if os.path.exists(CA_PATH) else ""
CA_ONELINE = ("-----BEGIN CERTIFICATE-----"
              + "".join(l for l in CA_PEM.splitlines() if "CERTIFICATE" not in l)
              + "-----END CERTIFICATE-----")
PINNED_HOSTS = ["gsl.samsunggsl.com:443", "pinning-02.secb2b.com:443"]


def request(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    path = flow.request.path
    log.info("%s %s%s", flow.request.method, host, path)
    # 反向模式的上游是固定的 gsl；把打往 eu-gslu（/af/…）的请求改指到 eu-gslu 上游
    if path.startswith("/af/"):
        flow.request.host = "eu-gslu.samsunggsl.com"
        flow.request.port = 443
        try:
            flow.server_conn.address = ("eu-gslu.samsunggsl.com", 443)
        except Exception:  # noqa: BLE001
            pass
    _dump("REQ", flow)

    if not MOCK:
        return

    if "getKGStatus" in path and os.environ.get("KG_STATUS_PASSTHROUGH") != "1":
        import base64 as _b
        dummy = _b.b64encode(b"FAKE").decode()
        body = json.load(open("/tmp/kgcerts/status.json"))
        body["action"] = os.environ.get("KG_ACTION", "ENROLLMENT")
        body["policyRequired"] = True
        flow.response = http.Response.make(200, json.dumps(body).encode(),
                                           {"Content-Type": "application/json"})
        return

    if "getPolicy" in path:
        import base64 as _b
        fake = _b.b64encode(b"FAKE").decode()
        body = {"kgPolicy": fake, "kgPolicySignature": fake, "essPolicy": fake,
                "sfPolicy": fake, "sfPolicySignature": fake,
                "customAppList": [], "customIconUrl": "", "customWallpaperUrl": ""}
        flow.response = http.Response.make(200, json.dumps(body).encode(),
                                           {"Content-Type": "application/json"})
        return

    if "/report" in path or path.endswith("/kgc20/KGC20.apk"):
        flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
        return

    if "/gksl/v1/lookup" in path:
        flow.response = http.Response.make(
            200,
            json.dumps(LOOKUP_BODY).encode(),
            {"Content-Type": "application/json"},
        )
        return

    # MPS 端点由 response 钩子改写（透传真实 URL 列表，只替换 CA）


def response(flow: http.HTTPFlow) -> None:
    """MPS 应答透传后改写：保留真实 URL 列表，把每个 CA 换成 mitmproxy 的 CA。"""
    if not MOCK or "/service/umc/leafcert" not in flow.request.path:
        return
    if flow.response is None or flow.response.status_code != 200:
        return
    try:
        data = json.loads(flow.response.get_text(strict=False))
    except Exception:  # noqa: BLE001
        return
    for entry in data.get("data", []):
        if "CA" in entry:
            entry["CA"] = [CA_ONELINE]
    flow.response.set_text(json.dumps(data))
    with open(REQLOG, "a", encoding="utf-8") as f:
        f.write(f"MPS rewritten, entries={len(data.get('data', []))}\n")


def error(flow: http.HTTPFlow) -> None:
    if flow.response is None and flow.error is not None:
        log.warning("upstream error %s: %s", flow.request.pretty_url, flow.error)
        flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
