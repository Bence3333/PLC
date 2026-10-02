# -*- coding: utf-8 -*-
"""
RoboDK LÉPÉSNAPLÓ - minden munkalépés rögzítése képernyőképpel a jegyzőkönyvhöz
==============================================================================

Használat:
  1. Mentsd el az állomást (File -> Save Station), mert a napló az .rdk fájl mellé kerül.
  2. Húzd be ezt a fájlt a RoboDK ablakába (vagy File -> Open) -> a fában megjelenik
     a "lepes_rogzitese" elem.
  3. Minden fontos lépés után (robot betöltése, szerszám felrakása, referencia keret,
     célpontok felvétele, program megírása, szimuláció...) állítsd be a 3D nézetet,
     és kattints duplán a "lepes_rogzitese" elemre.
  4. Írd be röviden, mit csináltál. A script elmenti a leírást, a képernyőképet és azt,
     hogy milyen új elemek jelentek meg az állomásban az előző lépés óta.

Kimenet: <az .rdk mappája>/<állomás neve>_dokumentacio/
  lepesek.json         a lépések listája (Jegyzettömbbel utólag is javítható)
  kepek/lepes_01.png   képernyőképek

A jegyzőkönyvben a lépések ebben a sorrendben, képpel együtt jelennek meg
(dokumentacio/jegyzokonyv_keszito.py).
"""

import datetime
import json
import os
import re
import unicodedata

try:
    from robodk import robolink  # RoboDK 5.4 és újabb
except ImportError:  # régebbi RoboDK verziók
    import robolink

ADATMAPPA_UTOTAG = "_dokumentacio"
KERDES = "Írd le röviden, mit csináltál ebben a lépésben\n(pl. „ABB IRB 120 robot betöltése a könyvtárból”):"


def ascii_nev(szoveg, alap="elem"):
    s = unicodedata.normalize("NFKD", str(szoveg))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")
    return s or alap


def adatmappa(RDK):
    """<az .rdk mappája>/<állomás neve>_dokumentacio  (ha nincs mentve: Asztal)."""
    allomas_nev = ""
    try:
        allomas_nev = RDK.ActiveStation().Name()
    except Exception:
        pass
    if not allomas_nev:
        try:
            allomas_nev = os.path.splitext(str(RDK.getParam("FILE_OPENSTATION") or ""))[0]
        except Exception:
            allomas_nev = ""
    mappa = ""
    try:
        mappa = str(RDK.getParam("PATH_OPENSTATION") or "")
    except Exception:
        mappa = ""
    if mappa.lower().endswith(".rdk"):
        mappa = os.path.dirname(mappa)
    if not mappa or not os.path.isdir(mappa):
        try:
            mappa = str(RDK.getParam("PATH_DESKTOP") or "")
        except Exception:
            mappa = ""
    if not mappa or not os.path.isdir(mappa):
        mappa = os.path.expanduser("~")
    return os.path.join(mappa, ascii_nev(allomas_nev, "allomas") + ADATMAPPA_UTOTAG)


def kepernyokep(RDK, fajl):
    for kamera in (None, 0):  # None: fő 3D nézet (újabb RoboDK), 0: régebbi verziók
        try:
            if RDK.Cam2D_Snapshot(fajl, kamera) and os.path.isfile(fajl):
                return True
        except Exception:
            pass
    return False


def leiras_bekerese(alapertek):
    """Szövegbekérés: RoboDK dialógus -> tkinter -> ha egyik sincs, az alapérték.
    None-t ad vissza, ha a felhasználó a Mégse gombot nyomta."""
    try:
        from robodk import robodialogs
        return robodialogs.InputDialog(KERDES, alapertek, title="Lépés rögzítése")
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import simpledialog
        gyoker = tkinter.Tk()
        gyoker.withdraw()
        gyoker.attributes("-topmost", True)
        valasz = simpledialog.askstring("Lépés rögzítése", KERDES, initialvalue=alapertek, parent=gyoker)
        gyoker.destroy()
        return valasz
    except Exception:
        return alapertek


def main():
    RDK = robolink.Robolink()
    gyoker = adatmappa(RDK)
    os.makedirs(os.path.join(gyoker, "kepek"), exist_ok=True)
    naplo_fajl = os.path.join(gyoker, "lepesek.json")

    lepesek = []
    if os.path.isfile(naplo_fajl):
        with open(naplo_fajl, encoding="utf-8") as f:
            lepesek = json.load(f)

    try:
        elemek = [n for n in RDK.ItemList(None, True)
                  if not n.startswith(("lepes_rogzitese", "meresek_rogzitese"))]
    except Exception:
        elemek = []
    elozo = set(lepesek[-1].get("elemek", [])) if lepesek else set()
    uj_elemek = [n for n in elemek if n not in elozo]

    # a legnagyobb eddigi sorszám + 1, így egy törölt lépés után sem íródik felül meglévő kép
    sorszam = max([int(l.get("sorszam", 0)) for l in lepesek] + [0]) + 1
    javaslat = ("Új elemek: " + ", ".join(uj_elemek[:8])) if (lepesek and uj_elemek) else ""
    leiras = leiras_bekerese(javaslat)
    if leiras is None:  # Mégse
        print("A lépés rögzítése megszakítva.")
        return
    leiras = leiras.strip() or ("%d. lépés (leírás pótlandó)" % sorszam)

    kep = os.path.join("kepek", "lepes_%02d.png" % sorszam)
    van_kep = kepernyokep(RDK, os.path.join(gyoker, kep))

    lepesek.append({
        "sorszam": sorszam,
        "idopont": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "leiras": leiras,
        "kep": kep.replace("\\", "/"),  # ha nem készült el, kézzel ide mentett kép is bekerül
        "kep_automatikus": van_kep,
        "uj_elemek": uj_elemek if lepesek else [],
        "elemek": elemek,
    })
    with open(naplo_fajl, "w", encoding="utf-8") as f:
        json.dump(lepesek, f, ensure_ascii=False, indent=2)

    uzenet = "%d. lépés rögzítve: %s" % (sorszam, leiras)
    if not van_kep:
        uzenet += " (képernyőkép nem készült - mentsd kézzel ide, és bekerül a jegyzőkönyvbe: %s)" % os.path.join(gyoker, kep)
    print(uzenet)
    try:
        RDK.ShowMessage(uzenet, False)  # állapotsor-üzenet, nem blokkol
    except Exception:
        pass


if __name__ == "__main__":
    main()
