"""파일 위치, 기본 설정, 목소리 목록, 설정 파일 읽고 쓰기."""
import json
import os

from .characters import CHARACTERS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 앱 폴더 (pet.py가 있는 곳)
CONFIG = os.path.join(ROOT, "config.json")
KEY_FILE = os.path.join(ROOT, "tts_api_key.txt")
USAGE_FILE = os.path.join(ROOT, "usage.json")
CACHE_DIR = os.path.join(ROOT, "audio_cache")     # 이 컴퓨터에서 만든 음성
VOICE_PACK_DIR = os.path.join(ROOT, "voices")     # 함께 배포하는 '아케르나르' 음성. API 키 없이 바로 읽어준다

# 잊으면 안 되는 일: 정해진 요일·시각에 다른 설정을 모두 제치고 화려하게 알린다. (설정 창에서 켜고 끈다)
SPECIAL_WEEKDAY = 0                 # 0=월요일 ... 6=일요일
SPECIAL_AT = "10:55"
SPECIAL_TEXT = "무료음료창고 개방해 주세요 !!!"
SPECIAL_HOLD = 15                   # 화면에 붙잡아 두는 시간(초). 펫을 누르면 바로 닫힌다
SPECIAL_CATCHUP = 5                 # 절전 등으로 놓쳤어도 이 시간(분) 안에는 늦게라도 알린다
WEEKDAYS = "월화수목금토일"

# 여성 음성만. Chirp3 HD(최신 고품질) → Neural2 → WaveNet → Standard 순으로 자연스럽다.
_HD = [("아오이데", "Aoede"), ("코레", "Kore"), ("레다", "Leda"), ("제피르", "Zephyr"), ("아케르나르", "Achernar"),
       ("아우토노에", "Autonoe"), ("칼리로에", "Callirrhoe"), ("데스피나", "Despina"), ("에리노메", "Erinome"),
       ("가크룩스", "Gacrux"), ("라오메데이아", "Laomedeia"), ("풀케리마", "Pulcherrima"), ("술라파트", "Sulafat"),
       ("빈데미아트릭스", "Vindemiatrix")]
VOICES = {f"[HD] {ko}": f"google:ko-KR-Chirp3-HD-{en}" for ko, en in _HD}
VOICES.update({
    "[Neural2] A": "google:ko-KR-Neural2-A",
    "[Neural2] B": "google:ko-KR-Neural2-B",
    "[WaveNet] A": "google:ko-KR-Wavenet-A",
    "[WaveNet] B": "google:ko-KR-Wavenet-B",
    "[Standard] A (기본 품질)": "google:ko-KR-Standard-A",
    "[Standard] B (기본 품질)": "google:ko-KR-Standard-B",
    "[무료] 선희 (edge-tts)": "edge:ko-KR-SunHiNeural",
})
EDGE_FALLBACK = "edge:ko-KR-SunHiNeural"
PREVIEW_TEXT = "안녕하세요! 지금은 오후 3시 20분이에요. 오늘도 힘내봐요!"

DEFAULTS = {
    "character": "cat",
    "interval_min": 10, "speak": True,
    "voice": "google:ko-KR-Chirp3-HD-Achernar",   # 함께 온 음성이 있어 키 없이도 바로 읽어준다
    "sound": "", "messages": [],
    "api_from": "07:40", "api_to": "12:00",   # 이 시간대에만 새 '시각 멘트'를 API로 생성
    "monthly_char_limit": 50000,              # 한 달 API 글자 수 상한
    "silent": True,           # 무음 모드(기본값): 딩동·음성 없이 화면 효과로만 알린다
    "quiet_sec": 8,           # 소리 없이 알릴 때 말풍선을 띄워두는 시간(초)
    "fx_glow": True,          # 화면 테두리 번쩍이기
    "fx_sparkle": True,       # 펫 주변 반짝이
    "fx_hop": True,           # 말하는 동안 폴짝폴짝 뛰기
    "fx_gif": "",             # 펫 뒤에서 재생할 효과 GIF(선택)
    "pos": None,              # 끌어다 놓은 자리 [x, 그 모니터 작업 영역의 아래쪽 y]
    "special": False,         # 특별 알림 사용 (요일·시각·문구는 위의 SPECIAL_*)
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if cfg.get("voice") not in VOICES.values():   # 목록에서 빠진 음성(남성·Windows 등) → 기본 음성
        cfg["voice"] = DEFAULTS["voice"]
    if cfg.get("character") not in CHARACTERS:
        cfg["character"] = DEFAULTS["character"]
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def cfg_int(cfg, key, lo, hi):
    """설정 파일이 망가져 있어도 멈추지 않게, 범위 안의 정수로 맞춰 돌려준다."""
    try:
        return max(lo, min(hi, int(cfg[key])))
    except (KeyError, TypeError, ValueError):
        return DEFAULTS[key]
