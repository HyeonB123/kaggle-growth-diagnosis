"""프로젝트 차트 스타일 헬퍼 (폰트, 색, 범례 위치, 라벨 겹침 처리, 구간 음영).

노트북에서: from metakaggle import viz as vs; vs.setup()
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

PURPLE, BLUE, ORANGE, GRAY = "#6A55D0", "#2B78D6", "#E8912D", "#8C8C8C"
LAVENDER, SHADE, SHADE_GRAY = "#B8B0E2", "#EFEDF8", "#E4E4EC"
BG, INK, MUTED, GRID = "#FCFBF9", "#222222", "#8A8A95", "#E6E6EA"


def _register_bold():
    """matplotlib은 .ttc의 첫 굵기만 읽음 → Bold/SemiBold를 시스템 폰트에서 꺼내 ~/.cache에 저장 후 등록.
    macOS가 아니면(시스템 폰트 없음) 건너뛰고 다른 한글 폰트로 대체한다."""
    import os
    from matplotlib import font_manager as fm
    src = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
    if not os.path.exists(src):
        return False
    d = os.path.expanduser("~/.cache/metakaggle-fonts")       # 폰트 파일은 레포에 넣지 않음 (라이선스)
    os.makedirs(d, exist_ok=True)
    targets = {4: "AppleSDGothicNeo-SemiBold.ttf", 6: "AppleSDGothicNeo-Bold.ttf"}
    missing = [i for i, f in targets.items() if not os.path.exists(os.path.join(d, f))]
    if missing:
        from fontTools.ttLib import TTCollection
        c = TTCollection(src)
        for i in missing:
            c.fonts[i].save(os.path.join(d, targets[i]))
    for f in targets.values():
        fm.fontManager.addfont(os.path.join(d, f))
    return True


def setup():
    mac = _register_bold()
    plt.rcParams.update({
        "font.family": "Apple SD Gothic Neo" if mac else ["Malgun Gothic", "NanumGothic", "DejaVu Sans"], "axes.unicode_minus": False,
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.edgecolor": "#CFCFD6", "axes.linewidth": 1.0,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.major.size": 0, "ytick.major.size": 0,
        "axes.labelcolor": MUTED, "axes.labelsize": 10, "xtick.labelsize": 10, "ytick.labelsize": 10,
        "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.titlecolor": INK, "axes.titlepad": 30,
        "lines.linewidth": 2.5, "lines.markersize": 5,
        "legend.frameon": False, "legend.fontsize": 10,
    })


# ---------- 포맷 ----------
def fmt_man(v, d=1):
    return f"{v / 1e4:.{d}f}만" if abs(v) >= 1e4 else f"{v:,.0f}"

def fmt_pct(v, d=1):
    return f"{v * 100:.{d}f}%"

def fmt_won(v):
    return f"{v:,.0f}원"

def n_label(name, n):
    return f"{name} (n={n:,})"

def yfmt(ax, f):
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f(v)))


# ---------- 그리기 ----------
def line(ax, x, y, color, label=None, **kw):
    """선 + 흰 테두리 원형 마커. 점이 40개를 넘으면 markevery를 자동으로 듬성듬성(약 12개) 잡는다.
    특정 지점에만 찍으려면 markevery=[0, 7, 30, 90]처럼 인덱스 목록을 넘긴다 (라벨 다는 지점은 꼭 포함)."""
    n = len(y)
    if "markevery" not in kw and n > 40:
        kw["markevery"] = max(1, n // 12)
    kw.setdefault("marker", "o")
    kw.setdefault("lw", 2.5)
    return ax.plot(x, y, color=color, label=label, markeredgecolor="white",
                   markeredgewidth=1.0, zorder=3, **kw)[0]


def legend_top_right(ax, **kw):
    """범례: 차트 오른쪽 위, 가로 한 줄."""
    h, l = ax.get_legend_handles_labels()
    return ax.legend(h, l, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=len(l),
                     frameon=False, handlelength=1.8, columnspacing=1.6, borderaxespad=0.3, **kw)


def shade(ax, start, end, label=None, color=SHADE, pad=0.5, label_y=0.92, label_color=PURPLE):
    """구간 음영. 범주/정수 x면 pad=0.5로 막대 폭만큼, 날짜 x면 pad=0.5일."""
    if isinstance(start, (np.datetime64,)) or hasattr(start, "to_pydatetime"):
        import pandas as pd
        s, e = pd.Timestamp(start) - pd.Timedelta(days=pad), pd.Timestamp(end) + pd.Timedelta(days=pad)
    else:
        s, e = start - pad, end + pad
    ax.axvspan(s, e, color=color, zorder=0, lw=0)
    if label:
        mid = s + (e - s) / 2
        ax.text(mid, label_y, label, transform=ax.get_xaxis_transform(), ha="center", va="top",
                color=label_color, fontsize=10, fontweight="bold", zorder=4)


# ---------- 라벨 (겹침 방지) ----------
LABEL_BOX = dict(boxstyle="round,pad=0.15", fc=BG, ec="none")


def label_lines(ax, x, series, fmt=lambda v: f"{v:,.0f}", fontsize=9, every=1, offset=9):
    """series: [(y_values, color), ...]. 같은 x에서 위쪽 선은 위에, 아래쪽 선은 아래에 라벨."""
    _headroom(ax, 0.08)
    texts = []
    ys = [np.asarray(s[0], float) for s in series]
    for i in range(0, len(x), every):
        vals = [y[i] for y in ys]
        order = np.argsort(vals)  # 아래 → 위
        for rank, k in enumerate(order):
            above = rank == len(order) - 1 or (len(order) > 2 and rank > 0 and rank % 2 == 0)
            t = ax.annotate(fmt(vals[k]), (x[i], vals[k]), xytext=(0, offset if above else -offset),
                            textcoords="offset points", ha="center", va="bottom" if above else "top",
                            color=series[k][1], fontsize=fontsize, fontweight="bold", zorder=5,
                            bbox=LABEL_BOX)
            texts.append(t)
    resolve_overlaps(ax, texts)
    return texts


def _headroom(ax, frac=0.12):
    """라벨이 축 경계·위 패널에 닿지 않도록 위아래 여백 확보."""
    lo, hi = ax.get_ylim(); r = hi - lo
    ax.set_ylim(lo - (r * frac if lo != 0 else 0), hi + r * frac)


def label_bars(ax, bars, fmt=lambda v: f"{v:,.0f}", color=MUTED, fontsize=9, inside=False):
    if not inside:
        _headroom(ax)
    texts = []
    for b in bars:
        h = b.get_height()
        if inside:
            t = ax.text(b.get_x() + b.get_width() / 2, b.get_y() + h / 2, fmt(h), ha="center",
                        va="center", color="white", fontsize=fontsize, zorder=5)
        else:
            t = ax.annotate(fmt(h), (b.get_x() + b.get_width() / 2, b.get_y() + h), xytext=(0, 3),
                            textcoords="offset points", ha="center", va="bottom", color=color,
                            fontsize=fontsize, zorder=5, bbox=LABEL_BOX)
        texts.append(t)
    resolve_overlaps(ax, texts)
    return texts


def resolve_overlaps(ax, texts, step=3, max_iter=80):
    """라벨끼리, 라벨-마커, 라벨-다른 텍스트(음영 설명 등)가 겹치면 위아래로 밀어낸다.
    그린 뒤 이미지 직접 확인은 여전히 필수."""
    fig = ax.figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pts = [ax.transData.transform(ln.get_xydata())
           for ln in ax.get_lines()
           if ln.get_marker() not in (None, "None", "", " ") and len(ln.get_xdata())
           and ln.get_transform().contains_branch(ax.transData)]
    pts = np.vstack(pts) if pts else np.empty((0, 2))
    ids = {id(t) for t in texts}
    for _ in range(max_iter):
        obstacles = [o.get_window_extent(r).expanded(1.02, 1.05) for o in ax.texts if id(o) not in ids]
        boxes = [t.get_window_extent(r).expanded(1.05, 1.1) for t in texts]
        moved = False
        for i, t in enumerate(texts):
            bi = boxes[i]
            hit = any(bi.overlaps(boxes[j]) for j in range(len(texts)) if j != i) \
                or any(bi.overlaps(o) for o in obstacles)
            if not hit and len(pts):
                hit = np.any((pts[:, 0] > bi.x0 - 3) & (pts[:, 0] < bi.x1 + 3) &
                             (pts[:, 1] > bi.y0 - 3) & (pts[:, 1] < bi.y1 + 3))
            if hit and hasattr(t, "xyann"):
                dx, dy = t.xyann
                t.xyann = (dx, dy + (step if dy >= 0 else -step))
                moved = True
        if not moved:
            break
        fig.canvas.draw()


# ---------- 레이아웃 ----------
def stacked_panels(height_ratios=(2.2, 1), figsize=(13, 6.5)):
    """단위가 다른 두 지표: 위아래 패널 + x축 공유 (이중 축 대신 기본)."""
    fig, axes = plt.subplots(len(height_ratios), 1, figsize=figsize, sharex=True,
                             gridspec_kw={"height_ratios": height_ratios, "hspace": 0.12})
    return fig, axes


def panel_title(ax, text):
    """그룹 패널 소제목 (AOS / iOS 등)."""
    ax.text(0, 1.04, text, transform=ax.transAxes, fontsize=12, fontweight="bold", color=INK,
            ha="left", va="bottom")


def date_axis(ax, interval=3, fmt="%m/%d"):
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


# ---------- 자동 점검 ----------
def check_overlaps(fig, tol=1):
    """그림 안의 모든 텍스트(제목·범례·라벨·눈금)끼리, 텍스트-마커 겹침을 찾아 목록으로 반환.
    빈 리스트면 통과. 이미지를 눈으로 보기 전 1차 자동 검사용."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    items = []
    for ax in fig.axes:
        cands = list(ax.texts) + [ax.title, ax._left_title, ax._right_title]
        cands += [t for t in ax.get_xticklabels() + ax.get_yticklabels()]
        leg = ax.get_legend()
        if leg:
            cands += list(leg.get_texts())
        for t in cands:
            if t.get_visible() and t.get_text().strip():
                items.append((t.get_text().replace("\n", " ")[:20], t.get_window_extent(r).shrunk(0.98, 0.9)))
    if fig._suptitle is not None:
        items.append((fig._suptitle.get_text()[:20], fig._suptitle.get_window_extent(r)))
    problems = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][1], items[j][1]
            if a.x0 < b.x1 - tol and b.x0 < a.x1 - tol and a.y0 < b.y1 - tol and b.y0 < a.y1 - tol:
                problems.append(f"텍스트 겹침: '{items[i][0]}' ↔ '{items[j][0]}'")
    for ax in fig.axes:
        for ln in ax.get_lines():
            if ln.get_marker() in (None, "None", "", " ") or not ln.get_transform().contains_branch(ax.transData):
                continue
            xy = ax.transData.transform(ln.get_xydata())
            for name, bb in items:
                if np.any((xy[:, 0] > bb.x0 + 2) & (xy[:, 0] < bb.x1 - 2) & (xy[:, 1] > bb.y0 + 2) & (xy[:, 1] < bb.y1 - 2)):
                    problems.append(f"마커 위 텍스트: '{name}'")
    return problems


def contact_sheet(paths, out, cols=2, width=900):
    """여러 차트를 한 장으로 모아 한 번에 눈으로 확인."""
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    ims = [im.resize((width, int(im.height * width / im.width))) for im in ims]
    rows = (len(ims) + cols - 1) // cols
    hs = [max(im.height for im in ims[r * cols:(r + 1) * cols]) for r in range(rows)]
    sheet = Image.new("RGB", (cols * width, sum(hs)), "white")
    y = 0
    for r in range(rows):
        for c, im in enumerate(ims[r * cols:(r + 1) * cols]):
            sheet.paste(im, (c * width, y))
        y += hs[r]
    sheet.save(out)
    return out
