import os
import sys
import unittest
import asyncio
import ipaddress
from starlette.requests import Request
from starlette.responses import Response

# Set environment variables for config loading
os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8,127.0.0.1/32,172.16.0.0/12"
os.environ["DEFAULT_LOCALE"] = "en"

# Ensure root folder is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from i18n_security import SmartClientContextMiddleware, ClientContext
from i18n_security.middleware import COUNTRY_TO_LOCALE

def make_request(
    client_ip: str = "127.0.0.1",
    headers: dict = None,
    cookies: dict = None
) -> Request:
    headers = headers or {}
    cookies = cookies or {}
    
    # Format headers as a list of bytes tuples
    raw_headers = []
    for k, v in headers.items():
        raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
        
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode("latin-1")))

    scope = {
        "type": "http",
        "client": (client_ip, 12345),
        "headers": raw_headers,
        "path": "/test",
        "method": "GET",
        "query_string": b"",
    }
    return Request(scope)

async def dummy_call_next(request: Request):
    return Response("OK")

class TestI18nSecurityMiddleware(unittest.TestCase):
    def setUp(self):
        # Instantiate the middleware with supported locales
        self.middleware = SmartClientContextMiddleware(
            app=None,
            supported_locales=["zh", "en", "fr", "es", "ar"]
        )

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_tc01_direct_ip_spoofing(self):
        """TC-01: Direct IP spoofing (No CDN) - XFF header from untrusted client is discarded, returning Peer IP."""
        req = make_request(
            client_ip="203.0.113.45",
            headers={"X-Forwarded-For": "8.8.8.8"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        
        self.assertEqual(ctx.client.ip, "203.0.113.45")
        self.assertFalse(ctx.client.is_proxy_detected)
        self.assertIsNone(ctx.client.proxy_type)

    def test_tc02_deep_spoofing(self):
        """TC-02: Deep Spoofing - Traverses past trusted proxies and truncates at the first untrusted IP from the right."""
        # 10.0.0.1 is in TRUSTED_PROXIES (10.0.0.0/8)
        # 203.0.113.45 is not trusted (Client IP)
        # 103.21.244.1 is in Cloudflare IP range (trusted proxy)
        # 1.1.1.1 is not trusted (Fake IP spoofed by client)
        req = make_request(
            client_ip="10.0.0.1",
            headers={"X-Forwarded-For": "1.1.1.1, 103.21.244.1, 203.0.113.45"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        
        self.assertEqual(ctx.client.ip, "203.0.113.45")
        self.assertTrue(ctx.client.is_proxy_detected)
        self.assertEqual(ctx.client.proxy_type, "Generic")

    def test_tc03_ipv6_spoofing(self):
        """TC-03: IPv6 Spoofing - Same logic applies to IPv6 addresses."""
        # 172.16.0.5 is trusted (172.16.0.0/12)
        # 2001:db8::1 is not trusted (Client IPv6)
        # 2400:cb00::1 is Cloudflare IP (trusted)
        req = make_request(
            client_ip="172.16.0.5",
            headers={"X-Forwarded-For": "::ffff:8.8.8.8, 2400:cb00::1, 2001:db8::1"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        
        self.assertEqual(ctx.client.ip, "2001:db8::1")
        self.assertTrue(ctx.client.is_proxy_detected)

    def test_tc04_redos_header_injection(self):
        """TC-04: ReDoS / Header Injection - Handles malicious strings safely, fallback to default."""
        req = make_request(
            client_ip="203.0.113.45",
            headers={"Accept-Language": "'; DROP TABLE users;-- , " + "a" * 5000}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        
        self.assertEqual(ctx.i18n.detected_locale, "en")
        self.assertEqual(ctx.i18n.decision_source, "SYSTEM_DEFAULT")
        self.assertEqual(ctx.i18n.confidence_score, 0.1)

    def test_tc05_invalid_cookie_locale(self):
        """TC-05: Invalid Cookie locale - SQL injection or invalid tags fallback safely."""
        # Case A: SQL injection attempt
        req = make_request(
            cookies={"locale": "'; DROP TABLE users;--"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        self.assertEqual(ctx.i18n.detected_locale, "en")
        self.assertEqual(ctx.i18n.decision_source, "SYSTEM_DEFAULT")

        # Case B: Invalid tag
        req2 = make_request(
            cookies={"locale": "xx-INVALID"}
        )
        self.run_async(self.middleware.dispatch(req2, dummy_call_next))
        ctx2: ClientContext = req2.state.client_context
        self.assertEqual(ctx2.i18n.detected_locale, "en")

        # Case C: Empty tag
        req3 = make_request(
            cookies={"locale": ""}
        )
        self.run_async(self.middleware.dispatch(req3, dummy_call_next))
        ctx3: ClientContext = req3.state.client_context
        self.assertEqual(ctx3.i18n.detected_locale, "en")

    def test_tc06_x_real_ip_spoofing(self):
        """TC-06: X-Real-IP spoofing - Middleware ignores X-Real-IP."""
        req = make_request(
            client_ip="203.0.113.45",
            headers={"X-Real-IP": "8.8.8.8"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        
        self.assertEqual(ctx.client.ip, "203.0.113.45")

    def test_tc07_blank_malformed_xff(self):
        """TC-07: Blank / Malformed XFF - Falls back to Peer IP, does not raise exception."""
        # Case A: Empty XFF
        req = make_request(
            client_ip="203.0.113.45",
            headers={"X-Forwarded-For": ""}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx: ClientContext = req.state.client_context
        self.assertEqual(ctx.client.ip, "203.0.113.45")

        # Case B: Malformed string XFF
        req2 = make_request(
            client_ip="203.0.113.45",
            headers={"X-Forwarded-For": "not-an-ip, also-not-an-ip"}
        )
        self.run_async(self.middleware.dispatch(req2, dummy_call_next))
        ctx2: ClientContext = req2.state.client_context
        self.assertEqual(ctx2.client.ip, "203.0.113.45")

    def test_locale_decision_tree_priorities(self):
        """Verify the locale priorities: Cookie > Accept-Language > CF-IPCountry > DB-IP > Default."""
        
        # 1. Cookie wins over Accept-Language
        req = make_request(
            headers={"Accept-Language": "fr;q=0.9"},
            cookies={"locale": "zh"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx = req.state.client_context
        self.assertEqual(ctx.i18n.detected_locale, "zh")
        self.assertEqual(ctx.i18n.decision_source, "EXPLICIT_COOKIE")
        self.assertEqual(ctx.i18n.confidence_score, 1.0)

        # 2. Accept-Language (Precise Match) wins over CF-IPCountry
        req2 = make_request(
            headers={"Accept-Language": "fr", "CF-IPCountry": "TW"}
        )
        self.run_async(self.middleware.dispatch(req2, dummy_call_next))
        ctx2 = req2.state.client_context
        self.assertEqual(ctx2.i18n.detected_locale, "fr")
        self.assertEqual(ctx2.i18n.decision_source, "ACCEPT_LANGUAGE_HEADER")
        self.assertEqual(ctx2.i18n.confidence_score, 0.85)

        # 3. Accept-Language (Fuzzy Match) wins over CF-IPCountry
        req3 = make_request(
            headers={"Accept-Language": "fr-CH", "CF-IPCountry": "TW"}
        )
        self.run_async(self.middleware.dispatch(req3, dummy_call_next))
        ctx3 = req3.state.client_context
        self.assertEqual(ctx3.i18n.detected_locale, "fr")
        self.assertEqual(ctx3.i18n.decision_source, "ACCEPT_LANGUAGE_HEADER")
        self.assertEqual(ctx3.i18n.confidence_score, 0.65)

        # 4. CF-IPCountry wins over DB-IP / Default
        # (CF-IPCountry is set to "ES" which maps to "es")
        req4 = make_request(
            headers={"CF-IPCountry": "ES"}
        )
        self.run_async(self.middleware.dispatch(req4, dummy_call_next))
        ctx4 = req4.state.client_context
        self.assertEqual(ctx4.i18n.detected_locale, "es")
        self.assertEqual(ctx4.i18n.decision_source, "CF_EDGE_GEOIP")
        self.assertEqual(ctx4.i18n.confidence_score, 0.7)

    def test_db_ip_lookup(self):
        """Verify DB-IP lookup works for Geo information and locale resolution."""
        # Use a Taiwan IP that is mapped in the Lite database.
        # Let's try 1.200.0.1 (Taiwan mobile IP) or 203.0.113.1.
        # Actually, let's use a standard Taiwan IP like 168.95.1.1 (Chunghwa Telecom).
        req = make_request(
            client_ip="168.95.1.1"
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx = req.state.client_context
        
        # The lookup should resolve TW
        self.assertEqual(ctx.geo.country_code, "TW")
        self.assertIn(ctx.geo.timezone, (None, "Asia/Taipei"))
        
        # Since no headers are set, it should fallback to LOCAL_DB_GEOIP and resolve "zh"
        self.assertEqual(ctx.i18n.detected_locale, "zh")
        self.assertEqual(ctx.i18n.decision_source, "LOCAL_DB_GEOIP")
        self.assertEqual(ctx.i18n.confidence_score, 0.7)

    def test_cloudflare_trusted_connecting_ip(self):
        """Verify that when Peer IP is in Cloudflare range, CF-Connecting-IP is trusted."""
        # 103.21.244.5 is a valid Cloudflare IP
        req = make_request(
            client_ip="103.21.244.5",
            headers={"CF-Connecting-IP": "198.51.100.22", "CF-IPCountry": "FR"}
        )
        self.run_async(self.middleware.dispatch(req, dummy_call_next))
        ctx = req.state.client_context
        
        self.assertEqual(ctx.client.ip, "198.51.100.22")
        self.assertTrue(ctx.client.is_proxy_detected)
        self.assertEqual(ctx.client.proxy_type, "Cloudflare")
        self.assertEqual(ctx.geo.country_code, "FR")

if __name__ == "__main__":
    unittest.main()
