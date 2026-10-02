# -*- coding: utf-8 -*-
"""
DOBOZ LÉTREHOZÁSA - egyszerű doboz (asztallap, munkadarab, rajzlap, tiltott zóna) megadott méretekkel
====================================================================================================

A cella kézi felépítéséhez (UTMUTATO.md). A RoboDK-ban nincs mindig kéznél egy egyszerű "doboz"
parancs, ezért ez a szkript megadott méretű és színű dobozt hoz létre egy referencia keretben.

Használat:
  1. Jelöld ki a fában azt a referencia keretet, amelyhez a doboz tartozzon (pl. "Asztal").
  2. Húzd be ezt a fájlt a RoboDK-ba, majd kattints rá duplán.
  3. Add meg a nevet, a méreteket, a doboz alaplapjának közepét a keretben és a színt.

A doboz origója az alaplapjának közepe. Ha a név tartalmazza a "tiltott", "zona" vagy "akadaly" szót,
a doboz méretét a meresek_rogzitese.py is látja, és megméri, milyen közel ment hozzá a robot TCP-je.
"""

import json

try:
    from robodk import robolink, robomath  # RoboDK 5.4 és újabb
except ImportError:  # régebbi RoboDK verziók
    import robolink
    import robodk as robomath

SZINEK = {
    "szürke (asztal)": [0.82, 0.82, 0.80, 1.0],
    "kék (munkadarab)": [0.16, 0.47, 0.84, 1.0],
    "világoskék (műtőasztal)": [0.75, 0.82, 0.86, 1.0],
    "fehér (rajzlap)": [0.97, 0.97, 0.95, 1.0],
    "zöld (jelölő)": [0.05, 0.64, 0.05, 0.7],
    "piros, átlátszó (tiltott zóna)": [0.82, 0.23, 0.23, 0.35],
}
ALAP = {"Név": "Munkadarab", "Méret X [mm]": 50.0, "Méret Y [mm]": 50.0, "Méret Z [mm]": 50.0,
        "Hely X [mm]": 0.0, "Hely Y [mm]": 0.0, "Hely Z [mm]": 0.0}


def lap(csucsok, normal):
    pontok = []
    for i in range(1, len(csucsok) - 1):
        a, b, c = csucsok[0], csucsok[i], csucsok[i + 1]
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        if sum(n[k] * normal[k] for k in range(3)) < 0:
            b, c = c, b
        for p in (a, b, c):
            pontok.append(list(p) + list(normal))
    return pontok


def doboz_haromszogek(dx, dy, dz):
    x0, x1, y0, y1, z0, z1 = -dx / 2.0, dx / 2.0, -dy / 2.0, dy / 2.0, 0.0, float(dz)
    lapok = [
        ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1)),
        ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1)),
        ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0)),
        ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0)),
        ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], (-1, 0, 0)),
        ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0)),
    ]
    pontok = []
    for csucsok, normal in lapok:
        pontok += lap(csucsok, normal)
    return pontok


def adatok_bekerese():
    """{mező: érték} és a szín neve, vagy None (Mégse)."""
    mezok = dict(ALAP)
    mezok["Szín"] = [1, list(SZINEK)]
    try:
        from robodk import robodialogs
        v = robodialogs.InputDialog("Az új doboz adatai (a hely a doboz alaplapjának közepe a kijelölt keretben):",
                                    mezok, title="Doboz létrehozása")
        if v is None:
            return None
        szin = v["Szín"]
        szin = list(SZINEK)[szin[0]] if isinstance(szin, list) else (szin if szin in SZINEK else list(SZINEK)[int(szin)])
        return v, szin
    except Exception:
        pass
    import tkinter
    from tkinter import simpledialog
    ablak = tkinter.Tk()
    ablak.withdraw()
    v = {}
    for k, alap in ALAP.items():
        if isinstance(alap, str):
            v[k] = simpledialog.askstring("Doboz létrehozása", k, initialvalue=alap, parent=ablak)
        else:
            v[k] = simpledialog.askfloat("Doboz létrehozása", k, initialvalue=alap, parent=ablak)
        if v[k] is None:
            ablak.destroy()
            return None
    sorszam = simpledialog.askinteger("Doboz létrehozása", "Szín:\n" + "\n".join(
        "%d = %s" % (i + 1, n) for i, n in enumerate(SZINEK)), initialvalue=2, parent=ablak)
    ablak.destroy()
    return v, list(SZINEK)[max(1, min(len(SZINEK), sorszam or 2)) - 1]


def main():
    RDK = robolink.Robolink()
    keret = None
    try:
        kijelolt = [x for x in RDK.Selection() if x.Type() in (robolink.ITEM_TYPE_FRAME, robolink.ITEM_TYPE_STATION)]
        keret = kijelolt[0] if kijelolt else None
    except Exception:
        keret = None
    if keret is None:
        keret = RDK.ItemUserPick("Melyik referencia kerethez tartozzon a doboz?", robolink.ITEM_TYPE_FRAME)
        if not keret.Valid():
            return
    eredmeny = adatok_bekerese()
    if eredmeny is None:
        print("Megszakítva.")
        return
    v, szin = eredmeny
    dx, dy, dz = float(v["Méret X [mm]"]), float(v["Méret Y [mm]"]), float(v["Méret Z [mm]"])
    obj = RDK.AddShape(doboz_haromszogek(dx, dy, dz))
    obj.setName(str(v["Név"]))
    obj.setParent(keret)
    obj.setPose(robomath.transl(float(v["Hely X [mm]"]), float(v["Hely Y [mm]"]), float(v["Hely Z [mm]"])))
    obj.setColor(list(SZINEK[szin]))
    nev = str(v["Név"]).lower()
    if any(k in nev for k in ("tiltott", "zona", "zóna", "akadaly", "akadály")):
        adat = {"min": [-dx / 2.0, -dy / 2.0, 0.0], "max": [dx / 2.0, dy / 2.0, dz]}
        try:
            obj.setParam("ZonaDoboz", json.dumps(adat).encode("utf-8"))
        except Exception:
            pass
    uzenet = "Létrehozva: %s (%g × %g × %g mm) a(z) %s keretben." % (v["Név"], dx, dy, dz, keret.Name())
    print(uzenet)
    RDK.ShowMessage(uzenet, False)


if __name__ == "__main__":
    main()
