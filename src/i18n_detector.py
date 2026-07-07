import os
import sys
import time
import socket
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Safe import of third-party dependencies to prevent startup crashes
try:
    import requests
except ImportError:
    requests = None

try:
    import maxminddb
except ImportError:
    maxminddb = None

# =====================================================================
# --- COUNTRY / TIMEZONE / LANGUAGE MAPPING TABLES ---
# =====================================================================

# Mapping of country codes to candidate language codes (preferred order)
COUNTRY_LANGS = {
    "TW": ["zh-TW", "zh", "ja", "en-US"],
    "CN": ["zh-CN", "zh", "en-US"],
    "HK": ["zh-TW", "zh", "en-US"],
    "MO": ["zh-TW", "zh", "en-US"],
    "SG": ["zh-CN", "zh", "en-US"],
    "JP": ["ja", "en-US"],
    "US": ["en-US", "en"],
    "GB": ["en-US", "en"],
    "CA": ["en-US", "en", "fr-FR"],
    "FR": ["fr-FR", "fr", "en-US"],
    "DE": ["de-DE", "de", "en-US"],
    "ES": ["es-US", "es", "en-US"],
    "ID": ["id", "en-US"],
    "IT": ["it", "en-US"],
    "BR": ["pt-BR", "en-US"],
    "PT": ["pt-BR", "en-US"],
    "UA": ["uk", "en-US"],
    "IN": ["hi", "ml", "en-US"],
    "PL": ["pl", "en-US"]
}

# Windows TimeZoneKeyName → ISO 3166-1 alpha-2 country code
# Source: https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/default-time-zones
TZ_TO_COUNTRY: Dict[str, str] = {
    "Taipei Standard Time":         "TW",
    "China Standard Time":          "CN",
    "Singapore Standard Time":      "SG",
    "W. Australia Standard Time":   "AU",
    "Tokyo Standard Time":          "JP",
    "Korea Standard Time":          "KR",
    "India Standard Time":          "IN",
    "SE Asia Standard Time":        "TH",
    "UTC+8":                        "CN",  # generic UTC+8 fallback
    "Eastern Standard Time":        "US",
    "Central Standard Time":        "US",
    "Mountain Standard Time":       "US",
    "Pacific Standard Time":        "US",
    "US Eastern Standard Time":     "US",
    "US Mountain Standard Time":    "US",
    "Alaskan Standard Time":        "US",
    "Hawaiian Standard Time":       "US",
    "GMT Standard Time":            "GB",
    "Greenwich Standard Time":      "GB",
    "Romance Standard Time":        "FR",
    "W. Europe Standard Time":      "DE",
    "Central Europe Standard Time": "DE",
    "Central European Standard Time": "DE",
    "FLE Standard Time":            "UA",
    "E. Europe Standard Time":      "UA",
    "Russian Standard Time":        "RU",
    "E. South America Standard Time": "BR",
    "SA Eastern Standard Time":     "BR",
    "Canada Central Standard Time": "CA",
    "Arab Standard Time":           "SA",
    "Arabic Standard Time":         "SA",
}

# IANA timezone prefix → country code (Linux/macOS fallback)
IANA_PREFIX_TO_COUNTRY: Dict[str, str] = {
    "Asia/Taipei":      "TW",
    "Asia/Shanghai":    "CN",
    "Asia/Beijing":     "CN",
    "Asia/Chongqing":   "CN",
    "Asia/Urumqi":      "CN",
    "Asia/Harbin":      "CN",
    "Asia/Hong_Kong":   "HK",
    "Asia/Macau":       "MO",
    "Asia/Singapore":   "SG",
    "Asia/Tokyo":       "JP",
    "Asia/Seoul":       "KR",
    "Asia/Kolkata":     "IN",
    "Asia/Calcutta":    "IN",
    "Asia/Bangkok":     "TH",
    "Asia/Jakarta":     "ID",
    "America/New_York": "US",
    "America/Chicago":  "US",
    "America/Denver":   "US",
    "America/Phoenix":  "US",
    "America/Los_Angeles": "US",
    "America/Anchorage": "US",
    "America/Honolulu": "US",
    "America/Toronto":  "CA",
    "America/Vancouver": "CA",
    "America/Sao_Paulo": "BR",
    "Europe/London":    "GB",
    "Europe/Paris":     "FR",
    "Europe/Berlin":    "DE",
    "Europe/Kiev":      "UA",
    "Europe/Kyiv":      "UA",
    "Europe/Moscow":    "RU",
}

# ISO 639 language synonym map.
# Maps canonical BCP-47 tag (lower-cased, hyphen-separated) → list of synonyms.
# IMPORTANT: 'chi' and 'zho' are ISO 639-2 codes for *all* Chinese — they are
# intentionally left OUT of zh-cn and placed in the neutral "zh" bucket so
# that the timezone/system-language decides the final zh-TW vs zh-CN mapping.
LANG_SYNONYMS: Dict[str, List[str]] = {
    "zh-tw":    ["zh-tw", "cht", "tpe", "zhtw", "taiwan",
                 "zh-hant", "zh-hant-tw", "traditional"],
    "zh-cn":    ["zh-cn", "chs", "zhcn", "china", "mainland",
                 "zh-hans", "zh-hans-cn", "simplified"],
    # Neutral Chinese: chi / zho / zh are mapped here; runtime decides TW vs CN
    "zh":       ["zh", "chi", "zho", "chinese", "mandarin", "zhongwen"],
    "en-us":    ["en-us", "en", "eng", "english", "usa", "american"],
    "en-gb":    ["en-gb", "en-uk", "british", "uk"],
    "ja":       ["ja", "jp", "jpn", "japanese", "nihongo"],
    "ko":       ["ko", "kr", "kor", "korean"],
    "fr-fr":    ["fr-fr", "fr", "fra", "french", "francais"],
    "de-de":    ["de-de", "de", "deu", "ger", "german", "deutsch"],
    "es-us":    ["es-us", "es", "spa", "spanish", "espanol"],
    "pt-br":    ["pt-br", "pt", "por", "portuguese", "brazil"],
    "id":       ["id", "ind", "indonesian", "bahasa"],
    "hi":       ["hi", "hin", "hindi"],
    "pl":       ["pl", "pol", "polish"],
    "uk":       ["uk", "ukr", "ukrainian"],
    "it":       ["it", "ita", "italian", "italiano"],
    "ml":       ["ml", "mal", "malayalam"],
}

# Reverse lookup: synonym (lower) → canonical tag
_SYNONYM_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _synonyms in LANG_SYNONYMS.items():
    for _syn in _synonyms:
        _SYNONYM_TO_CANONICAL[_syn.lower()] = _canonical


@dataclass
class DetectionResult:
    track_key: str                        # 最佳匹配音軌，例如 "zh-TW"
    source: str                           # 判定決策源
    confidence: float                     # 置信度 (0.0 ~ 1.0)
    detail: str                           # 用於儀表板輸出的日誌
    candidates: List[str] = field(default_factory=list) # 排序後的推薦音軌列表 (由優至劣)
    metadata: Dict[str, Any] = field(default_factory=dict) # 預留給未來擴充層的元數據


# =====================================================================
# --- UTILITY FUNCTIONS ---
# =====================================================================

def is_online(host="8.8.8.8", port=53, timeout=0.40):
    """
    Checks internet connection with a fast TCP connection check.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def get_local_country_by_timezone(system_languages: Optional[List[str]] = None) -> Optional[str]:
    """
    Returns an ISO 3166-1 alpha-2 country code derived from the local system timezone.

    Strategy (in priority order):
      1. Windows: read `TimeZoneKeyName` from the registry — always English, never garbled.
      2. Unix/macOS: read /etc/timezone or resolve /etc/localtime symlink for IANA name.
      3. Legacy fallback: UTC offset heuristic (least reliable, kept as last resort).

    The classic datetime.astimezone().tzinfo.tzname() approach is intentionally
    avoided because on Traditional Chinese Windows it returns garbled BIG5 bytes
    (e.g. b'\\xa5x\\xa5_\\xbc\\u03c7\\xc6\\b\\a6') that make all string comparisons fail.
    """
    # --- Strategy 1: Windows Registry (most reliable on Windows) ---
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
            )
            tz_key_name = winreg.QueryValueEx(key, "TimeZoneKeyName")[0]
            winreg.CloseKey(key)
            if tz_key_name:
                country = TZ_TO_COUNTRY.get(tz_key_name)
                if country:
                    return country
                # Partial prefix scan for unmapped keys
                for tz_key, cc in TZ_TO_COUNTRY.items():
                    if tz_key_name.startswith(tz_key.split()[0]):
                        return cc
        except Exception:
            pass

    # --- Strategy 2: Unix / macOS (/etc/timezone or /etc/localtime symlink) ---
    iana_name = None
    try:
        if os.path.isfile("/etc/timezone"):
            with open("/etc/timezone", "r") as f:
                iana_name = f.read().strip()
        elif os.path.islink("/etc/localtime"):
            link_target = os.readlink("/etc/localtime")
            # e.g. /usr/share/zoneinfo/Asia/Taipei
            if "zoneinfo/" in link_target:
                iana_name = link_target.split("zoneinfo/", 1)[1]
    except Exception:
        pass

    if iana_name:
        country = IANA_PREFIX_TO_COUNTRY.get(iana_name)
        if country:
            return country
        # Prefix scan for sub-zones (e.g. Asia/Shanghai → CN)
        for iana_prefix, cc in IANA_PREFIX_TO_COUNTRY.items():
            if iana_name.startswith(iana_prefix):
                return cc

    # --- Strategy 3: Legacy UTC offset heuristic (CST disambiguation) ---
    try:
        now = datetime.datetime.now()
        tz_info = now.astimezone().tzinfo
        if tz_info:
            offset_hours = tz_info.utcoffset(now).total_seconds() / 3600
            if offset_hours == 8:
                # UTC+8: could be TW, CN, HK, SG, etc. — use system_languages to disambiguate
                if system_languages:
                    first = system_languages[0].lower()
                    if first.startswith("zh-tw") or first.startswith("zh_tw"):
                        return "TW"
                    if first.startswith("zh-cn") or first.startswith("zh_cn"):
                        return "CN"
                    if first.startswith("ja"):
                        return "JP"
                return "CN"  # conservative fallback for UTC+8
            elif -5 <= offset_hours <= -4:
                return "US"
            elif offset_hours == 9:
                return "JP"
            elif 0 <= offset_hours <= 1:
                return "GB"
    except Exception:
        pass

    return None


def get_online_geoip(timeout=0.8):
    """
    Fetches online GeoIP info (IP and Country Code) from HTTPS-only public APIs.
    Falls back silently on timeout, DNS failure, or rate-limit (HTTP 429).

    Endpoints (all HTTPS):
      1. https://ipapi.co/json/    — primary
      2. https://ipwho.is/         — backup  (note: ip-api.com HTTP is intentionally excluded)
    """
    if not requests:
        return None, None
    apis = [
        (
            "https://ipapi.co/json/",
            lambda r: (r.get("ip"), r.get("country_code"))
        ),
        (
            "https://ipwho.is/",
            lambda r: (r.get("ip"), r.get("country_code"))
        ),
    ]
    for url, parser in apis:
        try:
            r = requests.get(url, timeout=timeout)
            # Respect rate-limiting: skip silently on 429
            if r.status_code == 429:
                continue
            if r.status_code == 200:
                data = r.json()
                ip, country = parser(data)
                if ip and country:
                    return ip, country.upper()
        except Exception:
            continue
    return None, None


def get_system_proxy_info() -> dict:
    """
    Detects system-level proxy configurations with zero dependencies.
    """
    try:
        import urllib.request
        proxies = urllib.request.getproxies()
        if proxies:
            details = ", ".join([f"{k}: {v}" for k, v in proxies.items()])
            return {"proxy_detected": True, "details": details}
    except Exception:
        pass
    return {"proxy_detected": False, "details": "Direct Connection"}


def normalize_locale(locale_str):
    """
    Normalizes locale separator and case.
    e.g., 'zh_TW' -> 'zh-tw'
    """
    if not locale_str:
        return ""
    return locale_str.replace("_", "-").lower().strip()


def _expand_canonical(locale_candidate: str) -> List[str]:
    """
    Given a locale candidate (e.g. 'zh-TW'), returns all known synonyms
    for that canonical tag as well as the candidate itself.
    Used to expand the search space when scanning available_tracks.
    """
    norm = normalize_locale(locale_candidate)
    # Direct synonym list lookup
    canonical = _SYNONYM_TO_CANONICAL.get(norm, norm)
    synonyms = LANG_SYNONYMS.get(canonical, [norm])
    # Also include the raw normalized candidate in case it's not in the table
    all_variants = list(dict.fromkeys([norm] + [s.lower() for s in synonyms]))
    return all_variants


def match_track_exact(locale_candidate, available_tracks) -> Optional[str]:
    """
    Checks exact matches after normalization, with synonym expansion.
    e.g., candidate 'zh-TW' will also match a track named 'cht'.
    """
    if not locale_candidate:
        return None
    expanded = _expand_canonical(locale_candidate)
    for track in available_tracks:
        norm_track = normalize_locale(track)
        if norm_track in expanded:
            return track
    return None


def match_track_fuzzy(locale_candidate, available_tracks) -> Optional[str]:
    """
    Checks prefix/fuzzy matches after normalization and synonym expansion.
    Falls back to the previous prefix-match logic if exact synonym match fails.
    """
    if not locale_candidate:
        return None
    expanded = _expand_canonical(locale_candidate)
    norm_cand = normalize_locale(locale_candidate)

    # First pass: try any synonym exact match (already done by match_track_exact,
    # but kept here for callers that only call fuzzy)
    for track in available_tracks:
        if normalize_locale(track) in expanded:
            return track

    # Second pass: prefix matching against the primary candidate and its root
    for track in available_tracks:
        norm_track = normalize_locale(track)
        if norm_track.startswith(norm_cand) or norm_cand.startswith(norm_track):
            p1 = norm_track.split("-")[0]
            p2 = norm_cand.split("-")[0]
            if p1 == p2:
                return track

    return None


def _resolve_neutral_zh(available_tracks: List[str], tz_country: Optional[str],
                         system_languages: Optional[List[str]]) -> Optional[str]:
    """
    Resolves neutral Chinese tracks (chi, zho, zh) to zh-TW or zh-CN
    based on timezone country and system language preferences.

    Returns the matched track key, or None if no neutral Chinese track found.
    """
    neutral_synonyms = set(LANG_SYNONYMS.get("zh", []))

    # Find any neutral Chinese track in available_tracks
    neutral_tracks = [t for t in available_tracks
                      if normalize_locale(t) in neutral_synonyms]
    if not neutral_tracks:
        return None

    # Determine target region: TW or CN
    target_region = None
    if tz_country in ("TW", "HK", "MO"):
        target_region = "TW"
    elif tz_country in ("CN", "SG"):
        target_region = "CN"
    elif system_languages:
        for lang in system_languages:
            n = normalize_locale(lang)
            if n.startswith("zh-tw") or n.startswith("zh_tw") or n.startswith("zh-hant"):
                target_region = "TW"
                break
            if n.startswith("zh-cn") or n.startswith("zh_cn") or n.startswith("zh-hans"):
                target_region = "CN"
                break

    # Return first neutral track (region is contextual metadata, track key stays as-is)
    return neutral_tracks[0]


# =====================================================================
# --- STRATEGY PATTERN FOR DECISION TREE ---
# =====================================================================

class I18nStrategy(ABC):
    @abstractmethod
    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        """執行該層決策邏輯，成功匹配則回傳 DetectionResult，否則回傳 None 讓下一層處理"""
        pass


class ExplicitHistoryStrategy(I18nStrategy):
    """【P1】 使用者本地手動選擇歷史紀錄偏好"""
    def __init__(self, history_lang: Optional[str]):
        self.history_lang = history_lang

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.history_lang:
            return None
        matched = match_track_exact(self.history_lang, available_tracks)
        if not matched:
            matched = match_track_fuzzy(self.history_lang, available_tracks)
            
        if matched:
            detail = f"偵測到歷史選擇偏好：{self.history_lang} -> 完美匹配音軌 [{matched}]"
            cands = [matched] + [t for t in available_tracks if t != matched]
            return DetectionResult(matched, "P1 EXPLICIT_HISTORY", 1.0, detail, candidates=cands)
        return None


class OsLanguagesExactStrategy(I18nStrategy):
    """【P2a】 作業系統偏好語言清單 - 精確比對 (優先級高，避免區域歧義被模糊匹配截斷)"""
    def __init__(self, system_languages: List[str], tz_country: Optional[str] = None):
        self.system_languages = system_languages
        self.tz_country = tz_country

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.system_languages:
            return None
        for lang in self.system_languages:
            matched = match_track_exact(lang, available_tracks)
            if matched:
                detail = f"依據系統語言優先級精確匹配：{lang} -> 匹配音軌 [{matched}]"
                cands = [matched] + [t for t in available_tracks if t != matched]
                return DetectionResult(matched, "P2a OS_UI_LANGS_EXACT", 0.85, detail, candidates=cands)

        # Neutral Chinese resolution: if OS lang is 'zh' and there's a neutral-zh track
        for lang in self.system_languages:
            norm = normalize_locale(lang)
            if norm.startswith("zh"):
                neutral = _resolve_neutral_zh(available_tracks, self.tz_country, self.system_languages)
                if neutral:
                    detail = f"系統語言 [{lang}] 命中中性中文音軌 [{neutral}]（時區國家: {self.tz_country}）"
                    cands = [neutral] + [t for t in available_tracks if t != neutral]
                    return DetectionResult(neutral, "P2a OS_UI_LANGS_EXACT", 0.80, detail, candidates=cands)
        return None


class TimezoneDisambiguationStrategy(I18nStrategy):
    """【P4a】 時區區域歧義消除策略 (離線 0ms, 當精確比對失敗，利用時區優先判斷區域音軌)"""
    def __init__(self, system_languages: List[str], tz_country: Optional[str] = None):
        self.system_languages = system_languages
        self.tz_country = tz_country

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.system_languages:
            return None

        # Use the pre-computed tz_country if available, otherwise re-compute
        tz_country = self.tz_country if self.tz_country else \
            get_local_country_by_timezone(self.system_languages)

        # 處理歐盟等模糊時區
        if tz_country == "EU" or not tz_country:
            first_lang = self.system_languages[0].split("-")[0].split("_")[0].lower() \
                if self.system_languages else "en"
            lang_to_country = {"zh": "TW", "ja": "JP", "de": "DE", "fr": "FR", "es": "ES"}
            tz_country = lang_to_country.get(first_lang, tz_country)

        if tz_country and tz_country != "EU":
            candidates = COUNTRY_LANGS.get(tz_country, [])
            for cand in candidates:
                # 優先使用精確匹配找出最適區域版本
                matched = match_track_exact(cand, available_tracks)
                if not matched:
                    matched = match_track_fuzzy(cand, available_tracks)
                    
                if matched:
                    # 交叉檢查系統語言是否包含該語系
                    os_primary = [l.split("-")[0].split("_")[0].lower() for l in self.system_languages]
                    cand_primary = cand.split("-")[0].split("_")[0].lower()
                    if cand_primary in os_primary:
                        detail = (f"時區偏好消除歧義成功 (時區國家: {tz_country} × 語言: {cand_primary})"
                                  f" -> 匹配音軌 [{matched}]")
                        cands = [matched] + [t for t in available_tracks if t != matched]
                        return DetectionResult(
                            matched, "P4a TIMEZONE_CROSS", 0.80, detail,
                            candidates=cands,
                            metadata={"country": tz_country}
                        )
        return None


class OsLanguagesFuzzyStrategy(I18nStrategy):
    """【P2b】 作業系統偏好語言清單 - 模糊比對 (時區未匹配時的保底模糊搜尋)"""
    def __init__(self, system_languages: List[str]):
        self.system_languages = system_languages

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.system_languages:
            return None
        for lang in self.system_languages:
            primary_lang = lang.split("-")[0].split("_")[0]
            matched = match_track_fuzzy(primary_lang, available_tracks)
            if matched:
                detail = f"依據系統語言模糊比對：{primary_lang} -> 匹配音軌 [{matched}]"
                cands = [matched] + [t for t in available_tracks if t != matched]
                return DetectionResult(matched, "P2b OS_UI_LANGS_FUZZY", 0.65, detail, candidates=cands)
        return None


class GeoIpStrategy(I18nStrategy):
    """【P4b & P4c】 本地 MMDB 離線地理查詢與線上 API 交叉驗證"""
    def __init__(self, db_path: Optional[str], public_ip: Optional[str] = None, geo_country: Optional[str] = None):
        self.db_path = db_path
        self.public_ip = public_ip
        self.geo_country = geo_country

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.db_path or not os.path.exists(self.db_path) or not maxminddb:
            return None
            
        if self.public_ip and self.geo_country:
            # P4c: 線上 API 與本地資料庫交叉比對
            try:
                with maxminddb.open_database(self.db_path, maxminddb.MODE_MEMORY) as reader:
                    geo_data = reader.get(self.public_ip)
                    local_country = None
                    if geo_data:
                        local_country = geo_data.get("country", {}).get("iso_code")
                        
                    if local_country:
                        local_country = local_country.upper()
                        
                    # 一致性校驗
                    if self.geo_country == local_country:
                        candidates = COUNTRY_LANGS.get(self.geo_country, [])
                        for cand in candidates:
                            matched = match_track_exact(cand, available_tracks)
                            if not matched:
                                matched = match_track_fuzzy(cand, available_tracks)
                                
                            if matched:
                                detail = (f"地理定位安全驗證成功：聯網檢測與離線資料庫一致"
                                          f" (IP: {self.public_ip} -> {self.geo_country}) -> 匹配音軌 [{matched}]")
                                cands = [matched] + [t for t in available_tracks if t != matched]
                                return DetectionResult(
                                    matched, "P4c GEOIP_VERIFIED", 0.95, detail,
                                    candidates=cands,
                                    metadata={"ip": self.public_ip, "country": self.geo_country}
                                )
                                
                    # 不一致：以本地資料庫為準降級 (P4b)
                    query_country = local_country if local_country else self.geo_country
                    candidates = COUNTRY_LANGS.get(query_country, [])
                    for cand in candidates:
                        matched = match_track_exact(cand, available_tracks)
                        if not matched:
                            matched = match_track_fuzzy(cand, available_tracks)
                            
                        if matched:
                            detail = (f"地理定位查詢成功 (API/本地數據不吻合或使用備援結果:"
                                      f" {query_country}) -> 匹配音軌 [{matched}]")
                            cands = [matched] + [t for t in available_tracks if t != matched]
                            return DetectionResult(
                                matched, "P4b LOCAL_DB_ONLY", 0.85, detail,
                                candidates=cands,
                                metadata={"ip": self.public_ip, "country": query_country, "local_db": True}
                            )
            except Exception as e:
                # 本地資料庫異常 fallback
                candidates = COUNTRY_LANGS.get(self.geo_country, [])
                for cand in candidates:
                    matched = match_track_exact(cand, available_tracks)
                    if not matched:
                        matched = match_track_fuzzy(cand, available_tracks)
                        
                    if matched:
                        detail = (f"線上地理定位查詢成功 (本地資料庫讀取異常, 採用 API 資料:"
                                  f" {self.geo_country}) -> 匹配音軌 [{matched}]")
                        cands = [matched] + [t for t in available_tracks if t != matched]
                        return DetectionResult(
                            matched, "P4b LOCAL_DB_ONLY", 0.85, detail,
                            candidates=cands,
                            metadata={"ip": self.public_ip, "country": self.geo_country, "local_db_error": str(e)}
                        )
        return None


class DefaultFallbackStrategy(I18nStrategy):
    """【P5】 智慧型預設語系 (zh-TW 優先兜底) / 影片首軌"""
    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        # 1. 優先在可用音軌中找 zh-TW 進行兜底，契合台灣在地化使用習慣
        for l in ["zh-TW", "zh", "en-US", "en"]:
            matched = match_track_exact(l, available_tracks)
            if not matched:
                matched = match_track_fuzzy(l, available_tracks)
            if matched:
                detail = f"無高優先級匹配，採用智慧預設語系 ({l}) -> 匹配音軌 [{matched}]"
                cands = [matched] + [t for t in available_tracks if t != matched]
                return DetectionResult(matched, "P5 SYSTEM_DEFAULT", 0.15, detail, candidates=cands)
                
        # 2. 若完全無匹配，降級採用影片預設首軌
        ultimate_fallback = available_tracks[0] if available_tracks else "en-US"
        detail = f"無任何匹配，降級採用影片預設首軌 -> 匹配音軌 [{ultimate_fallback}]"
        return DetectionResult(ultimate_fallback, "P5 SYSTEM_DEFAULT", 0.05, detail, candidates=available_tracks)


# =====================================================================
# --- ORCHESTRATOR & API WRAPPERS ---
# =====================================================================

class I18nDetector:
    def __init__(self, strategies: List[I18nStrategy]):
        self.strategies = strategies

    def execute(self, available_tracks: List[str]) -> DetectionResult:
        strategy_names = {
            "ExplicitHistoryStrategy": "用戶習慣",
            "OsLanguagesExactStrategy": "系統語言精確",
            "TimezoneDisambiguationStrategy": "時區消除歧義",
            "OsLanguagesFuzzyStrategy": "系統語言模糊",
            "GeoIpStrategy": "地理定位",
            "DefaultFallbackStrategy": "智慧兜底"
        }
        
        path_nodes = []
        final_res = None
        
        for strategy in self.strategies:
            cls_name = strategy.__class__.__name__
            friendly_name = strategy_names.get(cls_name, cls_name)
            
            res = strategy.detect(available_tracks)
            if res is not None:
                path_nodes.append(f"{friendly_name}(找到: {res.track_key})")
                final_res = res
                break
            else:
                path_nodes.append(f"{friendly_name}(未找到)")
                
        decision_path_str = " ➔ ".join(path_nodes)
        
        if final_res is not None:
            final_res.metadata["decision_chain"] = decision_path_str
            return final_res
            
        fallback_track = available_tracks[0] if available_tracks else "en-US"
        path_nodes.append(f"影片首軌兜底(找到: {fallback_track})")
        decision_path_str = " ➔ ".join(path_nodes)
        
        fallback_res = DetectionResult(fallback_track, "FALLBACK", 0.0, "策略鏈皆未命中，採用首軌。", candidates=available_tracks)
        fallback_res.metadata["decision_chain"] = decision_path_str
        return fallback_res


def detect_best_locale(
    available_tracks: List[str],
    system_languages: Optional[List[str]] = None,
    history_language: Optional[str] = None,
    db_path: Optional[str] = None
) -> DetectionResult:
    """
    外部調用便捷函數。以依賴注入方式接受系統偏好、歷史設定及資料庫路徑，內部執行策略鏈比對。

    Zero-Trust Security Assessment:
    - The local timezone country (`tz_country`) is always resolved first and
      written to metadata["tz_country"], regardless of which strategy wins.
    - If the GeoIP API returns a different country AND a system proxy is active,
      metadata["proxy_warning"] is set to True and the final confidence is
      reduced by 0.40 (floor: 0.10) to flag potential VPN/geo-spoofing.
    """
    if system_languages is None:
        system_languages = []
        try:
            import locale
            # 優先嘗試 Python 3.11+ 建議的 getlocale()
            loc = locale.getlocale(locale.LC_MESSAGES)
            if loc and loc[0]:
                system_languages.append(loc[0])
        except Exception:
            pass
            
        # 若仍然沒有且在 Windows 平台下，可使用 Windows API 原生 UI 語言
        if not system_languages and os.name == 'nt':
            try:
                import ctypes
                import locale
                windll = ctypes.windll.kernel32
                lcid = windll.GetUserDefaultUILanguage()
                loc_str = locale.windows_locale.get(lcid)
                if loc_str:
                    system_languages.append(loc_str)
            except Exception:
                pass
                
        # 最終智慧兜底
        if not system_languages:
            system_languages.append("zh-TW")

    # ── Pre-compute timezone country (always, regardless of strategy chosen) ──
    tz_country = get_local_country_by_timezone(system_languages)

    # ── Pre-fetch GeoIP to stamp into metadata and reuse in GeoIpStrategy ──
    public_ip = None
    geo_country = None
    if is_online(timeout=0.30):
        public_ip, geo_country = get_online_geoip(timeout=0.8)

    # V7 決策鏈順序：歷史 (P1) -> 精確匹配+中性中文 (P2a) -> 時區消除歧義 (P4a)
    #               -> 模糊匹配 (P2b) -> 地理定位 (P4b/P4c) -> 兜底 (P5)
    strategies = [
        ExplicitHistoryStrategy(history_language),
        OsLanguagesExactStrategy(system_languages, tz_country=tz_country),
        TimezoneDisambiguationStrategy(system_languages, tz_country=tz_country),
        OsLanguagesFuzzyStrategy(system_languages),
        GeoIpStrategy(db_path, public_ip=public_ip, geo_country=geo_country),
        DefaultFallbackStrategy()
    ]
    detector = I18nDetector(strategies)
    res = detector.execute(available_tracks)

    # ── Always stamp tz_country, public_ip and geo_country into metadata ──
    res.metadata["tz_country"] = tz_country
    res.metadata["ip"] = public_ip if public_ip else "127.0.0.1 (本地端)"
    res.metadata["country"] = geo_country if geo_country else "未定位"

    # ── Enrich metadata with client-side Zero-Trust proxy info ──
    proxy_info = get_system_proxy_info()
    res.metadata.update(proxy_info)

    # ── Zero-Trust cross-validation: GeoIP country vs timezone country ──
    geo_country = res.metadata.get("country")
    proxy_detected = res.metadata.get("proxy_detected", False)
    if tz_country and geo_country and geo_country != tz_country and proxy_detected:
        res.metadata["proxy_warning"] = True
        res.metadata["proxy_warning_detail"] = (
            f"警告：地理位置與時區不吻合！"
            f"時區國家={tz_country}, GeoIP 國家={geo_country}, 代理已開啟。"
            f"疑似使用 VPN 繞過或地理位置偽裝。"
        )
        # Deduct confidence — floor at 0.10
        res.confidence = max(round(res.confidence - 0.40, 2), 0.10)
        res.detail += f" | ⚠️ 零信任警告：{res.metadata['proxy_warning_detail']}"
    else:
        res.metadata["proxy_warning"] = False

    return res


if __name__ == "__main__":
    print("🧪 啟動 i18n_detector.py 單體測試 (V7 Registry + 同義詞 + 零信任版)...")

    # ── 測試 1：時區 Registry 讀取 ──
    print("\n[Test 1] 時區國家讀取 (Registry / /etc/timezone):")
    tz_c = get_local_country_by_timezone(["zh-TW"])
    print(f"  get_local_country_by_timezone() = {tz_c!r}  (期望: 'TW')")

    # ── 測試 2：同義詞 - cht / zhtw 應命中 zh-TW 系統語言 ──
    print("\n[Test 2] 同義詞比對 — 音軌 ['cht', 'eng']，系統語言 zh-TW:")
    res2 = detect_best_locale(["cht", "eng"], system_languages=["zh-TW"])
    print(f"  track_key = {res2.track_key!r}  (期望: 'cht')")
    print(f"  source    = {res2.source}")
    print(f"  confidence= {res2.confidence}")

    # ── 測試 3：同義詞 - zhtw 應命中 zh-TW ──
    print("\n[Test 3] 同義詞比對 — 音軌 ['zhtw', 'eng']，系統語言 zh-TW:")
    res3 = detect_best_locale(["zhtw", "eng"], system_languages=["zh-TW"])
    print(f"  track_key = {res3.track_key!r}  (期望: 'zhtw')")
    print(f"  source    = {res3.source}")

    # ── 測試 4：中性中文 chi 由時區決定 ──
    print("\n[Test 4] 中性中文 chi — 音軌 ['chi', 'eng']，系統語言 zh，時區 TW:")
    res4 = detect_best_locale(["chi", "eng"], system_languages=["zh"])
    print(f"  track_key = {res4.track_key!r}  (期望: 'chi')")
    print(f"  source    = {res4.source}")
    print(f"  tz_country= {res4.metadata.get('tz_country')}")

    # ── 測試 5：時區消除歧義 ['zh-CN', 'zh-TW']，系統語言 zh，時區 TW ──
    print("\n[Test 5] 時區消除歧義 — 音軌 ['zh-CN', 'zh-TW']，系統語言 ['zh']:")
    res5 = detect_best_locale(["zh-CN", "zh-TW"], system_languages=["zh"])
    print(f"  track_key = {res5.track_key!r}  (期望: 'zh-TW')")
    print(f"  source    = {res5.source}")
    print(f"  confidence= {res5.confidence}")

    # ── 測試 6：零信任模擬 (手動注入 proxy_warning 場景) ──
    print("\n[Test 6] 零信任模擬 — metadata 驗證:")
    res6 = detect_best_locale(["zh-TW", "en-US"], system_languages=["zh-TW"])
    print(f"  tz_country    = {res6.metadata.get('tz_country')!r}")
    print(f"  proxy_detected= {res6.metadata.get('proxy_detected')}")
    print(f"  proxy_warning = {res6.metadata.get('proxy_warning')}")
    print(f"  confidence    = {res6.confidence}")
    print(f"  detail        = {res6.detail}")
