"""펫 캐릭터 그리기.

캐릭터마다 클래스 하나가 draw(canvas, cx, top, tick, talking, blinking)로 한 프레임을 그린다.
cx, top은 머리 가운데와 꼭대기, tick은 50ms마다 1씩 느는 프레임 번호다.
새 캐릭터를 넣으려면 클래스를 만들어 CHARACTERS에 등록하면 설정 창에 나타난다.
"""
import math


def jelly_squeeze(p):
    """헤엄 주기 p(0~1)에서 갓을 오므린 정도(0~1). 앞 1/3 동안 재빨리 오므리고 나머지 동안 천천히 편다.
    양 끝에서 속도가 0으로 이어져 끊김 없이 되풀이된다."""
    p %= 1.0
    if p < 1 / 3.0:
        return (1 - math.cos(math.pi * p * 3)) / 2
    return (1 + math.cos(math.pi * (p - 1 / 3.0) * 1.5)) / 2


class Cat:
    name = "고양이"

    def draw(self, c, cx, top, tick, talking, blinking):
        if talking:   # 말하는 동안 통통 튄다
            top -= int(4 * abs(((tick % 12) - 6) / 6.0))
        outline, fill, ink = "#5b4636", "#ffd9a8", "#3a2a20"
        for sx in (-1, 1):   # 귀
            c.create_polygon(cx + sx * 30, top + 25, cx + sx * 62, top - 8, cx + sx * 66, top + 40,
                             fill=fill, outline=outline, width=3)
            c.create_polygon(cx + sx * 40, top + 25, cx + sx * 58, top + 5, cx + sx * 60, top + 32,
                             fill="#ffb0a8", outline="")
        c.create_oval(cx - 75, top, cx + 75, top + 125, fill=fill, outline=outline, width=3)   # 머리
        for sx in (-1, 1):   # 눈, 볼
            ex, ey = cx + sx * 30, top + 55
            if blinking:
                c.create_line(ex - 9, ey, ex + 9, ey, fill=ink, width=3, capstyle="round")
            else:
                c.create_oval(ex - 8, ey - 10, ex + 8, ey + 10, fill=ink, outline="")
                c.create_oval(ex - 3, ey - 6, ex + 1, ey - 2, fill="white", outline="")
            c.create_oval(ex - 22 if sx < 0 else ex + 8, ey + 12, ex - 8 if sx < 0 else ex + 22, ey + 24,
                          fill="#ffb0a8", outline="")
        c.create_oval(cx - 4, top + 68, cx + 4, top + 74, fill="#e07a7a", outline="")   # 코/입
        if talking and (tick // 3) % 2:
            c.create_oval(cx - 9, top + 78, cx + 9, top + 98, fill="#8a3b3b", outline=ink, width=2)
        else:
            c.create_arc(cx - 14, top + 66, cx, top + 90, start=200, extent=140, style="arc", outline=ink, width=2)
            c.create_arc(cx, top + 66, cx + 14, top + 90, start=200, extent=140, style="arc", outline=ink, width=2)
        for sx in (-1, 1):   # 수염
            for dy in (-4, 6):
                c.create_line(cx + sx * 45, top + 72 + dy, cx + sx * 78, top + 68 + dy * 2, fill=outline, width=2)


class Jelly:
    """분홍 해파리. 갓을 재빨리 오므려 쑥 떠오르고 천천히 펴며 내려앉기를 부드럽게 되풀이하고,
    그 사이에도 몸은 둥실거리고 촉수는 살랑인다."""
    name = "해파리"

    def __init__(self):
        self.swim = 0.0   # 헤엄 한 주기 중 어디쯤인지 (0~1)

    def draw(self, c, cx, top, tick, talking, blinking):
        outline, fill, ink = "#c23d7c", "#ffa8d2", "#3d1a2b"
        self.swim = (self.swim + (1 / 14.0 if talking else 1 / 32.0)) % 1   # 말할 때는 더 바쁘게 헤엄친다
        s = jelly_squeeze(self.swim)
        hw, bh, spread, seg = 76 - 12 * s, 64 + 10 * s, 1 - 0.7 * s, 9 + 2 * s
        top += 3 * math.sin(tick * 0.12) - 7 * jelly_squeeze(self.swim - 0.08)   # 몸은 모양보다 살짝 늦게 떠오른다
        rim = top + bh

        for i, ox in enumerate((-0.55, -0.2, 0.2, 0.55)):   # 촉수 (갓 뒤에 가려지도록 먼저)
            pts = []
            for j in range(6):
                k = j / 5.0
                sway = 7 * k * math.sin(tick * 0.22 + i * 1.7 + j * 0.9)
                pts += [cx + ox * hw + ox * 30 * spread * k + sway, rim - 6 + j * seg]
            c.create_line(pts, smooth=True, width=10, capstyle="round", fill=outline)
            c.create_line(pts, smooth=True, width=5, capstyle="round", fill="#ff8cc3" if i % 2 else "#ffc2e0")

        pts = []
        for i in range(17):                          # 둥근 갓
            a = math.pi * i / 16
            pts += [cx - hw * math.cos(a), rim - bh * math.sin(a) ** 0.8]
        n = 5
        for j in range(n):                           # 갓 아래 물결 테두리 (오른쪽 → 왼쪽)
            x0 = cx + hw - 2 * hw * j / n
            pts += [x0, rim, x0, rim, x0 - hw / n, rim + 12]
        pts += [cx - hw, rim, cx - hw, rim]
        c.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=3)

        c.create_arc(cx - hw + 12, top + 10, cx + hw - 12, 2 * rim - top - 10, start=112, extent=38,
                     style="arc", outline="#ffe6f2", width=5)                        # 반들반들 윤기
        for fx_, fy_, r in ((0.4, 0.26, 8), (0.12, 0.12, 5), (-0.18, 0.3, 4)):     # 동글동글 무늬
            x, y = cx + fx_ * hw, top + fy_ * bh
            c.create_oval(x - r, y - r * 0.8, x + r, y + r * 0.8, fill="#ff7ab8", outline="")

        a, r = 0.55, 12                               # 오른쪽 관자놀이에 꽂은 보라 꽃핀 (갓 테두리에 걸친다)
        x, y = cx + hw * math.cos(a) - 4, rim - bh * math.sin(a) ** 0.8
        petals = [(x + math.cos(t) * r * 0.62, y + math.sin(t) * r * 0.62)
                  for t in (0.3 + k * 2 * math.pi / 5 for k in range(5))]
        for grow, col in ((1.5, "#7b3fb5"), (0, "#b07ae6")):   # 진한 테두리를 먼저 깔고 꽃잎을 얹는다
            pr = r * 0.4 + grow
            for px, py in petals:
                c.create_oval(px - pr, py - pr, px + pr, py + pr, fill=col, outline="")
        c.create_oval(x - r * 0.28, y - r * 0.28, x + r * 0.28, y + r * 0.28, fill="#f3e2ff", outline="")

        # 얼굴도 갓을 따라 오므렸다 편다: 오므리면 눈 사이·볼·입이 모이고 눈은 세로로 길어지며,
        # 펴면 다시 벌어지고 동그래진다. 갓보다 살짝 늦게 따라와 말랑하게 출렁인다.
        f = jelly_squeeze(self.swim - 0.05)
        ey = rim - 27 - 6 * f
        erx, ery = 8 - 0.75 * f, 10 + 2 * f
        for sx in (-1, 1):   # 눈, 볼 (옆으로는 조금만 모여 얼굴 인상을 지킨다)
            ex = cx + sx * (26 - 2.5 * f)
            if blinking:
                c.create_line(ex - erx - 1, ey, ex + erx + 1, ey, fill=ink, width=3, capstyle="round")
            else:
                c.create_oval(ex - erx, ey - ery, ex + erx, ey + ery, fill=ink, outline="")
                c.create_oval(ex - erx / 2, ey - ery * 0.7, ex + erx / 8, ey - ery * 0.2, fill="white", outline="")
            chx, chw, chy = ex + sx * (8 - f), 8 - 1.25 * f, ey + ery
            c.create_oval(chx - chw, chy, chx + chw, chy + 7, fill="#ff6fa8", outline="")
        my, mw = rim - 10 - 4 * f, 8 - 1.5 * f
        if talking and (tick // 3) % 2:
            c.create_oval(cx - mw + 1, my - 6, cx + mw - 1, my + 8, fill="#8a2d4f", outline=ink, width=2)
        else:
            c.create_arc(cx - mw, my - 10, cx + mw, my + 4, start=200, extent=140, style="arc", outline=ink, width=2)


# 설정 파일에 저장하는 이름 → 캐릭터. 설정 창에는 이 순서대로 나온다.
CHARACTERS = {"cat": Cat, "jelly": Jelly}
