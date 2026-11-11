# -*- coding: utf-8 -*-
"""Генератор односторонньої плати під ЛУТ: ESP32 DevKit V1 (30 ніжок) + DFPlayer Mini + шилд 18650 V3.
Варіант проєкту «Двері» з Telegram. Зроблено на основі генератора плати BlackPill.
Координати — мм, вид З БОКУ ДЕТАЛЕЙ (крізь плату), x вправо, y вниз.
Запуск:  python gen_pcb_esp32.py
"""
import math, itertools, os

# ---------------- ПАРАМЕТРИ (звір штангенциркулем зі своїми модулями) ----------------
BOARD_W, BOARD_H = 100.0, 95.0
P = 2.54
BP_X0, BP_YT = 5.0, 39.0          # перший пін верхнього ряду ESP32 (VIN, біля USB)
BP_ROW = 25.4                     # відстань між рядами ESP32 — ОБОВ'ЯЗКОВО ЗВІР: буває 22.86 / 25.4 / 27.94
BP_BRK = 3.5                      # відступ дублюючих площадок від пінів
DF_X0, DF_YT = 80.0, 40.0         # перший пін верхнього ряду DFPlayer (BUSY)
DF_ROW = 17.78                    # відстань між рядами DFPlayer Mini
SH_Y = 28.0                       # ряд площадок 5V/GND шилда 18650
SH_EDGE = 30.0                    # нижній край шилда (зона y = 1..30)
PAD_M, HOLE_M = 1.9, 0.7          # площадки модулів / мітка свердління
PAD_C, HOLE_C = 2.3, 0.8          # площадки дискретних деталей
W_SIG, W_PWR = 0.8, 1.0
CLEAR_MIN = 0.5

# ESP32 DevKit V1, 30 ніжок, USB ліворуч, антена праворуч, вид згори
BP_TOP = ["VIN", "GND", "D13", "D12", "D14", "D27", "D26", "D25", "D33", "D32",
          "D35", "D34", "VN", "VP", "EN"]
BP_BOT = ["3V3", "GND", "D15", "D2", "D4", "RX2", "TX2", "D5", "D18", "D19",
          "D21", "RX0", "TX0", "D22", "D23"]
WIRE = {}   # усі датчики тепер мають свої групи площадок, дроти до ніжок модуля не потрібні
DF_TOP = ["BUSY", "USB-", "USB+", "ADKEY2", "ADKEY1", "IO2", "GND", "IO1"]
DF_BOT = ["VCC", "RX", "TX", "DAC_R", "DAC_L", "SPK1", "GND", "SPK2"]

pads = []    # dict(x,y,d,hole,net,label)
segs = []    # dict(x1,y1,x2,y2,w,net)


def pad(x, y, net, d=PAD_M, hole=HOLE_M, label=""):
    pads.append(dict(x=x, y=y, d=d, hole=hole, net=net, label=label))


def track(net, w, *pts):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        segs.append(dict(x1=x1, y1=y1, x2=x2, y2=y2, w=w, net=net))


# ---------------- ESP32 DevKit ----------------
BP_YB = BP_YT + BP_ROW
BRK_T, BRK_B = BP_YT - BP_BRK, BP_YB + BP_BRK
bp = {}
# Піни підібрано так, щоб усе розвелось на одному шарі без перемичок:
# MP3 — GPIO23/22 (правий край нижнього ряду), датчики — лівіша частина нижнього ряду,
# BUSY — VP (GPIO36), аналоговий датчик — D34 (GPIO34) доріжкою по лівому краю плати.
NETMAP_BOT = {"D23": "TX", "D22": "RX", "3V3": "V3", "D15": "RTX", "D4": "RRX", "RX2": "ROUT",
              "TX2": "SW", "D5": "SDA", "D18": "SCL", "D19": "ARM"}
NETMAP_TOP = {"VIN": "+5V", "GND": "GND", "VP": "BUSY", "D34": "ANA"}
for i, n in enumerate(BP_TOP):
    x = BP_X0 + i * P
    net = NETMAP_TOP.get(n, "bpT_" + n)
    pad(x, BP_YT, net, label=n); pad(x, BRK_T, net)
    track(net, W_SIG, (x, BP_YT), (x, BRK_T))
    bp["T_" + n] = x
for i, n in enumerate(BP_BOT):
    x = BP_X0 + i * P
    net = NETMAP_BOT.get(n, "bpB_" + n)
    pad(x, BP_YB, net, label=n); pad(x, BRK_B, net)
    track(net, W_SIG, (x, BP_YB), (x, BRK_B))
    bp["B_" + n] = x

# ---------------- DFPlayer Mini (SD-слот до правого краю) ----------------
DF_YB = DF_YT + DF_ROW
df = {}
DFNET = {"BUSY": "BUSY", "VCC": "+5V", "RX": "TXR", "TX": "RX", "SPK1": "SPK1", "SPK2": "SPK2", "GND": "GND"}
for i, n in enumerate(DF_TOP):
    x = DF_X0 + i * P
    pad(x, DF_YT, DFNET.get(n, "dfT_" + n), label=n); df["T_" + n] = x
for i, n in enumerate(DF_BOT):
    x = DF_X0 + i * P
    pad(x, DF_YB, DFNET.get(n, "dfB_" + n), label=n); df["B_" + n] = x

# ---------------- дискретні деталі ----------------
xG = df["T_GND"]                       # 95.24
xS5 = DF_X0 + P                        # площадки шилда: 5V зліва, GND справа
xSG = xS5 + P
pad(xS5, SH_Y, "VSH", PAD_M, HOLE_C, "5V"); pad(xSG, SH_Y, "GND", PAD_M, HOLE_C, "GND")
D1X, D1A, D1K = 75.5, 44.0, 54.16     # діод Шотткі (анод зверху — від шилда)
pad(D1X, D1A, "VSH", PAD_C, HOLE_C, "D1 A"); pad(D1X, D1K, "+5V", PAD_C, HOLE_C, "D1 K")
Y_GND, Y_5 = 49.08, D1K                # живлення йде між рядами ESP32 (під модулем)
C1X = 62.0                             # електроліт 470 мкФ, крок 5.08
pad(C1X, Y_GND, "GND", PAD_C, HOLE_C, "C1-"); pad(C1X, Y_5, "+5V", PAD_C, HOLE_C, "C1+")
Y_TX, Y_RX = BRK_B + 2.1, BRK_B + 4.7  # дві шини під нижнім рядом ESP32
R1A, R1B = 50.0, 60.16                 # резистор 1 кОм у лінії TX, крок 10.16
pad(R1A, Y_TX, "TX", PAD_C, HOLE_C, "R1"); pad(R1B, Y_TX, "TXR", PAD_C, HOLE_C, "R1")
SPKY = 62.5
pad(df["B_SPK1"], SPKY, "SPK1", 2.6, 1.2, "SPK"); pad(df["B_SPK2"], SPKY, "SPK2", 2.6, 1.2, "SPK")   # клемник 5.08, 2 контакти

# ---------------- доріжки ----------------
# шилд -> D1
track("VSH", W_PWR, (xS5, SH_Y), (xS5, 36.6), (D1X, 36.6), (D1X, D1A))
# +5V: D1 -> DFPlayer VCC; D1 -> C1+ -> між рядами ESP32 -> VIN
track("+5V", W_PWR, (D1X, D1K), (D1X, DF_YB), (df["B_VCC"], DF_YB))
track("+5V", W_PWR, (D1X, Y_5), (bp["T_VIN"], Y_5), (bp["T_VIN"], BP_YT))
# GND: шилд -> DFPlayer -> під діодом D1 -> C1- -> між рядами ESP32 -> GND
track("GND", W_PWR, (xSG, SH_Y), (xSG, 31.5), (xG, 31.5), (xG, DF_YT), (xG, DF_YB))
track("GND", W_PWR, (xG, Y_GND), (bp["T_GND"], Y_GND), (bp["T_GND"], BP_YT))
# TX (GPIO23 -> R1 -> DFPlayer RX)
track("TX", W_SIG, (bp["B_D23"], BRK_B), (bp["B_D23"], Y_TX), (R1A, Y_TX))
track("TXR", W_SIG, (R1B, Y_TX), (df["B_RX"], Y_TX), (df["B_RX"], DF_YB))
# RX (GPIO22 <- DFPlayer TX)
track("RX", W_SIG, (bp["B_D22"], BRK_B), (bp["B_D22"], Y_RX), (df["B_TX"], Y_RX), (df["B_TX"], DF_YB))
# BUSY -> VP / GPIO36 (під діодом D1)
track("BUSY", W_SIG, (df["T_BUSY"], DF_YT), (df["T_BUSY"], 46.2), (72.5, 46.2), (72.5, 33.2),
      (bp["T_VP"], 33.2), (bp["T_VP"], BRK_T))
# динамік
track("SPK1", W_SIG, (df["B_SPK1"], DF_YB), (df["B_SPK1"], SPKY))
track("SPK2", W_SIG, (df["B_SPK2"], DF_YB), (df["B_SPK2"], SPKY))

# ---------------- ряд гвинтових клемників на нижньому краю ----------------
# Клемники KF301 / DG301 з кроком 5.08 мм стикуються впритул: 3 + 5 + 3 + 4 + 2 контакти.
# Над рядом — сигнальні «смуги» (що лівіша ніжка-джерело, то нижча смуга, тому вони не перетинаються).
# Під рядом, біля самого краю, — шина GND (приходить від плеєра правим краєм) і відрізки 3,3 В,
# які пірнають між площадками клем: при кроку 5.08 між ними проходить доріжка 0.8 мм.
TB_P = 5.08
PAD_T, HOLE_T = 2.6, 1.2
TB_X0 = 7.5
Y_ROW = BOARD_H - 5.1
ROW = [  # (блок, підпис контакту, коло) — зліва направо
    ("ХОЛЛ", "GND", "GND"), ("ХОЛЛ", "VCC", "V3"), ("ХОЛЛ", "OUT", "ANA"),
    ("РАДАР", "5V", "+5V"), ("РАДАР", "TX", "RTX"), ("РАДАР", "RX", "RRX"), ("РАДАР", "OUT", "ROUT"),
    ("РАДАР", "GND", "GND"),
    ("SW-420", "GND", "GND"), ("SW-420", "VCC", "V3"), ("SW-420", "DO", "SW"),
    ("ADXL345", "VCC", "V3"), ("ADXL345", "SDA", "SDA"), ("ADXL345", "SCL", "SCL"), ("ADXL345", "GND", "GND"),
    ("ЗАЧИНЕНО", "SIG", "ARM"), ("ЗАЧИНЕНО", "GND", "GND")]
tx = [TB_X0 + i * TB_P for i in range(len(ROW))]
for (blk, lab, net), x in zip(ROW, tx):
    pad(x, Y_ROW, net, PAD_T, HOLE_T, lab)
LV0, LVP = Y_ROW - 2.4, 1.45              # рівень найнижчої смуги і крок смуг
Y_B1, Y_B2 = Y_ROW + 2.4, Y_ROW + 3.9      # під рядом: відрізки 3,3 В і шина GND


def lv(k):
    return LV0 - k * LVP


def between(i):                                # середина проміжку між клемами i та i+1
    return (tx[i] + tx[i + 1]) / 2


# аналоговий датчик: D34 угору, лівим краєм плати вниз (найнижча смуга) -> ХОЛЛ OUT
X_ANA, X_P5, Y_ANA_TOP = 1.1, 2.7, 31.6
track("ANA", W_SIG, (bp["T_D34"], BRK_T), (bp["T_D34"], Y_ANA_TOP), (X_ANA, Y_ANA_TOP), (X_ANA, lv(0)),
      (tx[2], lv(0)), (tx[2], Y_ROW))
# 5 В для радара: від шини +5V під модулем, лівим краєм униз
track("+5V", W_PWR, (bp["T_VIN"], Y_5), (X_P5, Y_5), (X_P5, lv(1)), (tx[3], lv(1)), (tx[3], Y_ROW))
# 3,3 В: від ніжки 3V3 до проміжку між «5V» і «TX» радара, крізь ряд униз;
# під рядом ліворуч до ХОЛЛ VCC і праворуч до проміжку перед «GND» радара, там угору,
# над двома клемами GND до SW-420 VCC, знову під рядом до ADXL345 VCC
g1, g2 = between(3), between(6)
track("V3", W_SIG, (bp["B_3V3"], BRK_B), (bp["B_3V3"], lv(2)), (g1, lv(2)), (g1, Y_B1))
track("V3", W_SIG, (tx[1], Y_ROW), (tx[1], Y_B1), (g2, Y_B1), (g2, lv(0)), (tx[9], lv(0)), (tx[9], Y_ROW),
      (tx[9], Y_B1), (tx[11], Y_B1), (tx[11], Y_ROW))
# сигнали з нижнього ряду ESP32
SIG = [("RTX", "B_D15", 4), ("RRX", "B_D4", 5), ("ROUT", "B_RX2", 6), ("SW", "B_TX2", 10),
       ("SDA", "B_D5", 12), ("SCL", "B_D18", 13), ("ARM", "B_D19", 15)]
for k, (net, key, i) in enumerate(SIG):
    track(net, W_SIG, (bp[key], BRK_B), (bp[key], lv(3 + k)), (tx[i], lv(3 + k)), (tx[i], Y_ROW))
# GND: від плеєра правим краєм до шини під рядом клем
X_GR = 92.4
track("GND", W_PWR, (xG, DF_YB), (xG, 65.5), (X_GR, 65.5), (X_GR, Y_B2), (tx[0], Y_B2))
for (blk, lab, net), x in zip(ROW, tx):
    if net == "GND":
        track("GND", W_PWR, (x, Y_B2), (x, Y_ROW))

# кріпильні отвори плати (М3)
MOUNT = [(3.5, 3.5), (96.5, 3.5), (3.5, BOARD_H - 3.5), (96.5, BOARD_H - 3.5)]
for k, (x, y) in enumerate(MOUNT):
    pad(x, y, "mnt%d" % k, 4.4, 1.0, "")

# ---------------- ПЕРЕВІРКИ ----------------
def d_pt_seg(px, py, s):
    x1, y1, x2, y2 = s["x1"], s["y1"], s["x2"], s["y2"]
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def seg_cross(a, b):
    def o(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    d1 = o(a["x1"], a["y1"], a["x2"], a["y2"], b["x1"], b["y1"])
    d2 = o(a["x1"], a["y1"], a["x2"], a["y2"], b["x2"], b["y2"])
    d3 = o(b["x1"], b["y1"], b["x2"], b["y2"], a["x1"], a["y1"])
    d4 = o(b["x1"], b["y1"], b["x2"], b["y2"], a["x2"], a["y2"])
    return d1 * d2 < 0 and d3 * d4 < 0


def d_seg_seg(a, b):
    if seg_cross(a, b):
        return 0.0
    return min(d_pt_seg(a["x1"], a["y1"], b), d_pt_seg(a["x2"], a["y2"], b),
               d_pt_seg(b["x1"], b["y1"], a), d_pt_seg(b["x2"], b["y2"], a))


def gap(a, b):
    """зазор мідь-мідь між двома примітивами"""
    if "d" in a and "d" in b:
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) - a["d"] / 2 - b["d"] / 2
    if "d" in a:
        return d_pt_seg(a["x"], a["y"], b) - a["d"] / 2 - b["w"] / 2
    if "d" in b:
        return gap(b, a)
    return d_seg_seg(a, b) - a["w"] / 2 - b["w"] / 2


prims = pads + segs
errors, worst = [], (99, None, None)
for a, b in itertools.combinations(prims, 2):
    if a["net"] != b["net"]:
        g = gap(a, b)
        if g < worst[0]:
            worst = (g, a, b)
        if g < CLEAR_MIN - 1e-6:
            errors.append("ЗАЗОР %.2f мм: %s / %s  %s | %s" % (g, a["net"], b["net"], a, b))
# зв'язність кожного кола
parent = list(range(len(prims)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
for i, j in itertools.combinations(range(len(prims)), 2):
    if prims[i]["net"] == prims[j]["net"] and gap(prims[i], prims[j]) < -0.05:
        parent[find(i)] = find(j)
nets = {}
for i, p in enumerate(prims):
    nets.setdefault(p["net"], set()).add(find(i))
EXPECT = {}
for n, comps in nets.items():
    if len(comps) != EXPECT.get(n, 1):
        errors.append("КОЛО %s: %d острівців (очікується %d)" % (n, len(comps), EXPECT.get(n, 1)))
# все в межах плати
for p in prims:
    xs = [p["x"]] if "d" in p else [p["x1"], p["x2"]]
    ys = [p["y"]] if "d" in p else [p["y1"], p["y2"]]
    r = p.get("d", p.get("w", 0)) / 2
    if min(xs) - r < 0.6 or max(xs) + r > BOARD_W - 0.6 or min(ys) - r < 0.6 or max(ys) + r > BOARD_H - 0.6:
        errors.append("ЗА КРАЄМ: %s" % p)
print("Найменший зазор між різними колами: %.2f мм (%s / %s)" % (worst[0], worst[1]["net"], worst[2]["net"]))
print("Кіл з доріжками:", sorted(n for n in nets if not n.startswith(("bp", "df", "mnt", "shm"))))
if errors:
    print("\n".join(errors)); raise SystemExit("ПОМИЛКИ ТРАСУВАННЯ")
print("Перевірки пройдено: перетинів немає, зазори >= %.1f мм, усі кола з'єднані." % CLEAR_MIN)

OUT = os.path.dirname(os.path.abspath(__file__))
LABEL = "ESP32+DF 18650"

# ---------------- SVG: мідь ----------------
def copper_svg(color="#000", hole="#fff", with_text=True):
    o = []
    for s in segs:
        o.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="%s" stroke-width="%.2f" stroke-linecap="round"/>'
                 % (s["x1"], s["y1"], s["x2"], s["y2"], color, s["w"]))
    for p in pads:
        o.append('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="%s"/>' % (p["x"], p["y"], p["d"] / 2, color))
    for p in pads:
        o.append('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="%s"/>' % (p["x"], p["y"], p["hole"] / 2, hole))
    o.append('<rect x="0.15" y="0.15" width="%.2f" height="%.2f" fill="none" stroke="%s" stroke-width="0.3"/>'
             % (BOARD_W - 0.3, BOARD_H - 0.3, color))
    if with_text:  # дзеркальний напис: на міді читатиметься нормально
        o.append('<text transform="translate(60,17) scale(-1,1)" font-family="Arial,Helvetica,sans-serif" '
                 'font-weight="bold" font-size="6" fill="%s">%s</text>' % (color, LABEL))
    return "\n".join(o)


M = 10
svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" viewBox="%g %g %g %g">'
       % (BOARD_W + 2 * M, BOARD_H + 2 * M + 8, -M, -M, BOARD_W + 2 * M, BOARD_H + 2 * M + 8),
       '<rect x="%g" y="%g" width="%g" height="%g" fill="#fff"/>' % (-M, -M, BOARD_W + 2 * M, BOARD_H + 2 * M + 8),
       copper_svg(),
       '<line x1="0" y1="%g" x2="50" y2="%g" stroke="#000" stroke-width="0.3"/>' % (BOARD_H + 6, BOARD_H + 6)]
for t in range(0, 51, 10):
    svg.append('<line x1="%d" y1="%g" x2="%d" y2="%g" stroke="#000" stroke-width="0.3"/>' % (t, BOARD_H + 4, t, BOARD_H + 8))
svg.append('<text x="53" y="%g" font-family="Arial" font-size="3">50 mm | 100%% | NE DZERKALYTY</text>' % (BOARD_H + 7))
svg.append("</svg>")
open(os.path.join(OUT, "esp32_pcb_copper_print.svg"), "w", encoding="utf-8").write("\n".join(svg))

# ---------------- SVG: складальне креслення (вид з боку деталей) ----------------
def T(x, y, s, size=1.6, anchor="middle", rot=0, fill="#123", bold=False):
    tr = ' transform="rotate(%g %.2f %.2f)"' % (rot, x, y) if rot else ""
    return ('<text x="%.2f" y="%.2f" font-family="Arial,sans-serif" font-size="%g" text-anchor="%s" fill="%s"%s%s>%s</text>'
            % (x, y, size, anchor, fill, ' font-weight="bold"' if bold else "", tr, s))


a = ['<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" viewBox="-6 -8 %g %g">'
     % ((BOARD_W + 12) * 2.2, (BOARD_H + 17) * 2.2, BOARD_W + 12, BOARD_H + 17),
     '<rect x="-6" y="-8" width="%g" height="%g" fill="#fff"/>' % (BOARD_W + 12, BOARD_H + 17),
     '<rect x="0" y="0" width="%g" height="%g" fill="#f4efdc" stroke="#333" stroke-width="0.3"/>' % (BOARD_W, BOARD_H),
     copper_svg("#d9a441", "#fff", with_text=False)]
# шилд
a.append('<rect x="1" y="1" width="98" height="%g" fill="#2b6cb0" fill-opacity="0.13" stroke="#2b6cb0" stroke-width="0.35" stroke-dasharray="1.5 1"/>' % (SH_EDGE - 1))
a.append(T(50, 13, "Шилд 18650 V3 (плата ≈98×29 мм) — USB-A ліворуч, край «5V / GND» донизу", 2.0, fill="#2b6cb0", bold=True))
a.append(T(50, 17.5, "три пари 5V/GND шилда стають на три пари площадок; живлення береться з правої", 1.8, fill="#2b6cb0"))
a.append(T(xS5 - 1.8, SH_Y + 0.6, "5V", 1.8, "end", fill="#c00", bold=True))
a.append(T(xSG + 1.8, SH_Y + 0.6, "GND", 1.8, "start", fill="#000", bold=True))
# ESP32 DevKit
bx0, bx1 = BP_X0 - 7.0, BP_X0 + (len(BP_TOP) - 1) * P + 9.0
a.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#222" fill-opacity="0.10" stroke="#222" stroke-width="0.35"/>'
         % (bx0, BP_YT - 2.8, bx1 - bx0, BP_ROW + 5.6))
a.append('<rect x="%.2f" y="%.2f" width="7" height="9" fill="#999" stroke="#222" stroke-width="0.3"/>' % (bx0 - 1.2, (BP_YT + BP_YB) / 2 - 4.5))
a.append(T(bx0 + 3, (BP_YT + BP_YB) / 2 - 5.5, "USB", 1.6, "middle"))
a.append(T(bx1 - 4, (BP_YT + BP_YB) / 2 - 8, "антена", 1.6, "middle"))
a.append(T(30, BP_YT + 6.5, "ESP32 DevKit V1 (30 ніжок)", 2.0, bold=True))
for i, n in enumerate(BP_TOP):
    x = BP_X0 + i * P
    hl = n in NETMAP_TOP
    a.append(T(x + 0.55, BP_YT + 1.6, n, 1.5, "end", -90, "#c00" if hl else "#06c" if n in WIRE else "#123", hl or n in WIRE))
for i, n in enumerate(BP_BOT):
    x = BP_X0 + i * P
    hl = n in NETMAP_BOT
    a.append(T(x + 0.55, BP_YB - 1.6, n, 1.5, "start", -90, "#c00" if hl else "#06c" if n in WIRE else "#123", hl or n in WIRE))
# DFPlayer
dx0 = DF_X0 - 1.1
a.append('<rect x="%.2f" y="%.2f" width="20" height="20" fill="#0a7" fill-opacity="0.12" stroke="#075" stroke-width="0.35"/>' % (dx0, DF_YT - 1.1))
a.append('<rect x="%.2f" y="%.2f" width="6" height="12" fill="#999" stroke="#075" stroke-width="0.3"/>' % (dx0 + 14, DF_YT + 2.9))
a.append(T(dx0 + 17, DF_YT + 9.6, "SD", 1.6))
a.append(T(dx0 + 7.5, DF_YT + 10.5, "DFPlayer", 2.2, fill="#075", bold=True))
a.append(T(dx0 + 7.5, DF_YT + 13, "Mini", 2.2, fill="#075", bold=True))
for i, n in enumerate(DF_TOP):
    hl = n in ("BUSY", "GND")
    a.append(T(DF_X0 + i * P + 0.5, DF_YT + 1.5, n, 1.2, "end", -90, "#c00" if hl else "#123", hl))
for i, n in enumerate(DF_BOT):
    hl = n in DFNET
    a.append(T(DF_X0 + i * P + 0.5, DF_YB - 1.5, n, 1.2, "start", -90, "#c00" if hl else "#123", hl))
# D1
a.append('<rect x="%.2f" y="%.2f" width="2.8" height="5.2" fill="#444" stroke="#000" stroke-width="0.2"/>' % (D1X - 1.4, (D1A + D1K) / 2 - 2.6))
a.append('<rect x="%.2f" y="%.2f" width="2.8" height="0.9" fill="#ddd"/>' % (D1X - 1.4, (D1A + D1K) / 2 + 1.3))
a.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="#555" stroke-width="0.5"/>' % (D1X, D1A, D1X, D1K))
a.append(T(D1X - 1.8, D1A + 3.2, "D1", 1.5, "end", fill="#000", bold=True))
# R1
a.append('<rect x="%.2f" y="%.2f" width="6.2" height="2.2" fill="#c9a66b" stroke="#000" stroke-width="0.2"/>' % ((R1A + R1B) / 2 - 3.1, Y_TX - 1.1))
a.append(T((R1A + R1B) / 2, Y_TX - 1.6, "R1 1 кОм", 1.5, fill="#000", bold=True))
# C1
a.append('<circle cx="%g" cy="%g" r="4" fill="#335" fill-opacity="0.25" stroke="#335" stroke-width="0.3"/>' % (C1X, (Y_GND + Y_5) / 2))
a.append(T(C1X + 4.6, (Y_GND + Y_5) / 2 + 0.6, "C1 470µ", 1.5, "start", fill="#000", bold=True))
a.append(T(C1X - 1.6, Y_5 + 0.8, "+", 2.2, "end", fill="#c00", bold=True))
# SPK
a.append('<rect x="%.2f" y="%.2f" width="%.2f" height="7.4" fill="#1a7f37" fill-opacity="0.22" stroke="#1a7f37" stroke-width="0.35"/>'
         % (df["B_SPK1"] - 2.4, SPKY - 3.4, df["B_SPK2"] - df["B_SPK1"] + 4.4))
a.append(T((df["B_SPK1"] + df["B_SPK2"]) / 2, SPKY + 5.9, "ДИНАМІК", 1.9, fill="#1a7f37", bold=True))
# клемники: корпус, назва блоку, підпис кожного контакту
HALO = ' stroke="#fff" stroke-width="0.5" paint-order="stroke" stroke-linejoin="round"'
NETCOL = {"GND": "#000", "V3": "#c00", "+5V": "#c00", "P5Z": "#c00"}
blocks = []
for i, (blk, lab, net) in enumerate(ROW):
    if not blocks or blocks[-1][0] != blk:
        blocks.append([blk, i, i])
    blocks[-1][2] = i
for n, (blk, i0, i1) in enumerate(blocks):
    x0, x1 = tx[i0] - TB_P / 2 + 0.15, tx[i1] + TB_P / 2 - 0.15
    a.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#1a7f37" fill-opacity="0.22" stroke="#1a7f37" '
             'stroke-width="0.35"/>' % (x0, Y_ROW - 3.4, x1 - x0, BOARD_H - Y_ROW + 3.4))
    a.append('<text x="%.2f" y="%.2f" font-family="Arial,sans-serif" font-size="2.3" font-weight="bold" '
             'text-anchor="middle" fill="#1a7f37">%s</text>' % ((x0 + x1) / 2, BOARD_H + 2.6, blk))
    a.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#1a7f37" stroke-width="0.4"/>'
             % (x0 + 0.4, BOARD_H + 0.6, x1 - 0.4, BOARD_H + 0.6))
for (blk, lab, net), x in zip(ROW, tx):
    a.append('<text x="%.2f" y="%.2f" font-family="Arial,sans-serif" font-size="1.9" font-weight="bold" '
             'text-anchor="start" fill="%s"%s transform="rotate(-90 %.2f %.2f)">%s</text>'
             % (x + 0.65, Y_ROW - 2.0, NETCOL.get(net, "#06c"), HALO, x + 0.65, Y_ROW - 2.0, lab))
# рамка-заголовок
a.append(T(BOARD_W / 2, -3.5, "Вид з боку деталей · плата %g×%g мм · мідь (жовта) — на зворотному боці" % (BOARD_W, BOARD_H), 2.6, bold=True))
a.append(T(BOARD_W / 2, BOARD_H + 6.2, "Гвинтові клемники KF301 / DG301, крок 5,08 мм: 3 + 5 + 3 + 4 + 2 контакти, стоять упритул уздовж нижнього краю.", 1.7))
a.append(T(BOARD_W / 2, BOARD_H + 8.5, "VCC = 3,3 В (ХОЛЛ, SW-420, ADXL345); радар живиться від 5V. На модулі ADXL345 з'єднати CS з VCC, SDO з GND.", 1.7))
a.append("</svg>")
open(os.path.join(OUT, "esp32_pcb_assembly.svg"), "w", encoding="utf-8").write("\n".join(a))
# те саме креслення в масштабі 1:1 — надрукувати й приклеїти на бік деталей як підписи клем
a[0] = ('<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" viewBox="-6 -8 %g %g">'
        % (BOARD_W + 12, BOARD_H + 17, BOARD_W + 12, BOARD_H + 17))
open(os.path.join(OUT, "esp32_pcb_labels_1to1.svg"), "w", encoding="utf-8").write("\n".join(a))

# ---------------- PDF A4 для друку 1:1 ----------------
K = 72 / 25.4
OX, OY = (210 - BOARD_W) / 2, 30.0     # положення плати на аркуші, мм від лівого верхнього кута
c = []
c.append("%.6f 0 0 %.6f %.4f %.4f cm" % (K, -K, OX * K, (297 - OY) * K))   # мм, y вниз
c.append("1 J 1 j 0 G 0 g")
for s in segs:
    c.append("%.2f w %.3f %.3f m %.3f %.3f l S" % (s["w"], s["x1"], s["y1"], s["x2"], s["y2"]))


def circ(x, y, r):
    k = 0.5522848 * r
    return ("%.3f %.3f m %.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c "
            "%.3f %.3f %.3f %.3f %.3f %.3f c %.3f %.3f %.3f %.3f %.3f %.3f c f" % (
                x + r, y, x + r, y + k, x + k, y + r, x, y + r, x - k, y + r, x - r, y + k, x - r, y,
                x - r, y - k, x - k, y - r, x, y - r, x + k, y - r, x + r, y - k, x + r, y))


for p in pads:
    c.append(circ(p["x"], p["y"], p["d"] / 2))
c.append("1 g")
for p in pads:
    c.append(circ(p["x"], p["y"], p["hole"] / 2))
c.append("0 g 0.3 w 0 J 0 j 0.15 0.15 %.2f %.2f re S" % (BOARD_W - 0.3, BOARD_H - 0.3))
# дзеркальний напис на міді
c.append("BT /F1 6 Tf -1 0 0 -1 60 17 Tm (%s) Tj ET" % LABEL)
# лінійка та підписи (звичайний текст)
ry = BOARD_H + 8
c.append("0.3 w 0 %g m 50 %g l S" % (ry, ry))
for t in range(0, 51, 10):
    c.append("%d %g m %d %g l S" % (t, ry - 2, t, ry + 2))
c.append("BT /F1 3.2 Tf 1 0 0 -1 53 %g Tm (50 mm  -  print at 100%% / actual size, DO NOT mirror) Tj ET" % (ry + 1.1))
c.append("BT /F1 3.2 Tf 1 0 0 -1 0 -4 Tm (LUT copper layer, board %gx%g mm. Text inside the board must look mirrored on paper.) Tj ET" % (BOARD_W, BOARD_H))
stream = "\n".join(c).encode("latin-1")
objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.276 841.89] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
pdf = b"%PDF-1.4\n"
offs = []
for i, o in enumerate(objs, 1):
    offs.append(len(pdf)); pdf += b"%d 0 obj\n" % i + o + b"\nendobj\n"
xref = len(pdf)
pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
for o in offs:
    pdf += b"%010d 00000 n \n" % o
pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
open(os.path.join(OUT, "esp32_pcb_LUT_A4.pdf"), "wb").write(pdf)
print("Готово: esp32_pcb_LUT_A4.pdf, esp32_pcb_copper_print.svg, esp32_pcb_assembly.svg")
