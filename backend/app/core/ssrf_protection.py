
import asyncio
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
import logging
import socket
from typing import Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import ParseResult, urljoin, urlparse
import httpx
import httpx2
logger = logging.getLogger(__name__)
DISALLOWED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
]
DISALLOWED_IPV6_NETWORKS = [
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001::/23"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]
ALLOWED_URL_SCHEMES = ("http", "https")
DISALLOWED_HOSTNAMES: Set[str] = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "ip6-localhost",
    "ip6-loopback",
    "local",
    "internal",
    "metadata.google.internal",
    "metadata.internal",
}
DISALLOWED_HOSTNAME_SUFFIXES: Tuple[str, ...] = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
    ".localdomain",
    ".corp",
)
BLOCKED_DANGEROUS_PORTS: Set[int] = {
    22,
    23,
    25,
    111,
    135,
    139,
    445,
    1433,
    1521,
    2375,
    2376,
    3306,
    5432,
    6379,
    11211,
    27017,
}
class DnsPool(Enum):
    USER_URL = "user-url"
    CONFIGURED_ENDPOINT = "configured-endpoint"
DNS_RESOLVE_TIMEOUT_SECONDS = 5.0
DNS_RESOLVER_MAX_WORKERS = {DnsPool.USER_URL: 8, DnsPool.CONFIGURED_ENDPOINT: 4}
_dns_executors = {
    pool: ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"ssrf-dns-{pool.value}")
    for pool, workers in DNS_RESOLVER_MAX_WORKERS.items()
}
class SSRFProtectionError(ValueError):
    pass
def is_ip_disallowed(ip: Union[str, ipaddress.IPv4Address, ipaddress.IPv6Address]) -> Tuple[bool, str]:
    try:
        if isinstance(ip, str):
            ip_obj = ipaddress.ip_address(ip.strip())
        else:
            ip_obj = ip
    except ValueError:
        return True, f"無效的 IP 位址格式: {ip}"
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ipv4_target = ip_obj.ipv4_mapped
        return is_ip_disallowed(ipv4_target)
    if ip_obj.is_private:
        return True, f"禁止存取私有網路 IP 位址: {ip_obj}"
    if ip_obj.is_loopback:
        return True, f"禁止存取本機迴路 (Loopback) IP 位址: {ip_obj}"
    if ip_obj.is_link_local:
        return True, f"禁止存取 Link-Local (含雲端 Metadata) IP 位址: {ip_obj}"
    if ip_obj.is_reserved:
        return True, f"禁止存取保留網段 IP 位址: {ip_obj}"
    if ip_obj.is_multicast:
        return True, f"禁止存取群播 (Multicast) IP 位址: {ip_obj}"
    if ip_obj.is_unspecified:
        return True, f"禁止存取未指定 (0.0.0.0 / ::) IP 位址: {ip_obj}"
    if isinstance(ip_obj, ipaddress.IPv4Address):
        for net in DISALLOWED_IPV4_NETWORKS:
            if ip_obj in net:
                return True, f"IP 位址 {ip_obj} 位於禁止網段 {net}"
    elif isinstance(ip_obj, ipaddress.IPv6Address):
        for net in DISALLOWED_IPV6_NETWORKS:
            if ip_obj in net:
                return True, f"IP 位址 {ip_obj} 位於禁止網段 {net}"
    return False, ""
def _resolve_hostname_sync(hostname: str, port: int) -> List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    resolved_ips: List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]] = []
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            try:
                resolved_ips.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue
    except socket.gaierror as e:
        logger.warning(f"DNS 解析主機失敗 ({hostname}): {e}")
    return resolved_ips
async def resolve_hostname(
    hostname: str, port: int, dns_pool: DnsPool
) -> List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_dns_executors[dns_pool], _resolve_hostname_sync, hostname, port),
            timeout=DNS_RESOLVE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(f"DNS 解析主機逾時 ({hostname})")
        return []
IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
async def validate_url_ssrf(url: str, dns_pool: DnsPool) -> Tuple[bool, str, Optional[ParseResult]]:
    is_valid, reason, parsed, _ = await _check_url(url, dns_pool)
    return is_valid, reason, parsed
async def _check_url(url: str, dns_pool: DnsPool) -> Tuple[bool, str, Optional[ParseResult], List[IPAddress]]:
    if not url or not isinstance(url, str):
        return False, "URL 不能為空值", None, []
    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
    except Exception as e:
        return False, f"URL 解析失敗: {str(e)}", None, []
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        return False, f"不允許的 URL 協定 '{scheme}'，僅支援: {', '.join(ALLOWED_URL_SCHEMES)}", None, []
    hostname = parsed.hostname
    if not hostname:
        return False, "URL 中缺少有效的主機名稱 (Host)", None, []
    hostname_lower = hostname.lower().strip("[]")
    if parsed.username or parsed.password:
        return False, "URL 禁止包含帳號密碼資訊 (Userinfo)", None, []
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80
    else:
        if port <= 0 or port > 65535:
            return False, f"無效的連接埠號碼: {port}", None, []
        if port in BLOCKED_DANGEROUS_PORTS:
            return False, f"禁止存取受保護的內部服務連接埠: {port}", None, []
    approved_ips: List[IPAddress] = []
    if hostname_lower in DISALLOWED_HOSTNAMES:
        return False, f"禁止存取保留/內部主機名稱: {hostname_lower}", None, []
    for suffix in DISALLOWED_HOSTNAME_SUFFIXES:
        if hostname_lower.endswith(suffix):
            return False, f"禁止存取內部專屬網域: {hostname_lower}", None, []
    try:
        direct_ip = ipaddress.ip_address(hostname_lower)
    except ValueError:
        direct_ip = None
    if direct_ip is not None:
        is_disallowed, reason = is_ip_disallowed(direct_ip)
        if is_disallowed:
            return False, f"目標 IP 位址不被允許: {reason}", None, []
        return True, "", parsed, approved_ips
    resolved_ips = await resolve_hostname(hostname_lower, port, dns_pool)
    if not resolved_ips:
        return False, f"無法解析主機名稱之 IP 位址: {hostname}", None, []
    for ip_addr in resolved_ips:
        is_disallowed, reason = is_ip_disallowed(ip_addr)
        if is_disallowed:
            logger.warning(f"SSRF 防護阻止存取 {url}: 解析出禁止 IP {ip_addr} ({reason})")
            return False, f"主機解析至受保護或私有 IP 位址 ({ip_addr}): {reason}", None, []
    approved_ips = resolved_ips
    return True, "", parsed, approved_ips
async def _pin_to_approved_ip(request, request_class, dns_pool: DnsPool):
    is_safe, error_msg, _, approved_ips = await _check_url(str(request.url), dns_pool)
    if not is_safe:
        raise SSRFProtectionError(f"SSRF 防護拒絕連線: {error_msg}")
    if not approved_ips:
        return request
    return request_class(
        method=request.method,
        url=request.url.copy_with(host=str(approved_ips[0])),
        headers=request.headers,
        stream=request.stream,
        extensions={**request.extensions, "sni_hostname": request.url.host},
    )
class SSRFSafeTransport(httpx.AsyncBaseTransport):
    def __init__(self, dns_pool: DnsPool) -> None:
        self._dns_pool = dns_pool
        self._transport = httpx.AsyncHTTPTransport()
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        pinned = await _pin_to_approved_ip(request, httpx.Request, self._dns_pool)
        return await self._transport.handle_async_request(pinned)
    async def aclose(self) -> None:
        await self._transport.aclose()
class SSRFSafeHttpx2Transport(httpx2.AsyncBaseTransport):
    def __init__(self, dns_pool: DnsPool) -> None:
        self._dns_pool = dns_pool
        self._transport = httpx2.AsyncHTTPTransport()
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        pinned = await _pin_to_approved_ip(request, httpx2.Request, self._dns_pool)
        return await self._transport.handle_async_request(pinned)
    async def aclose(self) -> None:
        await self._transport.aclose()
def same_origin(a: httpx.URL, b: httpx.URL) -> bool:
    return (a.scheme, a.host, a.port) == (b.scheme, b.host, b.port)
async def send_following_redirects(
    client: httpx.AsyncClient,
    request: httpx.Request,
    max_redirects: int,
    allow_cross_origin: bool,
) -> httpx.Response:
    for _ in range(max_redirects + 1):
        response = await client.send(request, stream=True, follow_redirects=False)
        next_request = response.next_request
        if next_request is None:
            return response
        await response.aclose()
        if not allow_cross_origin and not same_origin(next_request.url, request.url):
            raise ValueError("轉址到其他來源，已拒絕")
        request = next_request
    raise ValueError(f"轉址次數超過上限 ({max_redirects})")
async def safe_fetch_text(
    url: str,
    dns_pool: DnsPool,
    timeout: float = 15.0,
    max_redirects: int = 5,
    max_size_bytes: int = 10 * 1024 * 1024,
    headers: Optional[Dict[str, str]] = None,
    is_url_allowed: Optional[Callable[[str], bool]] = None
) -> str:
    current_url = url.strip()
    redirect_count = 0
    visited_urls: Set[str] = set()
    req_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AskMiaoBot/1.0; +https://github.com/Scorpio-meow/AskMiao)",
        "Accept": "application/json, application/yaml, application/x-yaml, text/yaml, text/plain, */*",
    }
    if headers:
        req_headers.update(headers)
    while True:
        is_safe, error_msg, _ = await validate_url_ssrf(current_url, dns_pool)
        if not is_safe:
            raise SSRFProtectionError(f"SSRF 防護拒絕連線: {error_msg}")
        visited_urls.add(current_url)
        client_kwargs = {
            "timeout": timeout,
            "follow_redirects": False,
            "transport": SSRFSafeTransport(dns_pool),
        }
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                req = client.build_request("GET", current_url, headers=req_headers)
                resp = await client.send(req, stream=True)
                try:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise ValueError(f"轉址次數超過上限 ({max_redirects})")
                        location = resp.headers.get("Location")
                        if not location:
                            raise ValueError(f"轉址回應缺少 Location 標頭 (狀態碼 {resp.status_code})")
                        next_url = urljoin(current_url, location.strip())
                        if next_url in visited_urls:
                            raise ValueError(f"偵測到轉址迴圈: {next_url}")
                        if is_url_allowed is not None and not is_url_allowed(next_url):
                            raise ValueError(f"轉址目標不在允許的網域內: {next_url}")
                        logger.info(f"安全轉址 ({redirect_count}/{max_redirects}): {current_url} -> {next_url}")
                        current_url = next_url
                        continue
                    if resp.status_code != 200:
                        raise ValueError(f"遠端伺服器回傳非成功狀態碼: {resp.status_code}")
                    content_length = resp.headers.get("Content-Length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > max_size_bytes:
                            raise ValueError(
                                f"回應檔案過大: {int(content_length)} 位元組 (上限 {max_size_bytes} 位元組)"
                            )
                    chunks = []
                    total_bytes = 0
                    async for chunk in resp.aiter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > max_size_bytes:
                            raise ValueError(
                                f"回應內容大小超過限制 ({max_size_bytes} 位元組)"
                            )
                        chunks.append(chunk)
                    raw_bytes = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
                    try:
                        return raw_bytes.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        return raw_bytes.decode("utf-8", errors="replace")
                finally:
                    await resp.aclose()
        except (SSRFProtectionError, ValueError):
            raise
        except Exception as e:
            raise ValueError(f"無法存取遠端 URL: {str(e)}")