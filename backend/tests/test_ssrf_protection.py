
import ipaddress
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from app.core.ssrf_protection import (
    DISALLOWED_IPV6_NETWORKS,
    DnsPool,
    is_ip_disallowed,
    validate_url_ssrf,
    safe_fetch_text,
    SSRFProtectionError,
)
from app.services.openapi_parser import OpenApiParser
def test_ip_disallowed_private_ipv4():
    private_ips = [
        "10.0.0.1",
        "10.255.255.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.1.100",
        "192.168.255.254",
    ]
    for ip in private_ips:
        disallowed, reason = is_ip_disallowed(ip)
        assert disallowed is True, f"應該封鎖私有 IP: {ip}"
        assert "私有" in reason or "禁止網段" in reason
def test_ip_disallowed_loopback_and_special():
    special_ips = [
        "127.0.0.1",
        "127.0.0.2",
        "127.255.255.255",
        "0.0.0.0",
        "169.254.169.254",
        "169.254.1.1",
        "100.64.0.1",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
    ]
    for ip in special_ips:
        disallowed, reason = is_ip_disallowed(ip)
        assert disallowed is True, f"應該封鎖特殊/迴路 IP: {ip}"
def test_ip_disallowed_ipv6():
    ipv6_blocked = [
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd12:3456:789a::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:10.0.0.1",
        "::ffff:192.168.1.1",
    ]
    for ip in ipv6_blocked:
        disallowed, reason = is_ip_disallowed(ip)
        assert disallowed is True, f"應該封鎖 IPv6 IP: {ip}"
def test_embedded_ipv4_ranges_are_listed_explicitly():
    for ip in ("2002:7f00:1::", "2002:a9fe:a9fe::1", "64:ff9b:1::a9fe:a9fe", "64:ff9b::a00:1"):
        address = ipaddress.ip_address(ip)
        assert any(address in net for net in DISALLOWED_IPV6_NETWORKS), ip
        assert is_ip_disallowed(ip)[0] is True, ip
def test_ip_allowed_public_ips():
    public_ips = [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",
        "140.82.112.4",
        "2606:4700:4700::1111",
    ]
    for ip in public_ips:
        disallowed, reason = is_ip_disallowed(ip)
        assert disallowed is False, f"合法的公開 IP 不應被封鎖: {ip}, reason={reason}"
@pytest.mark.anyio
async def test_validate_url_disallowed_schemes():
    invalid_urls = [
        "file:///etc/passwd",
        "ftp://ftp.example.com/files",
        "gopher://evil.com:70/1",
        "dict://dict.org/d:word",
        "ldap://localhost:389",
        "javascript:alert(1)",
    ]
    for u in invalid_urls:
        is_safe, reason, _ = await validate_url_ssrf(u, DnsPool.CONFIGURED_ENDPOINT)
        assert is_safe is False
        assert "協定" in reason or "格式" in reason
@pytest.mark.anyio
async def test_validate_url_disallowed_hostnames():
    blocked_hosts = [
        "http://localhost/openapi.json",
        "http://localhost:8080/spec.yaml",
        "https://localhost.localdomain/api",
        "http://test.localhost/docs",
        "http://api.local/spec",
        "http://db.internal/metrics",
        "http://server.lan/v1",
        "http://metadata.google.internal/computeMetadata/v1/",
    ]
    for u in blocked_hosts:
        is_safe, reason, _ = await validate_url_ssrf(u, DnsPool.CONFIGURED_ENDPOINT)
        assert is_safe is False
        assert "保留" in reason or "內部" in reason or "主機" in reason
@pytest.mark.anyio
async def test_validate_url_direct_private_ips():
    blocked_ip_urls = [
        "http://127.0.0.1:8000/api",
        "http://127.0.0.1/openapi.json",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1:8080/swagger.json",
        "http://192.168.1.1/admin",
        "http://172.16.1.1/openapi.json",
        "http://[::1]:8080/spec",
    ]
    for u in blocked_ip_urls:
        is_safe, reason, _ = await validate_url_ssrf(u, DnsPool.CONFIGURED_ENDPOINT)
        assert is_safe is False
        assert "IP" in reason or "禁止" in reason or "主機" in reason
@pytest.mark.anyio
async def test_validate_url_userinfo_blocked():
    u = "http://admin:secret@example.com/api"
    is_safe, reason, _ = await validate_url_ssrf(u, DnsPool.CONFIGURED_ENDPOINT)
    assert is_safe is False
    assert "Userinfo" in reason or "帳號密碼" in reason
@pytest.mark.anyio
async def test_validate_url_dangerous_ports():
    dangerous_port_urls = [
        "http://example.com:22/",
        "http://example.com:3306/",
        "http://example.com:6379/",
        "http://example.com:5432/",
        "http://example.com:27017/",
    ]
    for u in dangerous_port_urls:
        is_safe, reason, _ = await validate_url_ssrf(u, DnsPool.CONFIGURED_ENDPOINT)
        assert is_safe is False
        assert "連接埠" in reason or "連接" in reason
@pytest.mark.anyio
async def test_validate_url_valid_public_domain():
    mock_ips = [ipaddress.ip_address("93.184.216.34")]
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = mock_ips
        is_safe, reason, parsed = await validate_url_ssrf("https://example.com/openapi.json", DnsPool.CONFIGURED_ENDPOINT)
        assert is_safe is True
        assert reason == ""
        assert parsed is not None
        assert parsed.hostname == "example.com"
@pytest.mark.anyio
async def test_safe_fetch_text_blocks_ssrf():
    with pytest.raises(SSRFProtectionError):
        await safe_fetch_text("http://127.0.0.1:8000/secret.json", DnsPool.USER_URL)
    with pytest.raises(SSRFProtectionError):
        await safe_fetch_text("http://169.254.169.254/latest/meta-data/", DnsPool.USER_URL)
    with pytest.raises(SSRFProtectionError):
        await safe_fetch_text("file:///etc/passwd", DnsPool.USER_URL)
@pytest.mark.anyio
async def test_safe_fetch_text_blocks_redirect_to_private_ip():
    mock_public_ips = [ipaddress.ip_address("93.184.216.34")]
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = mock_public_ips
        mock_response_302 = MagicMock()
        mock_response_302.status_code = 302
        mock_response_302.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        mock_response_302.aclose = AsyncMock()
        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response_302
            with pytest.raises(SSRFProtectionError) as exc_info:
                await safe_fetch_text("https://example.com/redirect-to-metadata", DnsPool.USER_URL)
            assert "SSRF 防護" in str(exc_info.value)
            assert "169.254.169.254" in str(exc_info.value) or "禁止" in str(exc_info.value)
@pytest.mark.anyio
async def test_safe_fetch_text_size_limit():
    mock_public_ips = [ipaddress.ip_address("93.184.216.34")]
    with patch("app.core.ssrf_protection.resolve_hostname", new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = mock_public_ips
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Length": "20000000"}
        mock_response.aclose = AsyncMock()
        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_response
            with pytest.raises(ValueError) as exc_info:
                await safe_fetch_text("https://example.com/large_spec.json", DnsPool.USER_URL, max_size_bytes=10 * 1024 * 1024)
            assert "過大" in str(exc_info.value) or "超過限制" in str(exc_info.value)
@pytest.mark.anyio
async def test_openapi_parser_ssrf_protection():
    malicious_inputs = [
        "http://127.0.0.1:8000/openapi.json",
        "http://localhost:5000/swagger.yaml",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/spec.json",
        "http://192.168.1.1/api-docs",
    ]
    for url in malicious_inputs:
        with pytest.raises(ValueError) as exc_info:
            await OpenApiParser.parse(url, None, [])
        assert "安全防護" in str(exc_info.value) or "SSRF" in str(exc_info.value) or "失敗" in str(exc_info.value)
@pytest.mark.anyio
async def test_openapi_parser_valid_text_still_works():
    valid_spec = """
openapi: 3.0.0
info:
  title: Safe Test API
  version: 1.0.0
paths:
  /test:
    get:
      summary: Safe Endpoint
      responses:
        '200':
          description: OK
"""
    res = await OpenApiParser.parse(valid_spec, None, [])
    assert res["title"] == "Safe Test API"
    assert res["version"] == "openapi_3.0"
    assert len(res["endpoints"]) == 1