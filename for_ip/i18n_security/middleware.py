import os
import re
import ipaddress
import maxminddb
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .schemas import ClientContext, ClientInfo, I18nInfo, GeoInfo

# Country to locale mapping for supported languages: en, zh, fr, es, ar
COUNTRY_TO_LOCALE = {
    # Chinese (zh)
    "CN": "zh", "TW": "zh", "HK": "zh", "MO": "zh", "SG": "zh",
    # French (fr)
    "FR": "fr", "MC": "fr", "LU": "fr", "BE": "fr", "CH": "fr",
    "GP": "fr", "MQ": "fr", "GF": "fr", "RE": "fr", "YT": "fr",
    "PF": "fr", "NC": "fr", "WF": "fr", "PM": "fr", "BL": "fr",
    "MF": "fr", "SN": "fr", "CD": "fr", "CG": "fr", "CI": "fr",
    "BF": "fr", "NE": "fr", "ML": "fr", "GN": "fr", "TG": "fr",
    "BJ": "fr", "GA": "fr", "GQ": "fr", "DJ": "fr", "KM": "fr",
    "BI": "fr", "RW": "fr", "MG": "fr", "SC": "fr", "VU": "fr",
    # Spanish (es)
    "ES": "es", "MX": "es", "GT": "es", "SV": "es", "HN": "es",
    "NI": "es", "CR": "es", "PA": "es", "CU": "es", "DO": "es",
    "PR": "es", "CO": "es", "VE": "es", "EC": "es", "PE": "es",
    "BO": "es", "PY": "es", "CL": "es", "UY": "es", "AR": "es",
    # Arabic (ar)
    "SA": "ar", "AE": "ar", "QA": "ar", "OM": "ar", "KW": "ar",
    "BH": "ar", "EG": "ar", "DZ": "ar", "MA": "ar", "TN": "ar",
    "LY": "ar", "SD": "ar", "YE": "ar", "IQ": "ar", "SY": "ar",
    "JO": "ar", "LB": "ar", "PS": "ar", "MR": "ar", "SO": "ar",
    # English (en)
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "NZ": "en", "IE": "en", "ZA": "en",
}

# Country to primary timezone mapping (fallback for free DB-IP database)
COUNTRY_TO_TIMEZONE = {
    "TW": "Asia/Taipei",
    "CN": "Asia/Shanghai",
    "HK": "Asia/Hong_Kong",
    "MO": "Asia/Macau",
    "SG": "Asia/Singapore",
    "JP": "Asia/Tokyo",
    "KR": "Asia/Seoul",
    "FR": "Europe/Paris",
    "ES": "Europe/Madrid",
    "EG": "Africa/Cairo",
    "US": "America/New_York",
    "GB": "Europe/London",
    "CA": "America/Toronto",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "SA": "Asia/Riyadh",
    "AE": "Asia/Dubai",
    "QA": "Asia/Qatar",
    "OM": "Asia/Muscat",
    "KW": "Asia/Kuwait",
    "BH": "Asia/Bahrain",
    "DZ": "Africa/Algiers",
    "MA": "Africa/Casablanca",
    "TN": "Africa/Tunis",
    "LY": "Africa/Tripoli",
    "SD": "Africa/Khartoum",
    "YE": "Asia/Aden",
    "IQ": "Asia/Baghdad",
    "SY": "Asia/Damascus",
    "JO": "Asia/Amman",
    "LB": "Asia/Beirut",
    "PS": "Asia/Gaza",
}

BCP47_PATTERN = re.compile(r"^[a-z]{2,8}(-[a-z0-9]{2,8})*$")

def load_env_file():
    """Simple parser to load .env file from common directories into os.environ."""
    possible_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass

def is_ip_in_networks(ip_str: str, networks: list) -> bool:
    """Helper to check if an IP address is within a list of IP networks."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for net in networks:
            if ip.version == net.version:
                if ip in net:
                    return True
    except ValueError:
        pass
    return False

class SmartClientContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, supported_locales: list[str]):
        super().__init__(app)
        
        # Load local .env if present
        load_env_file()
        
        # 1. Validate supported_locales
        if not isinstance(supported_locales, list):
            raise ValueError(f"supported_locales must be a list of strings, got {type(supported_locales)}")
            
        for locale in supported_locales:
            if not isinstance(locale, str):
                raise ValueError(f"supported_locales elements must be strings, got {type(locale)}")
            if locale != locale.lower():
                raise ValueError(f"supported_locales elements must be lowercase, got '{locale}'")
            if not BCP47_PATTERN.match(locale):
                raise ValueError(f"supported_locales elements must be valid lowercase BCP 47 tags, got '{locale}'")
                
        self.supported_locales = supported_locales

        # 2. Load DEFAULT_LOCALE
        self.default_locale = os.getenv("DEFAULT_LOCALE", "en")
        if self.default_locale not in self.supported_locales:
            raise ValueError(f"DEFAULT_LOCALE '{self.default_locale}' is not in supported_locales {self.supported_locales}")

        # 3. Load TRUSTED_PROXIES
        self.trusted_proxies = []
        trusted_proxies_str = os.getenv("TRUSTED_PROXIES", "")
        if trusted_proxies_str:
            for item in trusted_proxies_str.split(","):
                item = item.strip()
                if item:
                    try:
                        self.trusted_proxies.append(ipaddress.ip_network(item))
                    except ValueError as e:
                        raise ValueError(f"Invalid CIDR in TRUSTED_PROXIES: '{item}'. Error: {e}")

        # 4. Load Cloudflare IP ranges from assets file
        self.cloudflare_ips = []
        cf_ips_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cloudflare_ips.txt")
        if os.path.exists(cf_ips_path):
            try:
                with open(cf_ips_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            try:
                                self.cloudflare_ips.append(ipaddress.ip_network(line))
                            except ValueError:
                                pass
            except Exception as e:
                print(f"Warning: Failed to load Cloudflare IPs from {cf_ips_path}: {e}")

        # 5. Open DB-IP database Reader
        self.db_reader = None
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dbip-city-lite.mmdb")
        if os.path.exists(db_path):
            try:
                # We use MODE_MEMORY to keep the database fully in RAM.
                # This prevents locking the physical file on Windows, allowing monthly background updates.
                self.db_reader = maxminddb.open_database(db_path, maxminddb.MODE_MEMORY)
            except Exception as e:
                print(f"Warning: Failed to load DB-IP database: {e}")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            # 1. Resolve client IP and proxy info
            peer_ip = request.client.host if request.client else "127.0.0.1"
            cf_connecting_ip = request.headers.get("CF-Connecting-IP")
            
            client_ip = peer_ip
            is_proxy_detected = False
            proxy_type = None

            # First track: Check if Peer IP is Cloudflare trusted range
            if cf_connecting_ip and is_ip_in_networks(peer_ip, self.cloudflare_ips):
                # Verify that CF-Connecting-IP is valid
                try:
                    ipaddress.ip_address(cf_connecting_ip.strip())
                    client_ip = cf_connecting_ip.strip()
                    is_proxy_detected = True
                    proxy_type = "Cloudflare"
                except ValueError:
                    # If invalid, fallback to XFF/Peer IP
                    self._resolve_xff_chain(request, peer_ip, client_ip, is_proxy_detected, proxy_type)
            else:
                # Second track: Traversal of XFF chain
                client_ip, is_proxy_detected, proxy_type = self._resolve_xff_chain(request, peer_ip)

            # 2. Lookup Geolocation / Timezone
            country_code = None
            timezone = None
            
            # Read country from CF Edge if present
            cf_country = request.headers.get("CF-IPCountry")
            if cf_country:
                cf_country = cf_country.strip().upper()
                if len(cf_country) == 2 and cf_country not in ("XX", "T1"):
                    country_code = cf_country

            # Lookup in DB-IP if available (to get timezone, and fallback country if needed)
            if self.db_reader:
                try:
                    geo_data = self.db_reader.get(client_ip)
                    if geo_data:
                        if not country_code:
                            country_code = geo_data.get("country", {}).get("iso_code")
                        timezone = geo_data.get("location", {}).get("time_zone")
                except Exception:
                    pass

            # Fallback timezone based on country code if timezone is missing
            if country_code and not timezone:
                timezone = COUNTRY_TO_TIMEZONE.get(country_code)

            # Override timezone if explicitly provided by the client (e.g. from frontend JS detection)
            client_timezone = request.headers.get("X-Client-Timezone")
            if client_timezone:
                # Sanitize: allow letters, numbers, slashes, hyphens, underscores, plus, minus
                if re.match(r"^[a-zA-Z0-9/_+-]+$", client_timezone):
                    timezone = client_timezone

            # 3. Fallback Pipeline for Locale Decision
            detected_locale = None
            decision_source = None
            confidence_score = 0.0

            # Priority 1: Explicit Cookie 'locale'
            cookie_locale = request.cookies.get("locale")
            if cookie_locale:
                cookie_locale = cookie_locale.strip().lower()
                if cookie_locale in self.supported_locales:
                    detected_locale = cookie_locale
                    decision_source = "EXPLICIT_COOKIE"
                    confidence_score = 1.0

            # Priority 2: Accept-Language Header
            if not detected_locale:
                accept_lang_header = request.headers.get("Accept-Language")
                if accept_lang_header:
                    # Parse accept-language header: e.g. "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
                    parsed_langs = []
                    parts = accept_lang_header.split(",")
                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        subparts = part.split(";")
                        lang_tag = subparts[0].strip().lower()
                        q_val = 1.0
                        if len(subparts) > 1:
                            q_part = subparts[1].strip()
                            if q_part.startswith("q="):
                                try:
                                    q_val = float(q_part[2:])
                                except ValueError:
                                    pass
                        parsed_langs.append((lang_tag, q_val))
                    
                    parsed_langs.sort(key=lambda x: x[1], reverse=True)

                    # 2a: Precise Match
                    for lang_tag, _ in parsed_langs:
                        if lang_tag in self.supported_locales:
                            detected_locale = lang_tag
                            decision_source = "ACCEPT_LANGUAGE_HEADER"
                            confidence_score = 0.85
                            break

                    # 2b: Fuzzy Fallback
                    if not detected_locale:
                        for lang_tag, _ in parsed_langs:
                            primary_tag = lang_tag.split("-")[0].split("_")[0]
                            if primary_tag in self.supported_locales:
                                detected_locale = primary_tag
                                decision_source = "ACCEPT_LANGUAGE_HEADER"
                                confidence_score = 0.65
                                break

            # Priority 3: CF-IPCountry Header
            if not detected_locale and country_code and request.headers.get("CF-IPCountry"):
                mapped_lang = COUNTRY_TO_LOCALE.get(country_code)
                if mapped_lang and mapped_lang in self.supported_locales:
                    detected_locale = mapped_lang
                    decision_source = "CF_EDGE_GEOIP"
                    confidence_score = 0.7

            # Priority 4: Local DB-IP GeoIP lookup
            if not detected_locale and country_code:
                mapped_lang = COUNTRY_TO_LOCALE.get(country_code)
                if mapped_lang and mapped_lang in self.supported_locales:
                    detected_locale = mapped_lang
                    decision_source = "LOCAL_DB_GEOIP"
                    confidence_score = 0.7

            # Priority 5: System Default
            if not detected_locale:
                detected_locale = self.default_locale
                decision_source = "SYSTEM_DEFAULT"
                confidence_score = 0.1

            # Construct ClientContext
            context = ClientContext(
                client=ClientInfo(
                    ip=client_ip,
                    is_proxy_detected=is_proxy_detected,
                    proxy_type=proxy_type
                ),
                i18n=I18nInfo(
                    detected_locale=detected_locale,
                    decision_source=decision_source,
                    confidence_score=confidence_score
                ),
                geo=GeoInfo(
                    country_code=country_code,
                    timezone=timezone
                )
            )

        except Exception as e:
            # Safe Default / Fail-Closed behavior if anything fails inside middleware
            peer_ip = request.client.host if request.client else "127.0.0.1"
            context = ClientContext(
                client=ClientInfo(
                    ip=peer_ip,
                    is_proxy_detected=False,
                    proxy_type=None
                ),
                i18n=I18nInfo(
                    detected_locale=self.default_locale,
                    decision_source="SYSTEM_DEFAULT",
                    confidence_score=0.1
                ),
                geo=GeoInfo(
                    country_code=None,
                    timezone=None
                )
            )

        request.state.client_context = context
        return await call_next(request)

    def _resolve_xff_chain(self, request: Request, peer_ip: str) -> tuple[str, bool, str | None]:
        """Traverse the XFF chain from right to left to resolve the client IP."""
        xff_header = request.headers.get("X-Forwarded-For")
        xff_ips = []
        if xff_header:
            xff_ips = [ip.strip() for ip in xff_header.split(",") if ip.strip()]

        chain = xff_ips + [peer_ip]
        client_ip = peer_ip
        is_proxy_detected = False
        proxy_type = None

        idx = len(chain) - 1
        while idx >= 0:
            current_ip = chain[idx]
            try:
                ipaddress.ip_address(current_ip)
                is_valid = True
            except ValueError:
                is_valid = False

            if not is_valid:
                # If current IP is invalid, we stop and take the last valid IP (chain[idx+1])
                if idx < len(chain) - 1:
                    client_ip = chain[idx + 1]
                else:
                    client_ip = peer_ip
                break

            # Check if current IP is a trusted proxy
            is_trusted = is_ip_in_networks(current_ip, self.trusted_proxies) or is_ip_in_networks(current_ip, self.cloudflare_ips)

            if not is_trusted:
                client_ip = current_ip
                if idx < len(chain) - 1:
                    is_proxy_detected = True
                    proxy_type = "Generic"
                break
            idx -= 1
        else:
            # All IPs were trusted proxies
            if chain:
                client_ip = chain[0]
                is_proxy_detected = True
                proxy_type = "Generic"

        return client_ip, is_proxy_detected, proxy_type
