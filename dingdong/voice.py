"""딩동 소리 재생, 음성 합성(Google Cloud TTS / edge-tts)과 캐시, API 사용량.

한 번 만든 mp3는 audio_cache/ 에 저장해 재사용한다. voices/ 에는 함께 배포한 '아케르나르' 음성이 있어
키 없이도 찾아 쓴다. 파일 이름은 (목소리, 문장)의 해시라 두 폴더를 같은 방식으로 찾는다.
"""
import asyncio
import base64
import ctypes
import hashlib
import json
import os
import random
import threading
import time
import urllib.request
import winsound

from .config import CACHE_DIR, EDGE_FALLBACK, KEY_FILE, ROOT, USAGE_FILE, VOICE_PACK_DIR
from .phrases import MESSAGES, TIME_TEMPLATES, in_api_window, time_phrase


# ---------------- 딩동 소리 ----------------
def notification_sound(custom=""):
    """설정한 파일, 없으면 앱 폴더의 첫 mp3. 둘 다 없으면 None(딩동 없이 진행)."""
    if custom and os.path.exists(custom):
        return custom
    for name in sorted(os.listdir(ROOT)):
        if name.lower().endswith(".mp3"):
            return os.path.join(ROOT, name)
    return None


def play_sound(path, alias="dd"):
    """mp3/wav를 끝까지 재생(MCI, 추가 설치 불필요)."""
    if path.lower().endswith(".wav"):
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    mci = ctypes.windll.winmm.mciSendStringW
    mci(f'close {alias}', None, 0, 0)
    if mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, 0) == 0:
        mci(f'play {alias} wait', None, 0, 0)
        mci(f'close {alias}', None, 0, 0)


# ---------------- API 키 / 사용량 ----------------
def api_key():
    k = os.environ.get("GOOGLE_TTS_KEY", "").strip()
    if k:
        return k
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_api_key(k):
    try:
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(k)
    except OSError:
        pass


def load_usage():
    month = time.strftime("%Y-%m")
    try:
        with open(USAGE_FILE, encoding="utf-8") as f:
            u = json.load(f)
        if u.get("month") == month:
            return u
    except (OSError, ValueError):
        pass
    return {"month": month, "chars": 0, "calls": 0}


def add_usage(chars):
    u = load_usage()
    u["chars"] += chars
    u["calls"] += 1
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(u, f)
    except OSError:
        pass


# ---------------- 음성 캐시 ----------------
def clip_name(spec, text):
    return hashlib.sha1(f"{spec}|{text}".encode("utf-8")).hexdigest()[:20] + ".mp3"


def _ready(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def cached_clip(spec, text):
    """이미 있는 mp3 경로(직접 만든 음성 → 함께 온 음성 순). 없으면 None."""
    name = clip_name(spec, text)
    for folder in (CACHE_DIR, VOICE_PACK_DIR):
        path = os.path.join(folder, name)
        if _ready(path):
            return path
    return None


def saved_counts():
    """(이 컴퓨터에서 만든 음성 수, 함께 온 음성 수)"""
    return tuple(len(os.listdir(d)) if os.path.isdir(d) else 0 for d in (CACHE_DIR, VOICE_PACK_DIR))


# ---------------- 합성 ----------------
def google_synth(text, voice, path):
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR", "name": voice},
        "audioConfig": {"audioEncoding": "MP3"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key()}",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        audio = base64.b64decode(json.load(r)["audioContent"])
    with open(path, "wb") as f:
        f.write(audio)


def edge_synth(text, voice, path):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice).save(path))


_gen_lock = threading.Lock()


def get_clip(text, spec, cfg, allow_new=True):
    """text를 읽는 mp3 경로를 반환. 저장된 것이 있으면 재사용, 없으면 allow_new일 때만 생성. 실패 시 None."""
    found = cached_clip(spec, text)
    if found or not allow_new:
        return found
    path = os.path.join(CACHE_DIR, clip_name(spec, text))
    kind, _, voice = spec.partition(":")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with _gen_lock:   # 미리 생성·알림·미리 듣기가 겹쳐도 같은 문장을 두 번 만들지 않는다
        if _ready(path):
            return path
        tmp = path + ".part"   # 다 받은 뒤에만 캐시에 넣어, 반쯤 쓰인 파일을 재생하지 않게
        try:
            if kind == "google":
                if not api_key() or load_usage()["chars"] + len(text) > cfg["monthly_char_limit"]:
                    return None
                google_synth(text, voice, tmp)
                add_usage(len(text))
            else:
                edge_synth(text, voice, tmp)
            os.replace(tmp, path)
            return path
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            return None


def prefetch_todo(cfg):
    """API 시간대의 모든 시각×문구 + 응원 문구 중 아직 저장되지 않은 문장 목록."""
    spec = cfg["voice"]
    jobs = []
    for minute in range(0, 24 * 60, cfg["interval_min"]):
        if in_api_window(cfg, minute):
            jobs += [time_phrase(minute // 60, minute % 60, t) for t in TIME_TEMPLATES]
    jobs += cfg["messages"] or MESSAGES
    return [t for t in dict.fromkeys(jobs) if not cached_clip(spec, t)]


def prefetch(cfg):
    """저장 안 된 문장을 미리 만들어 캐시. (생성 개수, 실패 개수) 반환."""
    spec = cfg["voice"]
    made = failed = 0
    for text in prefetch_todo(cfg):
        if get_clip(text, spec, cfg):
            made += 1
        else:
            failed += 1
            if failed >= 3:      # 계속 실패하면 중단(키/한도/네트워크 문제)
                break
    return made, failed


# ---------------- 알림 때 읽을 음성 고르기 ----------------
def pick_time_clip(cfg, lt, force=False):
    """이 시각의 문구를 고르고 (문구, mp3 경로 또는 None, 실제로 쓴 음성)을 반환.
    force: 설정 창에서 직접 부를 때. 생성 시간대 밖이어도 고른 목소리로 만든다."""
    spec = cfg["voice"]
    texts = [time_phrase(lt.tm_hour, lt.tm_min, t) for t in random.sample(TIME_TEMPLATES, len(TIME_TEMPLATES))]
    minute = lt.tm_hour * 60 + lt.tm_min
    allow_api = force or not spec.startswith("google") or in_api_window(cfg, minute)
    on_slot = allow_api and not minute % cfg["interval_min"]
    if on_slot:   # 정해진 알림 시각에는 무작위 문구를 그대로 써서 다양성을 유지
        p = get_clip(texts[0], spec, cfg)
        if p:
            return texts[0], p, spec
    # 시간대 밖이거나, 정해진 알림 시각이 아닐 때(펫 클릭·펫 불러보기 등), 키가 없어 새로 못 만들었을 때:
    # 이 시각에 이미 만든 문구가 있으면 재사용한다. 한 번 쓰고 말 음성을 문구마다 새로 만들지 않도록.
    for text in texts:
        p = get_clip(text, spec, cfg, allow_new=False)
        if p:
            return text, p, spec
    if allow_api and not on_slot:
        p = get_clip(texts[0], spec, cfg)
        if p:
            return texts[0], p, spec
    return texts[0], get_clip(texts[0], EDGE_FALLBACK, cfg), EDGE_FALLBACK


def prepare_clips(cfg, lt, msg, force=False):
    """시각 멘트와 응원 문구를 같은 목소리로 준비. 한쪽이라도 대체 음성이면 둘 다 대체 음성으로 맞춘다.
    (시각 멘트 문구, 재생할 mp3 목록) 반환."""
    ttext, tclip, used = pick_time_clip(cfg, lt, force)
    mclip = get_clip(msg, used, cfg)
    if not mclip and used != EDGE_FALLBACK:
        used = EDGE_FALLBACK
        tclip, mclip = get_clip(ttext, used, cfg), get_clip(msg, used, cfg)
    return ttext, [c for c in (tclip, mclip) if c]
