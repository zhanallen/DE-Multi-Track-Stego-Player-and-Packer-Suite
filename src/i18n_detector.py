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

@dataclass
class DetectionResult:
    track_key: str                        # 最佳匹配音軌，例如 "zh-TW"
    source: str                           # 判定決策源
    confidence: float                     # 置信度 (0.0 ~ 1.0)
    detail: str                           # 用於儀表板輸出的日誌
    candidates: List[str] = field(default_factory=list) # 排序後的推薦音軌列表 (由優至劣)
    metadata: Dict[str, Any] = field(default_factory=dict) # 預留給未來擴充層的元數據

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
    Maps local timezone to a country code using built-in datetime/time.
    Zero dependency. Resolves CST ambiguities using system_languages fallback.
    """
    try:
        now = datetime.datetime.now()
        tz_info = now.astimezone().tzinfo
        tz_name = tz_info.tzname(now) if tz_info else ""
        if not tz_name:
            tz_name = time.tzname[0]
            
        tz_name_lower = tz_name.lower()
        
        if any(x in tz_name_lower for x in ["taipei", "taiwan", "tst"]):
            return "TW"
        if any(x in tz_name_lower for x in ["china", "beijing", "shanghai", "cst"]):
            # CST can be China Standard Time (UTC+8) or Central Standard Time (US, UTC-6)
            if "cst" in tz_name_lower:
                if tz_info:
                    offset = tz_info.utcoffset(now)
                    if offset and offset.total_seconds() < 0:
                        return "US"
                # Fallback: check system languages. If not Chinese, default to US
                has_zh = False
                if system_languages:
                    has_zh = any(l.lower().startswith("zh") for l in system_languages)
                if not has_zh:
                    return "US"
            return "CN"
        if any(x in tz_name_lower for x in ["tokyo", "japan", "jst"]):
            return "JP"
        if any(x in tz_name_lower for x in ["london", "gmt", "bst", "western europe"]):
            return "GB"
        if any(x in tz_name_lower for x in ["romance", "w. europe", "paris", "berlin", "cet", "cest"]):
            return "EU"
        if any(x in tz_name_lower for x in ["eastern", "pacific", "central", "mountain", "est", "pst", "mst"]):
            return "US"
    except Exception:
        pass
    return None

def get_online_geoip(timeout=1.5):
    """
    Fetches online GeoIP info (IP and Country Code) from public APIs.
    """
    if not requests:
        return None, None
    apis = [
        ("http://ip-api.com/json", lambda r: (r.get("query"), r.get("countryCode"))),
        ("https://ipapi.co/json/", lambda r: (r.get("ip"), r.get("country_code")))
    ]
    for url, parser in apis:
        try:
            r = requests.get(url, timeout=timeout)
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

def match_track_exact(locale_candidate, available_tracks) -> Optional[str]:
    """
    Checks exact matches after normalization.
    """
    norm_cand = normalize_locale(locale_candidate)
    if not norm_cand:
        return None
    for track in available_tracks:
        if normalize_locale(track) == norm_cand:
            return track
    return None

def match_track_fuzzy(locale_candidate, available_tracks) -> Optional[str]:
    """
    Checks prefix/fuzzy matches after normalization.
    """
    norm_cand = normalize_locale(locale_candidate)
    if not norm_cand:
        return None
    for track in available_tracks:
        norm_track = normalize_locale(track)
        if norm_track.startswith(norm_cand) or norm_cand.startswith(norm_track):
            p1 = norm_track.split("-")[0]
            p2 = norm_cand.split("-")[0]
            if p1 == p2:
                return track
    return None


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
    def __init__(self, system_languages: List[str]):
        self.system_languages = system_languages

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.system_languages:
            return None
        for lang in self.system_languages:
            matched = match_track_exact(lang, available_tracks)
            if matched:
                detail = f"依據系統語言優先級精確匹配：{lang} -> 匹配音軌 [{matched}]"
                cands = [matched] + [t for t in available_tracks if t != matched]
                return DetectionResult(matched, "P2a OS_UI_LANGS_EXACT", 0.85, detail, candidates=cands)
        return None


class TimezoneDisambiguationStrategy(I18nStrategy):
    """【P4a】 時區區域歧義消除策略 (離線 0ms, 當精確比對失敗，利用時區優先判斷區域音軌)"""
    def __init__(self, system_languages: List[str]):
        self.system_languages = system_languages

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.system_languages:
            return None
            
        tz_country = get_local_country_by_timezone(self.system_languages)
        
        # 處理歐盟等模糊時區
        if tz_country == "EU" or not tz_country:
            first_lang = self.system_languages[0].split("-")[0].split("_")[0].lower() if self.system_languages else "en"
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
                    # 交叉檢查系統語言是否包含該語系 (例如使用者支援 zh 且處於 TW 時區，則匹配 zh-TW)
                    os_primary = [l.split("-")[0].split("_")[0].lower() for l in self.system_languages]
                    cand_primary = cand.split("-")[0].split("_")[0].lower()
                    if cand_primary in os_primary:
                        detail = f"時區偏好消除歧義成功 (時區國家: {tz_country} × 語言: {cand_primary}) -> 匹配音軌 [{matched}]"
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
    def __init__(self, db_path: Optional[str]):
        self.db_path = db_path

    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        if not self.db_path or not os.path.exists(self.db_path) or not maxminddb:
            return None
            
        # 快速聯網檢測 (400ms 超時)
        online = is_online(timeout=0.40)
        
        if online and requests:
            # P4c: 線上 API 與本地資料庫交叉比對
            public_ip, api_country = get_online_geoip(timeout=1.5)
            if public_ip and api_country:
                try:
                    with maxminddb.open_database(self.db_path, maxminddb.MODE_MEMORY) as reader:
                        geo_data = reader.get(public_ip)
                        local_country = None
                        if geo_data:
                            local_country = geo_data.get("country", {}).get("iso_code")
                            
                        if local_country:
                            local_country = local_country.upper()
                            
                        # 一致性校驗
                        if api_country == local_country:
                            candidates = COUNTRY_LANGS.get(api_country, [])
                            for cand in candidates:
                                matched = match_track_exact(cand, available_tracks)
                                if not matched:
                                    matched = match_track_fuzzy(cand, available_tracks)
                                    
                                if matched:
                                    detail = f"地理定位安全驗證成功：聯網檢測與離線資料庫一致 (IP: {public_ip} -> {api_country}) -> 匹配音軌 [{matched}]"
                                    cands = [matched] + [t for t in available_tracks if t != matched]
                                    return DetectionResult(
                                        matched, "P4c GEOIP_VERIFIED", 0.95, detail, 
                                        candidates=cands, 
                                        metadata={"ip": public_ip, "country": api_country}
                                    )
                                    
                        # 不一致：以本地資料庫為準降級 (P4b)
                        query_country = local_country if local_country else api_country
                        candidates = COUNTRY_LANGS.get(query_country, [])
                        for cand in candidates:
                            matched = match_track_exact(cand, available_tracks)
                            if not matched:
                                matched = match_track_fuzzy(cand, available_tracks)
                                
                            if matched:
                                detail = f"地理定位查詢成功 (API/本地數據不吻合或使用備援結果: {query_country}) -> 匹配音軌 [{matched}]"
                                cands = [matched] + [t for t in available_tracks if t != matched]
                                return DetectionResult(
                                    matched, "P4b LOCAL_DB_ONLY", 0.85, detail, 
                                    candidates=cands, 
                                    metadata={"ip": public_ip, "country": query_country, "local_db": True}
                                )
                except Exception as e:
                    # 本地資料庫異常 fallback
                    candidates = COUNTRY_LANGS.get(api_country, [])
                    for cand in candidates:
                        matched = match_track_exact(cand, available_tracks)
                        if not matched:
                            matched = match_track_fuzzy(cand, available_tracks)
                            
                        if matched:
                            detail = f"線上地理定位查詢成功 (本地資料庫讀取異常, 採用 API 資料: {api_country}) -> 匹配音軌 [{matched}]"
                            cands = [matched] + [t for t in available_tracks if t != matched]
                            return DetectionResult(
                                matched, "P4b LOCAL_DB_ONLY", 0.85, detail, 
                                candidates=cands, 
                                metadata={"ip": public_ip, "country": api_country, "local_db_error": str(e)}
                            )
        return None


class DefaultFallbackStrategy(I18nStrategy):
    """【P5】 系統預設語系 (en-US) / 影片首軌"""
    def detect(self, available_tracks: List[str]) -> Optional[DetectionResult]:
        matched = match_track_exact("en-US", available_tracks)
        if not matched:
            matched = match_track_fuzzy("en-US", available_tracks)
        if not matched:
            matched = match_track_exact("en", available_tracks)
        if not matched:
            matched = match_track_fuzzy("en", available_tracks)
            
        if matched:
            detail = f"無高優先級匹配，採用系統預設語系 (en-US) -> 匹配音軌 [{matched}]"
            cands = [matched] + [t for t in available_tracks if t != matched]
            return DetectionResult(matched, "P5 SYSTEM_DEFAULT", 0.10, detail, candidates=cands)
            
        ultimate_fallback = available_tracks[0]
        detail = f"無任何匹配，降級採用影片預設首軌 -> 匹配音軌 [{ultimate_fallback}]"
        return DetectionResult(ultimate_fallback, "P5 SYSTEM_DEFAULT", 0.05, detail, candidates=available_tracks)


# =====================================================================
# --- ORCHESTRATOR & API WRAPPERS ---
# =====================================================================

class I18nDetector:
    def __init__(self, strategies: List[I18nStrategy]):
        self.strategies = strategies

    def execute(self, available_tracks: List[str]) -> DetectionResult:
        for strategy in self.strategies:
            res = strategy.detect(available_tracks)
            if res is not None:
                return res
        fallback_track = available_tracks[0] if available_tracks else "en-US"
        return DetectionResult(fallback_track, "FALLBACK", 0.0, "策略鏈皆未命中，採用首軌。", candidates=available_tracks)


def detect_best_locale(
    available_tracks: List[str],
    system_languages: Optional[List[str]] = None,
    history_language: Optional[str] = None,
    db_path: Optional[str] = None
) -> DetectionResult:
    """
    外部調用便捷函數。以依賴注入方式接受系統偏好、歷史設定及資料庫路徑，內部執行策略鏈比對。
    """
    if system_languages is None:
        system_languages = []
        try:
            import locale
            default_loc = locale.getdefaultlocale()[0]
            if default_loc:
                system_languages.append(default_loc)
        except Exception:
            pass

    # V6 決策鏈順序：精確匹配 (P2a) -> 時區消除歧義 (P4a) -> 模糊匹配 (P2b) -> 地理定位 (P4b/P4c) -> 兜底 (P5)
    strategies = [
        ExplicitHistoryStrategy(history_language),
        OsLanguagesExactStrategy(system_languages),
        TimezoneDisambiguationStrategy(system_languages),
        OsLanguagesFuzzyStrategy(system_languages),
        GeoIpStrategy(db_path),
        DefaultFallbackStrategy()
    ]
    detector = I18nDetector(strategies)
    res = detector.execute(available_tracks)
    
    # Enrich metadata with client-side Zero-Trust proxy info
    proxy_info = get_system_proxy_info()
    res.metadata.update(proxy_info)
    
    return res


if __name__ == "__main__":
    print("🧪 啟動 i18n_detector.py 單體測試 (V6 策略消除歧義版)...")
    
    # 測試案例 1：時區消除歧義測試 (模擬地區中立的 OS 語言 'zh')
    # 若有 ['zh-CN', 'zh-TW'] 音軌，且時區為台灣，應正確消除歧義選擇 'zh-TW'
    test_tracks = ["zh-CN", "zh-TW"]
    sim_sys_langs = ["zh"]
    sim_history = None
    
    # 模擬台灣時區環境
    print(f"模擬可用音軌: {test_tracks} | OS 優先語言: {sim_sys_langs} | 本地時區: 台北")
    res = detect_best_locale(
        available_tracks=test_tracks,
        system_languages=sim_sys_langs,
        history_language=sim_history,
        db_path=None
    )
    print("\n--- 決策樹輸出結果 ---")
    print(f"匹配音軌 Key: {res.track_key}")
    print(f"決策來源 Source: {res.source}")
    print(f"置信度 Confidence: {res.confidence}")
    print(f"詳細分析 Detail: {res.detail}")
    print(f"排序候選列表 Candidates: {res.candidates}")
