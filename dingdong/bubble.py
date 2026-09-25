"""펫 머리 위 말풍선 그리기."""
import math

from .effects import PARTY_COLORS, PARTY_INK


def draw_bubble(c, width, text, tick, age, special=False):
    """캔버스 위쪽(가로 width)에 말풍선을 그린다. age는 말풍선이 뜬 뒤 지난 프레임 수."""
    x0, y0, x1, y1 = 15, 10, width - 15, 150
    r = 18
    # 뜰 때 작게 시작해 통통 튀어나온다(5프레임). 글자는 거의 다 커진 뒤에 보여준다.
    k = min(1.0, (age + 1) / 5.0)
    scale = 1.0 if k >= 1 else 0.72 + 0.28 * k + 0.06 * math.sin(math.pi * k)
    ox, oy = width / 2.0, (y0 + y1) / 2.0
    # 특별 알림: 좌우로 흔들리고 테두리 색이 돌고 글자가 커졌다 작아진다
    wob = 5 * math.sin(tick * 0.55) if special else 0
    edge = PARTY_COLORS[(tick // 3) % len(PARTY_COLORS)] if special else "#5b4636"
    ink = PARTY_INK[(tick // 4) % len(PARTY_INK)] if special else "#3a2a20"
    font = ("맑은 고딕", 14 + (tick // 4) % 2 * 2, "bold") if special else ("맑은 고딕", 11, "bold")

    def sx_(x):
        return ox + (x - ox) * scale + wob

    def sy_(y):
        return oy + (y - oy) * scale

    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    c.create_polygon([sx_(v) if i % 2 == 0 else sy_(v) for i, v in enumerate(pts)],
                     smooth=True, fill="white", outline=edge, width=5 if special else 3)
    tx, ty = width // 2, y1
    c.create_polygon(sx_(tx - 14), sy_(ty - 1), sx_(tx + 14), sy_(ty - 1), sx_(tx), sy_(ty + 22),
                     fill="white", outline="")
    c.create_line(sx_(tx - 14), sy_(ty), sx_(tx), sy_(ty + 22), sx_(tx + 14), sy_(ty),
                  fill=edge, width=5 if special else 3)
    c.create_line(sx_(tx - 12), sy_(ty + 1), sx_(tx + 12), sy_(ty + 1), fill="white", width=5)
    if k > 0.7:
        c.create_text(width // 2 + wob, (y0 + y1) // 2, text=text, width=width - 60, justify="center",
                      font=font, fill=ink)
