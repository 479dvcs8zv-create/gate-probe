"""
test_fault_injection.py (v4.6)
===============================
WebArchiveVerifier 的協定層級與故障注入測試。

做法：在本機啟動一個模擬 Wayback 的 HTTP 伺服器，並把它設成驗證器的 HTTP 代理。
驗證器照常對 http://web.archive.org/... 發出真正的 HTTP 請求（經過 socket、urllib、
逾時與轉址處理），由模擬伺服器依情境回應：正常、403、逾時、內容被竄改、轉址、
封存晚於公告、空結果、格式錯誤、超大回應、原始網址不符、缺封存摘要、5xx。

這驗證的是「驗證器程式碼對各種回應的處理」，不是真實 Wayback 的行為。
真實服務的網址正規化、壓縮內容摘要、轉址規則，必須在可連網的環境做端對端驗收。

執行：python3 test_fault_injection.py（也可用 pytest 收集）
"""

import base64
import hashlib
import http.server
import json
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from schema import TickerInputBundle
from gates import eval_gate5b_pre_earnings
from reject_codes import RC
from independent_verifier import WebArchiveVerifier, ArchiveFetchError, ArchiveIntegrityError
from test_adversarial import FakeIndependentVerifier, dp, full_coverage, make_announcement
from schema import PreEarningsConsensusSnapshot

SOURCE = "https://mops.twse.com.tw/consensus/T46/2026Q1"
TICKER, QUARTER = "T46", "2026Q1"
OFFICIAL = "2026-01-20T13:00:00+08:00"                      # = 2026-01-20T05:00:00Z
CUTOFF = datetime(2026, 1, 20, 5, 0, tzinfo=timezone.utc)
EARLY_TS, LATE_TS = "20260105000000", "20260125000000"
CDX_FIELDS = ["timestamp", "original", "statuscode", "digest", "mimetype"]


def body_for(eps):
    return json.dumps({"records": [{"ticker": TICKER, "fiscal_quarter": QUARTER, "consensus_eps": eps}]}).encode()


def cdx_digest(b: bytes) -> str:
    return base64.b32encode(hashlib.sha1(b).digest()).decode("ascii")


class WaybackStub:
    """模擬 Wayback 的本機 HTTP 伺服器（以 HTTP 代理方式接收對 web.archive.org 的請求）。"""

    def __init__(self):
        self.scenario, self.requests, self.cdx_pages_served = {}, [], 0
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body=b"", headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                stub.requests.append(self.path)
                sc = stub.scenario
                u = urllib.parse.urlsplit(self.path)
                if u.path == "/cdx/search/cdx":
                    q = dict(urllib.parse.parse_qsl(u.query))
                    time.sleep(sc.get("cdx_delay", 0))
                    if sc.get("cdx_status", 200) != 200:
                        return self._send(sc["cdx_status"], b"denied")
                    if "cdx_raw" in sc:
                        return self._send(200, sc["cdx_raw"])
                    caps = sc.get("captures", [])
                    if not sc.get("ignore_to"):
                        caps = [c for c in caps if ("to" not in q or c["timestamp"] <= q["to"])
                                and ("from" not in q or c["timestamp"] >= q["from"])]
                    limit = int(q.get("limit") or 0)
                    start = int(q.get("resumeKey") or 0)
                    page = caps[start:start + limit] if limit > 0 else caps[start:]
                    rows = [CDX_FIELDS] + [[c["timestamp"], c.get("original", SOURCE), c.get("statuscode", "200"),
                                            c["digest"], "application/json"] for c in page]
                    more = limit > 0 and start + limit < len(caps)
                    if more and q.get("showResumeKey") == "true" and not sc.get("never_resume"):
                        rows += [[], [str(start + limit)]]
                    stub.cdx_pages_served += 1
                    return self._send(200, json.dumps(rows).encode())
                m = re.fullmatch(r"/web/(\d{14})id_/(.+)", u.path)
                if m:
                    time.sleep(sc.get("raw_delay", 0))
                    if sc.get("raw_redirect"):
                        return self._send(302, b"", {"Location": sc["raw_redirect"]})
                    if sc.get("raw_status", 200) != 200:
                        return self._send(sc["raw_status"], b"error")
                    return self._send(200, sc["bodies"][m.group(1)])
                return self._send(404, b"not found")

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.handle_error = lambda *a: None
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def good_scenario(**overrides):
    early, late = body_for(10.0), body_for(10.0)
    sc = {"captures": [{"timestamp": EARLY_TS, "digest": cdx_digest(early)},
                       {"timestamp": LATE_TS, "digest": cdx_digest(late)}],
          "bodies": {EARLY_TS: early, LATE_TS: late}}
    sc.update(overrides)
    return sc


def make_verifier(stub, **kw):
    return WebArchiveVerifier(base_url="http://web.archive.org",
                              opener=WebArchiveVerifier.build_opener(proxy_url=stub.url),
                              timeout=kw.pop("timeout", 2.0), **kw)


def run_gate(wayback):
    """官方公告用測試替身（完整宣告查詢範圍），封存證據走真正的 WebArchiveVerifier。"""
    ann = FakeIndependentVerifier()
    ann.announcements[(TICKER, QUARTER)] = full_coverage([make_announcement(TICKER, QUARTER, OFFICIAL)])
    snap = PreEarningsConsensusSnapshot(
        ticker=TICKER, fiscal_quarter=QUARTER,
        snapshot_date=dp(None, url=SOURCE), earnings_announcement_date=None,
        snapshot_taken_before_earnings=True, consensus_eps=dp(10.0), consensus_revenue=dp(None))
    bundle = TickerInputBundle(ticker=TICKER)
    bundle.pre_earnings_snapshots = [snap]
    return eval_gate5b_pre_earnings(bundle, verifier=wayback, announcement_verifier=ann)


def _with_stub(scenario, fn, **verifier_kw):
    stub = WaybackStub()
    try:
        stub.scenario = scenario
        return fn(stub, make_verifier(stub, **verifier_kw))
    finally:
        stub.close()


def _expect_gate(name, scenario, code=None, verified=False, **verifier_kw):
    def go(stub, w):
        r = run_gate(w)
        if verified:
            assert r.evidence_count == 1, f"FAIL {name}: 應通過 {r.reject_codes} {r.reasons}"
        else:
            assert r.evidence_count == 0, f"FAIL {name}: 應擋下 {r.reject_codes}"
            assert code in r.reject_codes, f"FAIL {name}: 缺少 {code}，實際 {r.reject_codes}"
        detail = "驗證通過" if verified else sorted(set(r.reject_codes) - {RC.MIN_COUNT_NOT_MET, RC.SOURCE_UNVERIFIABLE})
        print(f"✓ 故障注入 {name} → {detail}")
        return r
    return _with_stub(scenario, go, **verifier_kw)


# --------------------------------------------------------------------------- 測試

def test_success_picks_capture_before_official_cutoff():
    def go(stub, w):
        b = w.fetch_verified_bundle(SOURCE, captured_before=CUTOFF)
        assert b.snapshot_id == EARLY_TS and b.captured_at == "2026-01-05T00:00:00+00:00"
        assert b.sha256 == hashlib.sha256(body_for(10.0)).hexdigest()
        assert b.archive_url == f"http://web.archive.org/web/{EARLY_TS}/{SOURCE}"
        cdx_q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(w.requests[0]).query))
        assert cdx_q["to"] == "20260120045959" and cdx_q["from"] == "20250724050000"
        assert cdx_q["filter"] == "statuscode:200" and cdx_q["limit"] == "100" and cdx_q["showResumeKey"] == "true"
        assert w.requests[1].endswith(f"/web/{EARLY_TS}id_/{SOURCE}")
        assert b.archive_digest_matched is True and b.archive_digest_algorithm == "sha1-base32"
        print("✓ 故障注入 正常：CDX 時間窗 = 官方截止點前 180 天～前一秒、正數分頁＋續查鍵，取 1/5 版本、摘要相符")
    _with_stub(good_scenario(), go)
    _expect_gate("正常情境走完整個 Gate5B", good_scenario(), verified=True)


def test_http_403():
    _expect_gate("CDX 回應 403", good_scenario(cdx_status=403), RC.EVIDENCE_VERIFIER_ERROR)


def test_timeout():
    t0 = time.time()
    _expect_gate("取原文逾時", good_scenario(raw_delay=1.5), RC.EVIDENCE_VERIFIER_ERROR, timeout=0.5)
    assert time.time() - t0 < 1.4, "逾時沒有及時中止"


def test_tampered_content():
    sc = good_scenario()
    sc["bodies"][EARLY_TS] = body_for(99.9)  # 回傳內容與封存當下摘要不符
    _expect_gate("內容遭竄改（與封存當下摘要不符）", sc, RC.EVIDENCE_HASH_MISMATCH)


def test_redirect_to_other_capture():
    sc = good_scenario(raw_redirect=f"http://web.archive.org/web/{LATE_TS}id_/{SOURCE}")
    _expect_gate("被轉址到其他版本", sc, RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)


def test_service_ignores_cutoff_filter():
    # 服務端忽略 to 參數，回傳公告後的版本：驗證器自己過濾，仍選公告前的版本
    _expect_gate("服務端忽略截止點過濾", good_scenario(ignore_to=True), verified=True)
    late_only = good_scenario(ignore_to=True)
    late_only["captures"] = [late_only["captures"][1]]
    _expect_gate("只有公告後的版本", late_only, RC.EVIDENCE_BUNDLE_UNAVAILABLE)


def test_no_capture():
    _expect_gate("查無任何封存版本", good_scenario(captures=[]), RC.EVIDENCE_BUNDLE_UNAVAILABLE)


def test_malformed_cdx():
    _expect_gate("CDX 回應不是 JSON", good_scenario(cdx_raw=b"<html>oops</html>"), RC.EVIDENCE_VERIFIER_ERROR)
    _expect_gate("CDX 欄位不符", good_scenario(cdx_raw=json.dumps([["foo", "bar"], ["1", "2"]]).encode()),
                 RC.EVIDENCE_VERIFIER_ERROR)


def test_oversized_response():
    _expect_gate("回應超過大小上限", good_scenario(), RC.EVIDENCE_VERIFIER_ERROR, max_bytes=16)


def test_original_url_mismatch():
    sc = good_scenario()
    sc["captures"][0]["original"] = SOURCE.replace("https://", "http://")
    _expect_gate("CDX 原始網址與請求不同", sc, RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)


def test_missing_capture_digest():
    sc = good_scenario()
    sc["captures"][0]["digest"] = "-"
    _expect_gate("CDX 沒有封存當下摘要", sc, RC.EVIDENCE_IMMUTABILITY_UNPROVEN)


def test_server_error():
    _expect_gate("取原文回應 503", good_scenario(raw_status=503), RC.EVIDENCE_VERIFIER_ERROR)


def test_exception_types():
    """驗證器層級：可用性問題與完整性問題拋出不同例外，報告才能區分「連不上」與「被竄改」。"""
    def go(stub, w):
        try:
            w.fetch_verified_bundle(SOURCE, captured_before=CUTOFF)
        except ArchiveIntegrityError as e:
            assert e.reject_code == RC.EVIDENCE_HASH_MISMATCH
        else:
            raise AssertionError("FAIL: 竄改內容沒有拋出 ArchiveIntegrityError")
    sc = good_scenario()
    sc["bodies"][EARLY_TS] = b"tampered"
    _with_stub(sc, go)

    def go403(stub, w):
        try:
            w.fetch_verified_bundle(SOURCE, captured_before=CUTOFF)
        except ArchiveFetchError as e:
            assert e.reject_code is None and "403" in str(e)
        else:
            raise AssertionError("FAIL: 403 沒有拋出 ArchiveFetchError")
    _with_stub(good_scenario(cdx_status=403), go403)
    print("✓ 故障注入 例外分類：竄改 → ArchiveIntegrityError(HASH_MISMATCH)；403 → ArchiveFetchError")


def many_captures(n):
    """n 個都在官方截止點之前的封存版本（2026-01-01 起每天一個），內容相同。"""
    body = body_for(10.0)
    ts = [f"202601{d:02d}000000" for d in range(1, n + 1)]
    return {"captures": [{"timestamp": t, "digest": cdx_digest(body)} for t in ts],
            "bodies": {t: body for t in ts}}, ts


def test_cdx_pagination_collects_all_pages():
    sc, ts = many_captures(5)

    def go(stub, w):
        b = w.fetch_verified_bundle(SOURCE, captured_before=CUTOFF)
        assert b.snapshot_id == ts[-1], f"FAIL: 應取最後一頁上最接近截止點的版本，實際 {b.snapshot_id}"
        assert b.retrieval_trace["pages"] == 3 and b.retrieval_trace["records"] == 5, b.retrieval_trace
        print(f"✓ 故障注入 CDX 分頁：5 筆、每頁 2 筆 → 依續查鍵取完 3 頁，選到最後一頁的 {ts[-1]}")
    _with_stub(sc, go, cdx_page_size=2)


def test_cdx_full_page_without_resume_key():
    sc, _ = many_captures(5)
    sc["never_resume"] = True
    _expect_gate("CDX 滿頁卻沒有續查鍵（可能被截斷）", sc, RC.EVIDENCE_VERIFIER_ERROR, cdx_page_size=2)


def test_cdx_too_many_pages():
    sc, _ = many_captures(5)
    _expect_gate("CDX 頁數超過上限", sc, RC.EVIDENCE_VERIFIER_ERROR, cdx_page_size=1, max_cdx_pages=2)


def test_integrity_semantics_in_trail():
    def go(stub, w):
        r = run_gate(w)
        integ = r.evidence_trail[0]["integrity"]
        assert integ["archive_capture_digest"]["matched_served_bytes"] is True
        assert integ["independent_history_proof"] is False
        assert r.evidence_trail[0]["retrieval"]["pages"] >= 1
        print("✓ 故障注入 驗證紀錄分開標示：封存索引摘要相符＝是；獨立歷史證明＝否")
    _with_stub(good_scenario(), go)


def test_network_probe_against_stub():
    """ops/network_probe.py 的成功路徑：可連時記錄 200、保存原始回應且雜湊正確、Wayback 端對端取得成功。"""
    import contextlib
    import importlib.util
    import io
    import os
    import tempfile
    spec = importlib.util.spec_from_file_location(
        "network_probe", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "network_probe.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    stub = WaybackStub()
    try:
        stub.scenario = good_scenario()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            cdx_url = f"http://web.archive.org/cdx/search/cdx?url={SOURCE}&output=json"
            probe.main(["--url", cdx_url, "--proxy", stub.url, "--wayback-check", SOURCE, "--cutoff", OFFICIAL,
                        "--wayback-base", "http://web.archive.org", "--out-dir", d, "--timeout", "2"])
            report = json.load(open(os.path.join(d, "probe_report.json"), encoding="utf-8"))
            t = report["targets"][0]
            saved = open(os.path.join(d, t["saved_as"]), "rb").read()
        assert t["reachable"] and t["status"] == 200, t
        assert hashlib.sha256(saved).hexdigest() == t["body_sha256"]
        wc = report["wayback_check"]
        assert wc["result"] == "BUNDLE_OK" and wc["snapshot_id"] == EARLY_TS and wc["archive_digest_matched"], wc
        print("✓ 故障注入 探測工具：可連時記錄 200、原始回應存檔且雜湊正確、Wayback 端對端取得 BUNDLE_OK")
    finally:
        stub.close()


def test_probe_tls_and_charset_evidence():
    """探測工具 v4.8：本機自簽 HTTPS 伺服器（只用於測試工具本身）。
    驗證逐跳轉址紀錄、TLS 證據（版本、SAN、憑證指紋與實際憑證一致）、Big5 編碼證據，
    以及不信任該憑證時如實記錄驗證失敗。"""
    import contextlib
    import importlib.util
    import io
    import os
    import ssl
    import subprocess
    import tempfile
    spec = importlib.util.spec_from_file_location(
        "network_probe", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "network_probe.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    big5_body = ('<html><head><meta charset="big5"></head><body>測試公司 2026Q1 自結損益公告</body></html>'
                 ).encode("big5")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/big5")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=big5")
            self.send_header("Content-Length", str(len(big5_body)))
            self.end_headers()
            self.wfile.write(big5_body)

    with tempfile.TemporaryDirectory() as d:
        cert, key = os.path.join(d, "cert.pem"), os.path.join(d, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                        "-days", "2", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, capture_output=True)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sctx.load_cert_chain(cert, key)
        srv.socket = sctx.wrap_socket(srv.socket, server_side=True)
        srv.handle_error = lambda *a: None
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        port = srv.server_address[1]
        try:
            out1, out2 = os.path.join(d, "o1"), os.path.join(d, "o2")
            with contextlib.redirect_stdout(io.StringIO()):
                probe.main(["--url", f"https://localhost:{port}/redirect", "--cafile", cert, "--out-dir", out1,
                            "--timeout", "3"])
                probe.main(["--url", f"https://localhost:{port}/redirect", "--out-dir", out2, "--timeout", "3"])
            r1 = json.load(open(os.path.join(out1, "probe_report.json"), encoding="utf-8"))["targets"][0]
            r2 = json.load(open(os.path.join(out2, "probe_report.json"), encoding="utf-8"))["targets"][0]
            expected_fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(open(cert).read())).hexdigest()
        finally:
            srv.shutdown()
            srv.server_close()

    hops = r1["hops"]
    assert [h["status"] for h in hops] == [302, 200], hops
    assert hops[0]["response_headers"]["Location"] == "/big5"
    tls = hops[1]["tls"]
    assert tls["tls_version"].startswith("TLS") and "localhost" in tls["cert_san"]
    assert tls["cert_sha256"] == expected_fp, "憑證指紋必須與實際憑證一致"
    assert hops[1]["peer_address"] == "127.0.0.1" and hops[1]["via_proxy"] is False
    cs = r1["charset"]
    assert cs["declared_in_header"] == "big5" and cs["declared_in_meta"] == "big5"
    assert cs["strict_decode"]["utf-8"] != True and cs["strict_decode"]["big5"] is True, cs
    assert r2["reachable"] is False and "憑證驗證失敗" in r2["error"], r2
    print(f"✓ 探測工具 TLS／編碼證據：2 跳轉址、{tls['tls_version']}、SAN 與指紋正確；"
          f"Big5 回應以 UTF-8 解碼失敗、Big5 成功；未信任憑證時如實記錄驗證失敗")


TESTS = [
    test_success_picks_capture_before_official_cutoff, test_http_403, test_timeout, test_tampered_content,
    test_redirect_to_other_capture, test_service_ignores_cutoff_filter, test_no_capture, test_malformed_cdx,
    test_oversized_response, test_original_url_mismatch, test_missing_capture_digest, test_server_error,
    test_exception_types, test_cdx_pagination_collects_all_pages, test_cdx_full_page_without_resume_key,
    test_cdx_too_many_pages, test_integrity_semantics_in_trail, test_network_probe_against_stub,
    test_probe_tls_and_charset_evidence,
]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: 執行例外 {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'全部通過' if failed == 0 else f'{failed} 項仍有問題'} （共{len(TESTS)}項）")
