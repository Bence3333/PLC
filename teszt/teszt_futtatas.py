# -*- coding: utf-8 -*-
"""
A RoboDK-szkriptek kipróbálása RoboDK NÉLKÜL, a kitalált tesztállomáson (robodk_szimulacio.py).

    python teszt/teszt_futtatas.py <kimeneti_mappa> [--hibas] [--ket-meres]

Lefuttatja a lepes_rogzitese.py-t (6 minta-lépés) és a meresek_rogzitese.py-t, majd ellenőrzi
a kimenetet. --hibas: egy szándékosan hibás programot is betesz (hibakezelés tesztelése).
--ket-meres: két mérés (300 és 500 mm/s), a mérések összehasonlításának teszteléséhez.
A keletkező adatok FIKTÍVEK.
"""

import json
import math
import os
import runpy
import sys
import types

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ITT = os.path.dirname(os.path.abspath(__file__))
GYOKER = os.path.dirname(ITT)
sys.path.insert(0, ITT)
import robodk_szimulacio as szim  # noqa: E402

MINTA_LEPESEK = [
    "Új állomás létrehozása, ABB IRB 120-3/0.6 robot betöltése az online könyvtárból",
    "Megfogó szerszám hozzáadása a robothoz, TCP beállítása (Z = 100 mm)",
    "Asztal referencia keret létrehozása (X = 250 mm, Z = 20 mm), asztallap és doboz elhelyezése",
    "Célpontok felvétele: Home (csukló target), Felvetel_felett, Felvetel, Lerakas_felett, Lerakas",
    "PickAndPlace program összeállítása MoveJ/MoveL utasításokkal, 300 mm/s sebesség, megfogás/elengedés esemény",
    "Program szimulációja, ütközésvizsgálat bekapcsolása (Tools → Check collisions)",
]


def helyettesito_kep(fajl, allomas):
    """'Képernyőkép' helyett egyszerű vázlat a robotról - jól láthatóan MINTA felirattal."""
    fig = plt.figure(figsize=(8, 5), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    fig.patch.set_facecolor("#f0efec")
    ax.set_facecolor("#f0efec")

    def rajz(q, szin, vastag, alfa):
        pontok = [T[:3, 3] for T in szim.fk_lancolat(q)] + [szim.fk_tcp(q)[:3, 3]]
        p = np.array(pontok)
        ax.plot(p[:, 0], p[:, 1], p[:, 2], "-o", color=szin, lw=vastag, ms=3, alpha=alfa)

    for q in allomas.robot.szellemek:
        rajz(q, "#86b6ef", 1.5, 0.6)
    rajz(allomas.robot.q, "#2a78d6", 3, 1.0)
    for c in allomas.celpontok:
        p = szim.fk_tcp(c.q)[:3, 3]
        ax.scatter([p[0]], [p[1]], [p[2]], color="#eb6834", s=12)
    xs, ys = np.meshgrid([250, 550], [-300, 300])
    ax.plot_surface(xs, ys, np.full_like(xs, 20.0), color="#c3c2b7", alpha=0.5)
    ax.set_xlim(-150, 600)
    ax.set_ylim(-375, 375)
    ax.set_zlim(0, 750)
    ax.set_box_aspect((750, 750, 750), zoom=1.25)
    fig.subplots_adjust(0, 0.08, 1, 1)
    ax.view_init(elev=22, azim=-60)
    ax.set_axis_off()
    fig.text(0.5, 0.06, "MINTA – helyettesítő vázlat; a valódi jegyzőkönyvben itt a RoboDK 3D nézetének képe lesz",
             ha="center", fontsize=9, color="#52514e")
    fig.savefig(fajl, facecolor=fig.get_facecolor())
    plt.close(fig)


def hamis_dialogus(valaszok):
    modul = types.ModuleType("robodk.robodialogs")
    modul.InputDialog = lambda msg, value, title=None, **kw: valaszok.pop(0)
    sys.modules["robodk.robodialogs"] = modul
    import robodk
    robodk.robodialogs = modul


def main():
    kimenet = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ITT, "kimenet"))
    os.makedirs(kimenet, exist_ok=True)
    allomas = szim.telepites(kimenet, hibas_program="--hibas" in sys.argv, kep_rajzolo=helyettesito_kep)

    adatmappa = os.path.join(kimenet, "Minta_pick_and_place_dokumentacio")
    naplo = os.path.join(adatmappa, "lepesek.json")
    lepes_elotte = len(json.load(open(naplo, encoding="utf-8"))) if os.path.isfile(naplo) else 0
    meres_elotte = len([d for d in os.listdir(adatmappa) if d.startswith("meres_")]) if os.path.isdir(adatmappa) else 0

    ket_meres = "--ket-meres" in sys.argv
    cimkek = ["első változat: v = 300 mm/s", "végleges: v = 500 mm/s"] if ket_meres else ["végleges változat"]
    hamis_dialogus(list(MINTA_LEPESEK) + cimkek)
    for _ in MINTA_LEPESEK:
        runpy.run_path(os.path.join(GYOKER, "robodk_scripts", "lepes_rogzitese.py"), run_name="__main__")
    runpy.run_path(os.path.join(GYOKER, "robodk_scripts", "meresek_rogzitese.py"), run_name="__main__")
    if ket_meres:  # második mérés nagyobb lineáris sebességgel
        prog = allomas.programok[0]
        prog.utasitasok[0] = ("speed", 500)
        prog._palya = None
        runpy.run_path(os.path.join(GYOKER, "robodk_scripts", "meresek_rogzitese.py"), run_name="__main__")

    # --- Ellenőrzések (egy korábbi futás adatai mellé is írhat: a napló bővül, a mérés új mappába kerül) ---
    lepesek = json.load(open(naplo, encoding="utf-8"))
    assert len(lepesek) == lepes_elotte + len(MINTA_LEPESEK), len(lepesek)
    assert all(os.path.isfile(os.path.join(adatmappa, l["kep"])) for l in lepesek)
    meresek = sorted(d for d in os.listdir(adatmappa) if d.startswith("meres_"))
    assert len(meresek) == meres_elotte + (2 if ket_meres else 1), meresek
    adat = json.load(open(os.path.join(adatmappa, meresek[-1], "meresek.json"), encoding="utf-8"))
    assert adat["megnevezes"] == cimkek[-1], adat["megnevezes"]
    if ket_meres:
        elso = json.load(open(os.path.join(adatmappa, meresek[0], "meresek.json"), encoding="utf-8"))
        assert elso["programok"][0]["frissites"]["ciklusido_s"] > adat["programok"][0]["frissites"]["ciklusido_s"]
    p = adat["programok"][0]
    st = p["palya"]["statisztika"]
    assert abs(st["idotartam_s"] - p["frissites"]["ciklusido_s"]) < 0.05, (st["idotartam_s"], p["frissites"])
    assert abs(st["tcp_palyahossz_mm"] - p["frissites"]["palyahossz_mm"]) / p["frissites"]["palyahossz_mm"] < 0.02
    assert len(st["csuklok"]) == 6 and all("max_gyorsulas_fok_s2" in c for c in st["csuklok"])
    assert p["utkozes"]["utkozesmentes"] is True
    assert len(adat["celpontok"]) >= 5 and len(adat["robotok"]) == 1

    # A pózkonverzió egyezzen a robodk csomag Pose_2_TxyzRxyz függvényével
    from robodk import robomath
    for c in allomas.celpontok:
        ref = robomath.Pose_2_TxyzRxyz(c.Pose())
        sajat = next(x["poz"] for x in adat["celpontok"] if x["nev"] == c.nev)
        assert all(abs(a - b) < 1e-6 for a, b in zip(sajat[:3], ref[:3]))
        assert all(abs(math.radians(a) - b) < 1e-9 for a, b in zip(sajat[3:], ref[3:]))

    if "--hibas" in sys.argv:
        h = adat["programok"][1]
        assert h["palya"]["statisztika"]["hibas_mintak"] > 0
        assert h["utkozes"]["utkozesmentes"] is False
        leirasok = [x["leiras"] for x in h["palya"]["statisztika"]["hibak"]]
        assert any("Ütközés" in x for x in leirasok) and any("szingularitás" in x for x in leirasok), leirasok
    print("\nOK - minden ellenőrzés sikeres. Adatok: " + adatmappa)


if __name__ == "__main__":
    main()
