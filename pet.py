"""딩동 펫 실행 파일. run.bat이 이 파일을 pythonw로 띄운다. 본체는 dingdong/ 폴더에 있다.

    pythonw pet.py          # 평소처럼 실행
    python pet.py --now     # 바로 한 번 나와서 말하기 (확인용)
"""
import ctypes
import sys

if sys.platform != "win32":
    sys.exit("Windows 전용 앱입니다.")

from dingdong.app import Pet


def main():
    # 한 번에 하나만 실행: 두 개가 뜨면 같은 시각에 같은 음성을 API로 두 번 만든다
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, "DingdongPet.SingleInstance")   # 핸들은 프로세스가 끝날 때 닫힌다
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        sys.exit(0)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    pet = Pet()
    if "--now" in sys.argv:
        pet.root.after(500, pet.pop)
    pet.root.mainloop()


if __name__ == "__main__":
    main()
