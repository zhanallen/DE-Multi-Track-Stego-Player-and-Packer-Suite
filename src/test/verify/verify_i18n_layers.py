"""TC-PL-06：語系判定六層決策鏈逐層命中（STP 1.2，Q4-5）；另重現 TC-PL-08 的 IP 鎖定路徑（DEF-003）。

呼叫 i18n_detector.detect_best_locale()（與 player_app.py:1093 相同入口），以替換
get_local_country_by_timezone 的方式控制時區層；db_path=None 使第 5 層 GeoIP 不啟用（需網路與 MMDB，本腳本不涵蓋）。
另記錄本機實際的時區名稱與 get_local_country_by_timezone() 的判定結果。

用法：python src/test/verify/verify_i18n_layers.py > <log>
"""
import sys
import time
import datetime
import traceback

from _common import print_header
import i18n_detector as det

JIMMY = ["de-DE", "en-US", "en", "es-US", "fr-FR", "hi", "id", "it", "ja", "ml", "nl-NL", "pl", "pt-BR", "uk"]

CASES = [
    # (案例, 預期層, 音軌, 系統語言, 歷史, 時區國碼, 預期 resolved_by, 預期音軌)
    ("L1 history ja", 1, JIMMY, ["fr-FR"], "ja", None, "EXPLICIT_HISTORY", "ja"),
    ("L2 OS exact fr-FR", 2, JIMMY, ["fr-FR"], None, None, "OS_LANGS_EXACT", "fr-FR"),
    ("L3 zh + tz TW", 3, ["zh-CN", "zh-TW", "en-US"], ["zh"], None, "TW", "TIMEZONE_CROSS", "zh-TW"),
    ("L3 zh + tz CN", 3, ["zh-CN", "zh-TW", "en-US"], ["zh"], None, "CN", "TIMEZONE_CROSS", "zh-CN"),
    ("L4 OS fuzzy en-GB", 4, JIMMY, ["en-GB"], None, None, "OS_LANGS_FUZZY", None),
    ("L6 smart default (ko-KR)", 6, JIMMY, ["ko-KR"], None, None, "DEFAULT_FALLBACK_SMART", "en-US"),
    ("L6 first track (ko-KR)", 6, ["ml", "uk"], ["ko-KR"], None, None, "DEFAULT_FALLBACK_FIRST_TRACK", "ml"),
    ("history not available -> L2", 2, JIMMY, ["it-IT", "it"], "ko", None, "OS_LANGS_EXACT", "it"),
]


def main():
    print_header(__file__, sys.argv)
    now = datetime.datetime.now()
    tzname = now.astimezone().tzinfo.tzname(now)
    print(f"[TZ] machine: datetime tzname={tzname!r}  time.tzname={time.tzname!r}  "
          f"utcoffset={now.astimezone().utcoffset()}")
    for langs in (["zh-TW"], ["en-US"]):
        print(f"     get_local_country_by_timezone({langs}) = {det.get_local_country_by_timezone(langs)!r}")

    real_tz = det.get_local_country_by_timezone
    fails = 0
    print("[L] case | expect layer | resolved_by | track | PASS/FAIL")
    for label, layer, tracks, langs, hist, tz, exp_by, exp_track in CASES:
        det.get_local_country_by_timezone = lambda _l=None, _tz=tz: _tz
        try:
            r = det.detect_best_locale(tracks, system_languages=langs, history_language=hist, db_path=None,
                                       ip_lock_mode=False)
            ok = r.resolved_by == exp_by and (exp_track is None or r.track_key == exp_track)
            print(f"    {label:30s} | L{layer} | {r.resolved_by:28s} | {r.track_key:6s} | {'PASS' if ok else 'FAIL'}")
        except Exception as e:
            ok = False
            print(f"    {label:30s} | L{layer} | EXCEPTION {type(e).__name__}: {e} | FAIL")
        fails += not ok
    det.get_local_country_by_timezone = real_tz

    print("[IP-LOCK] detect_best_locale(..., ip_lock_mode=True)  (DEF-003 reproduction)")
    try:
        r = det.detect_best_locale(JIMMY, system_languages=["zh-TW"], db_path=None, ip_lock_mode=True)
        print(f"    no exception: resolved_by={r.resolved_by} track={r.track_key}")
    except Exception as e:
        print(f"    EXCEPTION {type(e).__name__}: {e}")
        print("    " + traceback.format_exc().strip().splitlines()[-3].strip())
    print("[NOTE] layer 5 (GeoIP) not exercised: requires network + MMDB (db_path=None here)")
    print(f"[RESULT] six-layer chain {'PASS' if fails == 0 else f'FAIL ({fails})'}")


if __name__ == "__main__":
    main()
