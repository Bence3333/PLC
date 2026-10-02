# -*- coding: utf-8 -*-
"""
A RoboDK-szkriptek kipróbálása RoboDK NÉLKÜL, szimulált állomásokon (robodk_szimulacio.py).

    python teszt/teszt_futtatas.py <kimeneti_mappa> [--feladat 1 2 3] [--xyz-allomasban]

Feladatonként: új állomás a javasolt robottal -> lépésnapló -> cella_epito.py -> lépésnapló ->
meresek_rogzitese.py -> ellenőrzések. A keletkező adatok FIKTÍVEK (egyszerűsített kinematika).
--xyz-allomasban: a pályaadat XYZ oszlopait más rendszerben adja (a direkt kinematikás ág tesztje).
"""

import json
import os
import runpy
import sys
import types

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ITT = os.path.dirname(os.path.abspath(__file__))
GYOKER = os.path.dirname(ITT)
sys.path.insert(0, ITT)
import robodk_szimulacio as szim  # noqa: E402

R = szim.R
ROBOTOK = {1: "UR5e", 2: "ABB IRB 120-3/0.6", 3: "KUKA LBR iiwa 7 R800"}
LEPESEK = {
    1: (["Új állomás, UR5e robot betöltése az online könyvtárból (File → Open online library)"],
        ["Megfogó (TCP: Z = 160 mm), Asztal referencia keret, asztallap, munkadarab (50×50×50 mm) és lerakóhely",
         "Célpontok: Home, Felvetel_felett, Felvetel, Lerakas_felett, Lerakas (a szerszám lefelé néz)",
         "Programok: PP_MoveJ_* és PP_MoveL_* három sebességgel, PP_ismetles_3x; megfogás/elengedés eseménnyel"]),
    2: (["Új állomás, ABB IRB 120-3/0.6 robot betöltése az online könyvtárból"],
        ["Toll szerszám (TCP: Z = 120 mm), Palya referencia keret a négyzet közepén, rajzlap",
         "A négyzet csúcsai: P1(-75; -75), P2(75; -75), P3(75; 75), P4(-75; 75) mm, Z = 0",
         "Programok: lassú (50 mm/s) és gyors (500 mm/s), pontos és 10 mm-es lekerekítéssel"]),
    3: (["Új állomás, KUKA LBR iiwa 7 R800 robot betöltése az online könyvtárból"],
        ["Műszer (TCP: Z = 180 mm), műtéti terület keret, műtőasztal, tiltott zóna (60×60×60 mm)",
         "Kiindulási pont és C1, C2, C3 célpont, fölöttük 100 mm-es biztonsági pontok",
         "Programok: 10, 50 és 200 mm/s, valamint 200 mm/s lekerekített átmeneti pontokkal"]),
}


def helyettesito_kep(fajl, st):
    """'Képernyőkép' helyett vázlat az állomásról - jól láthatóan MINTA felirattal."""
    fig = plt.figure(figsize=(8, 5), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    fig.patch.set_facecolor("#f0efec")
    ax.set_facecolor("#f0efec")
    pontok = []

    def halo(A, haromszogek, szin, alfa):
        for pts, _ in haromszogek:
            P = (np.c_[pts, np.ones(len(pts))] @ A.T)[:, :3]
            pontok.extend(P)
            ax.add_collection3d(Poly3DCollection(P.reshape(-1, 3, 3), facecolor=szin, alpha=alfa, edgecolor="none"))

    for e in st.elo(R.ITEM_TYPE_OBJECT):
        if e.haromszogek:
            halo(e._abs(), e.haromszogek, e.szin[:3], max(0.25, e.szin[3]))
        if e.gorbe is not None:
            P = (np.c_[e.gorbe, np.ones(len(e.gorbe))] @ e._abs().T)[:, :3]
            ax.plot(P[:, 0], P[:, 1], P[:, 2], color="#52514e", lw=1)
    for r in st.elo(R.ITEM_TYPE_ROBOT):
        def rajz(q, szin, vastag, alfa):
            lanc = [(r._abs() @ T)[:3, 3] for T in r._lanc(q)] + [(r._abs() @ r._fk(q) @ r._tcp())[:3, 3]]
            p = np.array(lanc)
            pontok.extend(p)
            ax.plot(p[:, 0], p[:, 1], p[:, 2], "-o", color=szin, lw=vastag, ms=3, alpha=alfa)
        for q in r.szellemek:
            rajz(q, "#86b6ef", 1.4, 0.6)
        rajz(r.q, "#2a78d6", 3, 1.0)
        if isinstance(r.aktiv_szerszam, szim.Elem) and r.aktiv_szerszam.haromszogek:
            halo(r._abs() @ r._fk(r.q), r.aktiv_szerszam.haromszogek, (0.35, 0.35, 0.38), 0.9)
    for t in st.elo(R.ITEM_TYPE_TARGET):
        p = (t.szulo._abs() @ szim.np_m(t.Pose()))[:3, 3]
        ax.scatter([p[0]], [p[1]], [p[2]], color="#eb6834", s=10)
    P = np.array(pontok)
    kozep, meret = (P.max(0) + P.min(0)) / 2, max(P.max(0) - P.min(0)) / 2 * 1.05
    z0 = max(P.min(0)[2] - 20, kozep[2] - meret)
    ax.set_xlim(kozep[0] - meret, kozep[0] + meret)
    ax.set_ylim(kozep[1] - meret, kozep[1] + meret)
    ax.set_zlim(z0, z0 + 2 * meret)
    ax.set_box_aspect((1, 1, 1), zoom=1.3)
    ax.view_init(elev=24, azim=-58)
    ax.set_axis_off()
    fig.subplots_adjust(0, 0.06, 1, 1)
    fig.text(0.5, 0.03, "MINTA – helyettesítő vázlat; a valódi jegyzőkönyvben itt a RoboDK 3D nézetének képe lesz",
             ha="center", fontsize=9, color="#52514e")
    fig.savefig(fajl, facecolor=fig.get_facecolor())
    plt.close(fig)


def hamis_dialogusok(valaszok):
    modul = types.ModuleType("robodk.robodialogs")

    def input_dialog(msg, value, title=None, **kw):
        v = valaszok.pop(0)
        return [v, value[1]] if isinstance(value, list) else v
    modul.InputDialog = input_dialog
    modul.ShowMessageYesNo = lambda msg, title=None: True
    sys.modules["robodk.robodialogs"] = modul
    import robodk
    robodk.robodialogs = modul


def futtat(nev):
    runpy.run_path(os.path.join(GYOKER, "robodk_scripts", nev), run_name="__main__")


def feladat_teszt(k, kimenet, xyz_bazisban=True):
    bazis = None
    if not xyz_bazisban:  # a robot nem az origóban áll: a pályaadat XYZ-je más rendszerben van
        bazis = np.eye(4)
        bazis[:3, 3] = [150.0, -80.0, 250.0]
    st = szim.telepites(kimenet, "Feladat%d" % k, ROBOTOK[k], kep_rajzolo=helyettesito_kep, bazis_poz=bazis)
    st.xyz_bazisban = xyz_bazisban
    elotte, utana = LEPESEK[k]
    hamis_dialogusok(list(elotte) + [k - 1] + list(utana) + ["végleges változat"])
    for _ in elotte:
        futtat("lepes_rogzitese.py")
    futtat("cella_epito.py")
    for _ in utana:
        futtat("lepes_rogzitese.py")
    robot = st.rdk.ItemList(R.ITEM_TYPE_ROBOT)[0]
    st.rdk.AddProgram("x_proba", robot)  # próbaprogram: a mérésnek ki kell hagynia
    futtat("meresek_rogzitese.py")

    adatmappa = os.path.join(kimenet, "Feladat%d_dokumentacio" % k)
    assert os.path.isfile(os.path.join(adatmappa, "feladat.txt"))
    meres = sorted(d for d in os.listdir(adatmappa) if d.startswith("meres_"))[-1]
    adat = json.load(open(os.path.join(adatmappa, meres, "meresek.json"), encoding="utf-8"))
    progs = {p["nev"]: p for p in adat["programok"]}
    assert "x_proba" not in progs and adat.get("kihagyott_programok") == ["x_proba"], adat.get("kihagyott_programok")
    for p in progs.values():
        assert p["frissites"]["ervenyesseg_arany"] > 0.999, (p["nev"], p["frissites"])
        st_ = p["palya"]["statisztika"]
        assert abs(st_["idotartam_s"] - p["frissites"]["ciklusido_s"]) < 0.05, (p["nev"], st_["idotartam_s"])
        assert st_["max_elteres_megallo_mm"] < 0.05, (p["nev"], st_["max_elteres_megallo_mm"])
        assert p["palya"]["celpontok"], p["nev"]
        assert p["utkozes"]["utkozesmentes"], p["nev"]
        assert st_["pozicio_forras"] == ("RoboDK pályaadat (XYZ)" if xyz_bazisban else "direkt kinematika")
        if st_.get("max_palya_elteres_mm") is not None and "lekerekitett" not in p["nev"]:
            assert st_["max_palya_elteres_mm"] < 0.01, (p["nev"], st_["max_palya_elteres_mm"])
    if k == 1:
        for szint in ("lassu", "kozepes", "gyors"):
            j, l = progs["PP_MoveJ_" + szint], progs["PP_MoveL_" + szint]
            assert j["palya"]["statisztika"]["felveteltol_lerakasig_s"] > 0
            assert l["palya"]["statisztika"]["tcp_palyahossz_mm"] < j["palya"]["statisztika"]["tcp_palyahossz_mm"]
        assert progs["PP_ismetles_3x"]["palya"]["statisztika"]["ismetlesi_elteres_mm"] < 0.05
        assert progs["PP_MoveJ_gyors"]["frissites"]["ciklusido_s"] < progs["PP_MoveJ_lassu"]["frissites"]["ciklusido_s"]
        # a megfogás/elengedés makrók működnek
        darab = st.rdk.Item("Munkadarab", R.ITEM_TYPE_OBJECT)
        asztal = st.rdk.Item("Asztal", R.ITEM_TYPE_FRAME)
        for makro, szulo in (("Megfogas", st.rdk.Item("Megfogo", R.ITEM_TYPE_TOOL)), ("Elengedes", asztal),
                             ("Alaphelyzet", asztal)):
            runpy.run_path(st.rdk.Item(makro, R.ITEM_TYPE_PROGRAM_PYTHON).fajl, run_name="__main__")
            assert darab.szulo is szulo, makro
    if k == 2:
        for szint in ("lassu", "gyors"):
            pontos = progs["Negyzet_" + szint]["palya"]["statisztika"]
            kerek = progs["Negyzet_%s_lekerekitett" % szint]["palya"]["statisztika"]
            assert pontos["max_palya_elteres_mm"] < 0.05 and kerek["max_palya_elteres_mm"] > 0.5, (pontos, kerek)
            assert pontos["ismetlesi_elteres_mm"] < 0.05  # P1 a kör elején és végén
            cp = progs["Negyzet_" + szint]["palya"]["celpontok"]
            assert [c["celpont"] for c in cp] == ["Home", "P1_felett", "P1", "P2", "P3", "P4", "P1", "P1_felett", "Home"]
    if k == 3:
        for p in progs.values():
            z = p["palya"]["statisztika"]["zona"]
            assert not z["belepett"] and 20 < z["min_tavolsag_mm"] < 60, (p["nev"], z)
        assert adat["tiltott_zonak"][0]["max"][2] == 60
        doboz_teszt(st)
    print("  %d. feladat: OK (%d program)" % (k, len(progs)))
    return adatmappa


def doboz_teszt(st):
    """doboz_letrehozasa.py: a kijelölt keretbe kerül, a megadott helyre, és a zóna mérete eltárolódik."""
    keret = st.rdk.Item("Muteti_terulet", R.ITEM_TYPE_FRAME)
    st.kijeloles = [keret]
    hamis_dialogusok([{"Név": "Akadaly_proba", "Méret X [mm]": 40.0, "Méret Y [mm]": 20.0, "Méret Z [mm]": 30.0,
                       "Hely X [mm]": 100.0, "Hely Y [mm]": 50.0, "Hely Z [mm]": 0.0, "Szín": [5, []]}])
    futtat("doboz_letrehozasa.py")
    st.kijeloles = []
    obj = [o for o in st.rdk.ItemList(R.ITEM_TYPE_OBJECT) if o.Name() == "Akadaly_proba"][0]
    assert obj.szulo is keret, obj.szulo
    assert np.allclose(szim.np_m(obj.Pose())[:3, 3], [100, 50, 0])
    assert json.loads(obj.getParam("ZonaDoboz").decode("utf-8")) == {"min": [-20, -10, 0], "max": [20, 10, 30]}
    P = np.vstack([pts for pts, _ in obj.haromszogek])
    assert np.allclose(P.min(0), [-20, -10, 0]) and np.allclose(P.max(0), [20, 10, 30]), (P.min(0), P.max(0))
    print("  doboz_letrehozasa.py: OK")


def main():
    argumentumok = [a for a in sys.argv[1:]]
    kimenet = os.path.abspath(argumentumok[0] if argumentumok and not argumentumok[0].startswith("--")
                              else os.path.join(ITT, "kimenet"))
    os.makedirs(kimenet, exist_ok=True)
    feladatok = [1, 2, 3]
    if "--feladat" in argumentumok:
        i = argumentumok.index("--feladat") + 1
        feladatok = []
        while i < len(argumentumok) and argumentumok[i].isdigit():
            feladatok.append(int(argumentumok[i]))
            i += 1
    for k in feladatok:
        feladat_teszt(k, kimenet, xyz_bazisban="--xyz-allomasban" not in argumentumok)
    print("\nOK - minden ellenőrzés sikeres. Adatok: " + kimenet)


if __name__ == "__main__":
    main()
