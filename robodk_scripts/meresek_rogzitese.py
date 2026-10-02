# -*- coding: utf-8 -*-
"""
RoboDK MÉRÉSRÖGZÍTŐ - a jegyzőkönyvhöz szükséges mérések automatikus kimentése
==============================================================================

Mit ment ki?
  * az állomás adatait (RoboDK verzió, robotok, szerszámok/TCP, referencia keretek, objektumok)
  * minden célpont (target) koordinátáit és csuklószögeit
  * minden program utasításlistáját
  * programonként: becsült ciklusidő, TCP pályahossz, érvényesség, ütközésvizsgálat
  * programonként időalapú pályát: csuklószögek, TCP pozíció, csukló- és TCP-sebesség,
    csuklógyorsulás, csuklóhatároktól való távolság, szingularitás/elérhetőségi hibák
  * célpontonként: érkezési és indulási idő, szakaszidő, szakaszhossz, a tengelyek elfordulása,
    a célpont elérésének pontossága (eltérés mm-ben), MoveL-nél az egyenes pályától való eltérés,
    ugyanazon célpont ismételt elérésének szórása, felvételtől lerakásig eltelt idő
  * tiltott zóna (pl. "Tiltott_zona" nevű doboz) esetén a TCP legkisebb távolsága a zónától
  * képernyőképeket (az állomásról + a pályákról "szellemrobotokkal")
  Az "x_" kezdetű nevű programokat (próbaprogramok) kihagyja (KIHAGYOTT_ELOTAG).

Használat:
  1. Mentsd el az állomást (File -> Save Station), mert az adatok az .rdk fájl mellé kerülnek.
  2. Állítsd be a 3D nézetet úgy, ahogy a képeken látni szeretnéd.
  3. Húzd be ezt a fájlt a RoboDK ablakába (vagy File -> Open), majd kattints duplán
     a fában megjelenő "meresek_rogzitese" elemre.
     (Külső Pythonból / VS Code-ból is futtatható, ha közben a RoboDK nyitva van.)

Kimenet:  <az .rdk mappája>/<állomás neve>_dokumentacio/meres_ÉÉÉÉHHNN_ÓÓPPMM/
  meresek.json          minden adat (ezt olvassa a dokumentacio/jegyzokonyv_keszito.py)
  celpontok.csv         célpontok (Excelben megnyitható)
  programok.csv         programonkénti összesítés
  palya_<program>.csv   időalapú pálya-mintavétel
  kepek/*.png           képernyőképek

Csak a RoboDK-val együtt telepített 'robodk' csomagot és a Python standard könyvtárat használja.
"""

import csv
import datetime
import json
import math
import os
import re
import sys
import time
import unicodedata

try:
    from robodk import robolink  # RoboDK 5.4 és újabb
except ImportError:  # régebbi RoboDK verziók
    import robolink

# ---------------------------------------------------------------------------
# BEÁLLÍTÁSOK
# ---------------------------------------------------------------------------
IDOLEPES_S = None  # pálya-mintavételi időlépés [s]; None = automatikus (kb. 3000 minta/program)
MAX_MINTASZAM = 3000  # automatikus időlépésnél ennyi mintára törekszik
UTKOZESVIZSGALAT = True  # programonként ütközésvizsgálat is (lassabb, de a jegyzőkönyvbe kell)
KEPERNYOKEPEK = True  # képernyőképek mentése a 3D nézetről
SZELLEM_ROBOTOK = 8  # ennyi átlátszó "szellemrobot" a pályaképeken (0 = kikapcsolva)
ADATMAPPA_UTOTAG = "_dokumentacio"  # <állomás neve>_dokumentacio
MEGNEVEZES_KERESE = True  # induláskor rákérdez a mérés nevére (pl. "v = 300 mm/s") - összehasonlításhoz hasznos
KEZDES_ELSO_CELPONTBOL = True  # mérés előtt a robot a program első célpontjába áll -> a ciklusidő nem függ
#                                attól, hol állt éppen a robot (a mérés végén visszaáll az eredeti helyzetbe)
CELPONT_TUR_MM = 0.1  # a TCP ennyire [mm] megközelítve "megérkezett" egy megálló célpontba (a 7 tengelyes
#                        robotoknál a csuklóállás nem egyértelmű, ezért a felismerés a TCP helyzetén alapul)
ZONA_KULCSSZAVAK = ("tiltott", "zona", "akadaly")  # ilyen nevű objektumok számítanak tiltott zónának
KIHAGYOTT_ELOTAG = "x_"  # az ilyen nevű programokat (pl. "x_proba", próbaprogramok) a mérés kihagyja

ITEM_TYPE_ROBOT = robolink.ITEM_TYPE_ROBOT
ITEM_TYPE_FRAME = robolink.ITEM_TYPE_FRAME
ITEM_TYPE_TOOL = robolink.ITEM_TYPE_TOOL
ITEM_TYPE_OBJECT = robolink.ITEM_TYPE_OBJECT
ITEM_TYPE_TARGET = robolink.ITEM_TYPE_TARGET
ITEM_TYPE_PROGRAM = robolink.ITEM_TYPE_PROGRAM
COLLISION_OFF = getattr(robolink, "COLLISION_OFF", 0)
COLLISION_ON = getattr(robolink, "COLLISION_ON", 1)
INS_TYPE_MOVE = getattr(robolink, "INS_TYPE_MOVE", 0)

UTASITAS_TIPUSOK = {
    0: "Mozgás", 1: "Körmozgás (MoveC)", 2: "Sebesség beállítása", 3: "Referencia beállítása",
    4: "Szerszám beállítása", 5: "Robot beállítása", 6: "Szünet", 7: "Szimulációs esemény",
    8: "Kód / programhívás", 9: "Üzenet", 10: "Lekerekítés", 11: "I/O beállítás / várakozás",
    12: "Egyedi utasítás",
}
MOZGAS_TIPUSOK = {1: "MoveJ (csukló)", 2: "MoveL (lineáris)", 3: "MoveC (kör)", 5: "SearchL (keresés)"}

# Sequence-display jelzők számértékkel, hogy régebbi robodk csomaggal is működjön
SEQ_RESET = 1024
SEQ_ROBOT_JOINTS = 2048
SEQ_COLOR_TRANSPARENT = 2


# ---------------------------------------------------------------------------
# Segédfüggvények
# ---------------------------------------------------------------------------
def ascii_nev(szoveg, alap="elem"):
    """Fájlnévnek alkalmas, ékezet nélküli név."""
    s = unicodedata.normalize("NFKD", str(szoveg))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")
    return s or alap


def egyedi_nev(nev, foglalt):
    """Ha a név már foglalt, sorszámot fűz hozzá (palya_Prog, palya_Prog_2, ...)."""
    jelolt, i = nev, 2
    while jelolt.lower() in foglalt:
        jelolt = "%s_%d" % (nev, i)
        i += 1
    foglalt.add(jelolt.lower())
    return jelolt


def szam_csv(v, tizedes=3):
    """Szám magyar Excel-formátumban (tizedesvessző)."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return ""
    return ("%.*f" % (tizedes, f)).replace(".", ",")


def csv_iras(fajl, fejlec, sorok):
    with open(fajl, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(fejlec)
        for s in sorok:
            w.writerow(s)


def pose_xyzrxyz(pose):
    """4x4 pózmátrix -> [X, Y, Z (mm), Rx, Ry, Rz (fok)]  ahol  H = transl(X,Y,Z)·rotx(Rx)·roty(Ry)·rotz(Rz)."""
    H = pose.rows
    x, y, z = H[0][3], H[1][3], H[2][3]
    a, b, c, d, e = H[0][0], H[0][1], H[0][2], H[1][2], H[2][2]
    if c > 1.0 - 1e-10:
        rx, ry, rz = 0.0, math.pi / 2, math.atan2(H[1][0], H[1][1])
    elif c < -1.0 + 1e-10:
        rx, ry, rz = 0.0, -math.pi / 2, math.atan2(H[1][0], H[1][1])
    else:
        cy = math.sqrt(1.0 - c * c)
        rx = math.atan2(-d / cy, e / cy)
        ry = math.atan2(c, cy)
        rz = math.atan2(-b / cy, a / cy)
    return [float(x), float(y), float(z), math.degrees(rx), math.degrees(ry), math.degrees(rz)]


def mat_lista(m):
    """robodk Mat (oszlopvektor) -> lista; verziófüggetlenül."""
    try:
        return [float(sor[0]) for sor in m.rows]
    except Exception:
        return [float(v) for v in m.list()]


def csuklok(item):
    try:
        j = mat_lista(item.Joints())
    except Exception:
        return []
    # A RoboDK üres tömb helyett [0]-t ad vissza
    return [] if (len(j) == 1 and j[0] == 0) else j


def nev_or_ures(item):
    try:
        return item.Name() if item is not None and item.Valid() else ""
    except Exception:
        return ""


def hibakod_leiras(kod):
    """A RoboDK pálya-hibakódjának (InstructionListJoints ERROR oszlop) magyar értelmezése."""
    e = int(round(kod))
    if e == 0:
        return []
    if e == 20:
        return ["Pontatlan számítás nagy tengelymozgás miatt (csökkentsd az időlépést vagy a sebességet)"]
    h = []
    if e % 1000000000 > 99999999:
        h.append("Érvénytelen körmozgás (a MoveC pontjai egy egyenesbe esnek)")
    if e % 100000000 > 9999999:
        h.append("Nem elérhető vagy érvénytelen célpont")
    if e % 10000000 > 999999:
        h.append("180°-hoz közeli forgatás (a forgástengely nem egyértelmű)")
    if e % 1000000 > 99999:
        h.append("Ütközés")
    if e % 1000 > 99:
        h.append("Csukló-szingularitás (J5 áthalad 0°-on)")
    elif e % 10000 > 999:
        if e % 10000 > 3999:
            h.append("Váll-szingularitás közelében (a csukló közel van a J1 tengelyhez)")
        elif e % 10000 > 1999:
            h.append("Könyök-szingularitás közelében (J3 kinyújtva)")
        else:
            h.append("Csukló-szingularitás közelében (J5 ≈ 0°)")
    if e % 10 > 0:
        h.append("A pálya nem hajtható végre (csuklóhatár)")
    if e % 100 > 9:
        h.append("Lineáris mozgás nem lehetséges (csuklóhatár / elérhetetlen pont) - próbálj MoveJ-t")
    return h or ["Ismeretlen hibakód: %d" % e]


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
    return os.path.join(mappa, ascii_nev(allomas_nev, "allomas") + ADATMAPPA_UTOTAG), allomas_nev


def kepernyokep(RDK, fajl):
    """A RoboDK fő 3D nézetének mentése PNG-be."""
    if not KEPERNYOKEPEK:
        return False
    for kamera in (None, 0):  # None: fő 3D nézet (újabb RoboDK), 0: régebbi verziók
        try:
            ok = RDK.Cam2D_Snapshot(fajl, kamera)
            if ok and os.path.isfile(fajl):
                return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Adatgyűjtés
# ---------------------------------------------------------------------------
def robotok_gyujtese(RDK, figy):
    eredmeny = []
    for r in RDK.ItemList(ITEM_TYPE_ROBOT):
        try:
            d = {"nev": r.Name(), "csuklok_fok": csuklok(r)}
            d["szabadsagfok"] = len(d["csuklok_fok"])
            try:
                lim = r.JointLimits()
                d["also_hatar"] = mat_lista(lim[0])
                d["felso_hatar"] = mat_lista(lim[1])
            except Exception as e:
                figy.append("%s: csuklóhatárok nem olvashatók (%s)" % (r.Name(), e))
            try:
                d["bazis_abszolut"] = pose_xyzrxyz(r.PoseAbs())
            except Exception:
                pass
            try:
                d["tcp_aktualis"] = pose_xyzrxyz(r.Pose())  # aktív szerszám az aktív referenciához képest
                d["aktiv_szerszam"] = nev_or_ures(r.getLink(ITEM_TYPE_TOOL))
                d["aktiv_referencia"] = nev_or_ures(r.getLink(ITEM_TYPE_FRAME))
            except Exception:
                pass
            eredmeny.append(d)
        except Exception as e:
            figy.append("Robot adatai nem olvashatók: %s" % e)
    return eredmeny


def egyszeru_elemek(RDK, tipus, figy, tcp=False):
    eredmeny = []
    for it in RDK.ItemList(tipus):
        try:
            d = {"nev": it.Name(), "szulo": nev_or_ures(it.Parent())}
            if tcp:
                try:
                    d["tcp"] = pose_xyzrxyz(it.PoseTool())
                except Exception:
                    d["tcp"] = pose_xyzrxyz(it.Pose())
            else:
                d["relativ"] = pose_xyzrxyz(it.Pose())
            d["abszolut"] = pose_xyzrxyz(it.PoseAbs())
            eredmeny.append(d)
        except Exception as e:
            figy.append("Elem nem olvasható (%s)" % e)
    return eredmeny


def celpontok_gyujtese(RDK, figy):
    eredmeny = []
    for t in RDK.ItemList(ITEM_TYPE_TARGET):
        try:
            d = {"nev": t.Name(), "referencia": nev_or_ures(t.Parent())}
            try:
                d["csuklo_target"] = bool(t.isJointTarget())
            except Exception:
                d["csuklo_target"] = None
            d["poz"] = pose_xyzrxyz(t.Pose())  # a szülő referencia kerethez képest
            d["abszolut"] = pose_xyzrxyz(t.PoseAbs())
            d["csuklok_fok"] = csuklok(t)
            d["robot"] = nev_or_ures(t.getLink(ITEM_TYPE_ROBOT))
            eredmeny.append(d)
        except Exception as e:
            figy.append("Célpont nem olvasható (%s)" % e)
    return eredmeny


def utasitasok_gyujtese(prog, figy):
    lista = []
    try:
        db = prog.InstructionCount()
    except Exception as e:
        figy.append("%s: utasítások száma nem olvasható (%s)" % (prog.Name(), e))
        return lista
    for i in range(db):
        try:
            nev, tipus, mozgas, csuklo_cel, _cel, jnts = prog.Instruction(i)
            d = {"sorszam": i + 1, "nev": nev, "tipus": UTASITAS_TIPUSOK.get(tipus, str(tipus))}
            if tipus == INS_TYPE_MOVE:
                d["mozgas"] = MOZGAS_TIPUSOK.get(mozgas, str(mozgas))
                d["csuklo_cel"] = bool(csuklo_cel)
                if jnts is not None:
                    d["csuklok_fok"] = mat_lista(jnts)
            lista.append(d)
        except Exception as e:
            figy.append("%s: %d. utasítás nem olvasható (%s)" % (prog.Name(), i + 1, e))
    return lista


def frissites(prog, utkozes):
    vi, ido, tav, arany, uzenet = prog.Update(COLLISION_ON if utkozes else COLLISION_OFF)
    return {
        "ervenyes_utasitasok": int(vi), "ciklusido_s": float(ido), "palyahossz_mm": float(tav),
        "ervenyesseg_arany": float(arany), "uzenet": str(uzenet),
    }


def palya_feldolgozasa(mat, dof):
    """InstructionListJoints(flags=4) mátrix -> mintánkénti adatok + statisztika.
    Oszlopok mintánként: J1..Jn, ERROR, MM_STEP, DEG_STEP, MOVE_ID, TIME, X, Y, Z, [v_J1..v_Jn], [a_J1..a_Jn]"""
    sorok = mat.rows
    nval = len(sorok)
    nminta = len(sorok[0]) if nval else 0
    if nval == 0 or nminta == 0:
        return None
    n = dof if dof and nval >= dof + 8 else max(1, (nval - 8) // 3)
    if nval < n + 8:
        raise ValueError("váratlan oszlopszám a pályaadatokban: %d" % nval)
    minta = [[float(sorok[k][j]) for k in range(nval)] for j in range(nminta)]
    van_seb = nval >= 2 * n + 8
    van_gyors = nval >= 3 * n + 8

    ido = [m[n + 4] for m in minta]
    # Biztonsági ellenőrzés: ha az idő oszlop lépésközöket tartalmaz, összegezzük
    monoton = all(ido[i + 1] >= ido[i] - 1e-9 for i in range(len(ido) - 1))
    if not (monoton and ido[-1] > ido[0]):
        osszeg, kum = 0.0, []
        for v in ido:
            osszeg += v
            kum.append(osszeg)
        ido = kum

    adatok = []
    for i, m in enumerate(minta):
        adatok.append({
            "t": ido[i] - ido[0], "j": m[0:n], "hiba": m[n], "move_id": m[n + 3],
            "xyz": m[n + 5:n + 8], "v": m[n + 8:2 * n + 8] if van_seb else None,
            "a": m[2 * n + 8:3 * n + 8] if van_gyors else None,
        })

    # TCP sebesség a pozíciók különbségéből
    hossz = 0.0
    adatok[0]["tcp_v"] = 0.0
    for i in range(1, len(adatok)):
        d = math.sqrt(sum((adatok[i]["xyz"][k] - adatok[i - 1]["xyz"][k]) ** 2 for k in range(3)))
        dt = adatok[i]["t"] - adatok[i - 1]["t"]
        hossz += d
        adatok[i]["tcp_v"] = d / dt if dt > 1e-9 else adatok[i - 1]["tcp_v"]
    return {"n": n, "adatok": adatok, "hossz": hossz, "van_seb": van_seb, "van_gyors": van_gyors}


def palya_statisztika(p, also, felso):
    adatok, n = p["adatok"], p["n"]
    idotartam = adatok[-1]["t"] - adatok[0]["t"]
    stat = {
        "mintak_szama": len(adatok),
        "idotartam_s": idotartam,
        "tcp_palyahossz_mm": p["hossz"],
        "tcp_max_sebesseg_mm_s": max(a["tcp_v"] for a in adatok),
        "tcp_atlag_sebesseg_mm_s": p["hossz"] / idotartam if idotartam > 0 else 0.0,
        "csuklok": [],
    }
    for k in range(n):
        ertekek = [a["j"][k] for a in adatok]
        cs = {"nev": "J%d" % (k + 1), "min": min(ertekek), "max": max(ertekek)}
        cs["mozgastartomany"] = cs["max"] - cs["min"]
        if also and felso and k < len(also) and k < len(felso):
            cs["also_hatar"], cs["felso_hatar"] = also[k], felso[k]
            cs["tartalek_also"] = cs["min"] - also[k]
            cs["tartalek_felso"] = felso[k] - cs["max"]
            teljes = felso[k] - also[k]
            cs["kihasznaltsag_szazalek"] = 100.0 * cs["mozgastartomany"] / teljes if teljes > 0 else None
        if p["van_seb"]:
            cs["max_sebesseg_fok_s"] = max(abs(a["v"][k]) for a in adatok)
        if p["van_gyors"]:
            cs["max_gyorsulas_fok_s2"] = max(abs(a["a"][k]) for a in adatok)
        stat["csuklok"].append(cs)

    hibak = {}
    for a in adatok:
        if int(round(a["hiba"])) != 0:
            for h in hibakod_leiras(a["hiba"]):
                if h not in hibak:
                    hibak[h] = {"leiras": h, "elso_idopont_s": a["t"], "mintak": 0}
                hibak[h]["mintak"] += 1
    stat["hibas_mintak"] = sum(1 for a in adatok if int(round(a["hiba"])) != 0)
    stat["hibak"] = list(hibak.values())

    # Mozgásszakaszok (MOVE_ID szerint, végrehajtási sorrendben)
    szakaszok, kezdo = [], 0
    for i in range(1, len(adatok) + 1):
        if i == len(adatok) or adatok[i]["move_id"] != adatok[kezdo]["move_id"]:
            resz = adatok[kezdo:i]
            veg = adatok[i]["t"] if i < len(adatok) else resz[-1]["t"]
            hossz = 0.0
            for j in range(kezdo + 1, min(i + 1, len(adatok))):
                hossz += math.sqrt(sum((adatok[j]["xyz"][k] - adatok[j - 1]["xyz"][k]) ** 2 for k in range(3)))
            szakaszok.append({
                "sorszam": len(szakaszok) + 1, "move_id": int(round(resz[0]["move_id"])),
                "kezdet_s": resz[0]["t"], "veg_s": veg, "idotartam_s": veg - resz[0]["t"], "hossz_mm": hossz,
            })
            kezdo = i
    stat["szakaszok"] = szakaszok
    return stat


def palya_csv(fajl, p, zona_tavok=None):
    n = p["n"]
    fejlec = ["ido_s"] + ["J%d_fok" % (k + 1) for k in range(n)]
    fejlec += ["TCP_X_mm", "TCP_Y_mm", "TCP_Z_mm", "TCP_sebesseg_mm_s"]
    if p["van_seb"]:
        fejlec += ["v_J%d_fok_s" % (k + 1) for k in range(n)]
    if p["van_gyors"]:
        fejlec += ["a_J%d_fok_s2" % (k + 1) for k in range(n)]
    fejlec += ["mozgas_id", "hibakod"]
    if zona_tavok:
        fejlec.append("zona_tavolsag_mm")
    sorok = []
    for i, a in enumerate(p["adatok"]):
        s = [szam_csv(a["t"], 4)] + [szam_csv(v, 4) for v in a["j"]]
        s += [szam_csv(v, 3) for v in a["xyz"]] + [szam_csv(a["tcp_v"], 3)]
        if p["van_seb"]:
            s += [szam_csv(v, 4) for v in a["v"]]
        if p["van_gyors"]:
            s += [szam_csv(v, 4) for v in a["a"]]
        s += [str(int(round(a["move_id"]))), str(int(round(a["hiba"])))]
        if zona_tavok:
            s.append(szam_csv(zona_tavok[i], 3))
        sorok.append(s)
    csv_iras(fajl, fejlec, sorok)


# ---------------------------------------------------------------------------
# Célpontok elérése, pályaeltérés, tiltott zóna (4x4 mátrixok listákkal, verziófüggetlenül)
# ---------------------------------------------------------------------------
def m_lista(pose):
    return [[float(v) for v in sor] for sor in pose.rows]


def m_szor(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def m_inv(A):
    """Merev test transzformációjának inverze."""
    R = [[A[j][i] for j in range(3)] for i in range(3)]
    t = [-sum(R[i][k] * A[k][3] for k in range(3)) for i in range(3)]
    return [R[0] + [t[0]], R[1] + [t[1]], R[2] + [t[2]], [0.0, 0.0, 0.0, 1.0]]


def m_pont(A, p):
    return [A[i][0] * p[0] + A[i][1] * p[1] + A[i][2] * p[2] + A[i][3] for i in range(3)]


def tav(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def legkozelebbi_pont(p, a, b):
    """Az a-b szakasz p-hez legközelebbi pontja."""
    ab = [b[i] - a[i] for i in range(3)]
    l2 = sum(v * v for v in ab)
    u = 0.0 if l2 < 1e-18 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / l2))
    return [a[i] + u * ab[i] for i in range(3)]


def tcp_fuggveny(robot):
    """q -> a TCP helyzete a robot bázisához képest [mm] (direkt kinematika + aktív szerszám)."""
    try:
        sz = m_lista(robot.PoseTool())
    except Exception:
        sz = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    def tcp(q):
        return m_pont(m_lista(robot.SolveFK([float(v) for v in q])), [sz[0][3], sz[1][3], sz[2][3]])
    return tcp


class Pozicio(object):
    """A minták TCP-pozíciója a robot bázisában. Ha a RoboDK pályaadataiban lévő XYZ is ebben a
    rendszerben van, azt használja, különben direkt kinematikával számol (gyorsítótárral)."""

    def __init__(self, p, tcp):
        self.adatok, self.tcp, self.tar = p["adatok"], tcp, {}
        elso, utolso = self.adatok[0], self.adatok[-1]
        self.xyz_jo = tav(tcp(elso["j"]), elso["xyz"]) < 0.01 and tav(tcp(utolso["j"]), utolso["xyz"]) < 0.01

    def __call__(self, i):
        if self.xyz_jo:
            return self.adatok[i]["xyz"]
        if i not in self.tar:
            self.tar[i] = self.tcp(self.adatok[i]["j"])
        return self.tar[i]


def celpontnev(utasitas_nev):
    m = re.search(r"\(([^()]*)\)\s*$", utasitas_nev)
    return m.group(1).strip() if m else utasitas_nev


def celpont_elemzes(p, utasitasok, tcp, poz):
    """Végigköveti a pályán a mozgásutasítások célpontjait: érkezés, indulás, eltérés, szakaszadatok."""
    adatok, n = p["adatok"], p["n"]
    N = len(adatok)
    mozgasok = [u for u in utasitasok if u.get("mozgas") and len(u.get("csuklok_fok") or []) >= n]
    if not mozgasok:
        return None

    def jt(i, q):
        return max(abs(adatok[i]["j"][k] - q[k]) for k in range(n))

    celok = [tcp(u["csuklok_fok"][:n]) for u in mozgasok]  # a célpontok TCP-helyzete a robot bázisában

    def tv(i, k):
        return tav(poz(i), celok[k])

    # 1. menet: megálló (pontos) célpontok, sorrendben
    tal = [None] * len(mozgasok)
    kezd = 0
    for k in range(len(mozgasok)):
        if k > 0 and tal[k - 1] and tav(celok[k], celok[k - 1]) <= CELPONT_TUR_MM:
            tal[k] = (tal[k - 1][1], tal[k - 1][1], tal[k - 1][2])  # ugyanaz a célpont még egyszer: nulla hosszú mozgás
            continue
        i = kezd
        while i < N and tv(i, k) > CELPONT_TUR_MM:
            i += 1
        if i < N:
            j = i
            while j + 1 < N and tv(j + 1, k) <= CELPONT_TUR_MM:
                j += 1
            tal[k] = (min(range(i, j + 1), key=lambda s: tv(s, k)), j, True)
            kezd = min(j + 1, N - 1)  # a következő célpontot csak az indulás után keressük
    # 2. menet: lekerekített célpontok (ahol a robot nem áll meg): legközelebbi minta a szomszédok között
    for k in range(len(mozgasok)):
        if tal[k] is None:
            lo = next((tal[m][1] for m in range(k - 1, -1, -1) if tal[m]), 0)
            hi = max(lo, next((tal[m][0] for m in range(k + 1, len(mozgasok)) if tal[m]), N - 1))
            i = min(range(lo, hi + 1), key=lambda s: tv(s, k))
            tal[k] = (i, i, False)

    latogatasok, elert = [], []
    elozo_dep, elozo_P = 0, None
    for k, u in enumerate(mozgasok):
        i_arr, i_dep, megallt = tal[k]
        q = u["csuklok_fok"][:n]
        P = celok[k]
        # elért pont: a mintapontok közti szakaszok P-hez legközelebbi pontja (a mintavételnél pontosabb)
        lo, hi = max(0, i_arr - 6), min(N - 1, i_arr + 6)
        pontok = [poz(s) for s in range(lo, hi + 1)]
        jeloltek = [(legkozelebbi_pont(P, pontok[s], pontok[s + 1]), tav(pontok[s], pontok[s + 1]))
                    for s in range(len(pontok) - 1)] or [(pontok[0], 0.0)]
        Q, felbontas = min(jeloltek, key=lambda x: tav(P, x[0]))  # felbontás: a két szomszédos minta távolsága
        s0 = elozo_dep if k > 0 else 0
        d = {
            "sorszam": k + 1, "celpont": celpontnev(u["nev"]), "utasitas": u["nev"], "mozgas": u["mozgas"],
            "megallt": megallt, "erkezes_s": adatok[i_arr]["t"], "indulas_s": adatok[i_dep]["t"],
            "szakaszido_s": adatok[i_arr]["t"] - adatok[s0]["t"],
            "szakasz_hossz_mm": sum(tav(adatok[s]["xyz"], adatok[s - 1]["xyz"]) for s in range(s0 + 1, i_arr + 1)),
            "szakasz_max_sebesseg_mm_s": max(adatok[s]["tcp_v"] for s in range(s0, i_arr + 1)),
            "elteres_mm": tav(P, Q),
            "felbontas_mm": felbontas,
            "csuklo_elteres_fok": jt(i_arr, q),
            "csuklo_valtozas_fok": [adatok[i_arr]["j"][m] - adatok[s0]["j"][m] for m in range(n)],
        }
        if "MoveL" in u["mozgas"] and elozo_P is not None:
            # csak a két célpont közötti belső minták: a megállás körüli minták már a szomszédos szakaszon lehetnek
            belso = range(s0 + 1, i_arr)
            d["palya_elteres_mm"] = max([tav(poz(s), legkozelebbi_pont(poz(s), elozo_P, P)) for s in belso] or [0.0])
        latogatasok.append(d)
        if megallt:  # ismételhetőség: ugyanannak a megálló célpontnak az ismételt elérései
            elert.append((d["celpont"], Q))
        elozo_dep, elozo_P = i_dep, P

    def kulcs(s):
        return ascii_nev(s).lower()

    csoportok = {}
    for nev, Q in elert:
        csoportok.setdefault(nev, []).append(Q)
    ismetelt = [pts for pts in csoportok.values() if len(pts) > 1]
    megallo = [d["elteres_mm"] for d in latogatasok if d["megallt"]]
    lekerekitett = [d["elteres_mm"] for d in latogatasok if not d["megallt"]]
    palya = [d["palya_elteres_mm"] for d in latogatasok if "palya_elteres_mm" in d]
    eredmeny = {
        "latogatasok": latogatasok,
        "max_elteres_megallo_mm": max(megallo) if megallo else None,
        "max_elteres_lekerekitett_mm": max(lekerekitett) if lekerekitett else None,
        "max_palya_elteres_mm": max(palya) if palya else None,
        "ismetlesi_elteres_mm": max(max(tav(a, b) for a in pts for b in pts) for pts in ismetelt) if ismetelt else None,
        "kezdo_veg_elteres_mm": tav(adatok[0]["xyz"], adatok[-1]["xyz"]),
        "pozicio_forras": "RoboDK pályaadat (XYZ)" if poz.xyz_jo else "direkt kinematika",
    }
    fel = next((d for d in latogatasok if "felvet" in kulcs(d["celpont"]) and "felett" not in kulcs(d["celpont"])), None)
    if fel:
        le = next((d for d in latogatasok if d["sorszam"] > fel["sorszam"]
                   and "lerak" in kulcs(d["celpont"]) and "felett" not in kulcs(d["celpont"])), None)
        if le:
            eredmeny["felveteltol_lerakasig_s"] = le["erkezes_s"] - fel["indulas_s"]
    return eredmeny


def zonak_gyujtese(RDK, figy):
    """Tiltott zónák: olyan objektumok, amelyek nevében szerepel valamelyik ZONA_KULCSSZAVAK elem.
    A doboz méretét a cella_epito.py / doboz_letrehozasa.py tárolja el az objektumban; ha nincs
    ilyen adat, a névből olvassa ki (pl. "Tiltott_zona 60x60x50": a doboz alaplapjának közepe az origó)."""
    zonak = []
    for obj in RDK.ItemList(ITEM_TYPE_OBJECT):
        nev = obj.Name()
        if not any(k in ascii_nev(nev).lower() for k in ZONA_KULCSSZAVAK):
            continue
        doboz = None
        try:
            nyers = obj.getParam("ZonaDoboz")
            if nyers:
                doboz = json.loads(nyers.decode("utf-8") if isinstance(nyers, bytes) else nyers)
        except Exception:
            doboz = None
        if doboz is None:
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)", nev)
            if m:
                a, b, c = [float(x.replace(",", ".")) for x in m.groups()]
                doboz = {"min": [-a / 2, -b / 2, 0.0], "max": [a / 2, b / 2, c]}
        if doboz is None:
            figy.append("%s: a tiltott zóna mérete nem ismert (nevezd el pl. így: 'Tiltott_zona 60x60x50') - "
                        "a belépést csak az ütközésvizsgálat jelzi." % nev)
            continue
        zonak.append({"nev": nev, "abs": m_lista(obj.PoseAbs()), "min": doboz["min"], "max": doboz["max"]})
    return zonak


def doboz_tav(p, mn, mx):
    """Előjeles távolság egy tengelyekkel párhuzamos doboztól: pozitív = kívül, negatív = belül [mm]."""
    kulso = math.sqrt(sum(max(mn[i] - p[i], 0.0, p[i] - mx[i]) ** 2 for i in range(3)))
    if kulso > 0:
        return kulso
    return -min(min(p[i] - mn[i], mx[i] - p[i]) for i in range(3))


def zona_elemzes(robot, zonak, p, poz):
    """A TCP távolsága a legközelebbi tiltott zónától, mintánként."""
    B = m_lista(robot.PoseAbs())
    atvaltok = [(z, m_szor(m_inv(z["abs"]), B)) for z in zonak]  # robotbázis -> zóna saját rendszere
    tavok, legkozelebbi = [], []
    for i in range(len(p["adatok"])):
        P = poz(i)
        ertekek = [(doboz_tav(m_pont(M, P), z["min"], z["max"]), z["nev"]) for z, M in atvaltok]
        d, nev = min(ertekek)
        tavok.append(d)
        legkozelebbi.append(nev)
    i = min(range(len(tavok)), key=lambda k: tavok[k])
    return tavok, {"zona": legkozelebbi[i], "min_tavolsag_mm": tavok[i], "ido_s": p["adatok"][i]["t"],
                   "belepett": tavok[i] <= 0.0}


def palyakep(RDK, robot, p, fajl, figy):
    if not KEPERNYOKEPEK:
        return False
    szellem = False
    if robot is not None and SZELLEM_ROBOTOK > 0 and p and len(p["adatok"]) > 1:
        try:
            db = min(SZELLEM_ROBOTOK, len(p["adatok"]))
            idx = sorted(set(int(round(i * (len(p["adatok"]) - 1) / max(1, db - 1))) for i in range(db)))
            robot.ShowSequence([p["adatok"][i]["j"] for i in idx], SEQ_RESET | SEQ_ROBOT_JOINTS | SEQ_COLOR_TRANSPARENT, 20000)
            szellem = True
            time.sleep(1.0)
        except Exception as e:
            figy.append("Szellemrobotok nem jeleníthetők meg (%s) - a kép ezek nélkül készül" % e)
    ok = kepernyokep(RDK, fajl)
    if szellem:
        try:
            robot.ShowSequence([], SEQ_RESET, 0)
        except Exception:
            pass
    return ok


def program_meres(RDK, prog, kimenet, foglalt, figy, zonak):
    robot = prog.getLink(ITEM_TYPE_ROBOT)
    robot = robot if robot.Valid() else None
    eredeti = csuklok(robot) if robot is not None else None
    try:
        return _program_meres(RDK, prog, robot, kimenet, foglalt, figy, zonak)
    finally:
        if eredeti:
            try:
                robot.setJoints(eredeti)  # a robot visszaáll a mérés előtti helyzetébe
            except Exception:
                pass


def _program_meres(RDK, prog, robot, kimenet, foglalt, figy, zonak):
    nev = prog.Name()
    d = {"nev": nev, "robot": nev_or_ures(robot), "utasitasok": utasitasok_gyujtese(prog, figy)}
    dof, also, felso = 0, None, None
    if robot is not None:
        dof = len(csuklok(robot))
        try:
            lim = robot.JointLimits()
            also, felso = mat_lista(lim[0]), mat_lista(lim[1])
        except Exception:
            pass

    if robot is not None and KEZDES_ELSO_CELPONTBOL:
        elso = next((u["csuklok_fok"] for u in d["utasitasok"] if u.get("mozgas") and u.get("csuklok_fok")), None)
        if elso and len(elso) >= dof:
            try:
                robot.setJoints(elso[:dof])
                d["kezdohelyzet"] = "a program első célpontja"
            except Exception as e:
                figy.append("%s: a robot nem állítható a kezdőhelyzetbe (%s)" % (nev, e))

    print("  - %s: becsült ciklusidő és érvényesség..." % nev)
    try:
        d["frissites"] = frissites(prog, False)
    except Exception as e:
        figy.append("%s: a program nem frissíthető / nem ellenőrizhető (%s)" % (nev, e))
        return d
    if UTKOZESVIZSGALAT:
        print("  - %s: ütközésvizsgálat..." % nev)
        try:
            u = frissites(prog, True)
            u["utkozesmentes"] = u["ervenyesseg_arany"] >= d["frissites"]["ervenyesseg_arany"] - 1e-9
            d["utkozes"] = u
        except Exception as e:
            figy.append("%s: ütközésvizsgálat sikertelen (%s)" % (nev, e))

    print("  - %s: időalapú pálya-mintavétel..." % nev)
    ciklus = d["frissites"]["ciklusido_s"]
    dt = IDOLEPES_S or max(0.002, min(0.1, ciklus / float(MAX_MINTASZAM) if ciklus > 0 else 0.05))
    try:
        uzenet, mat, allapot = prog.InstructionListJoints(mm_step=1, deg_step=1, flags=4, time_step=dt)
        p = palya_feldolgozasa(mat, dof)
    except Exception as e:
        figy.append("%s: a pálya nem mintavételezhető (%s)" % (nev, e))
        p = None
        uzenet, allapot = "", None
    if p is None:
        return d

    stat = palya_statisztika(p, also, felso)
    celpontok, zona_tavok = None, None
    if robot is not None:
        print("  - %s: célpontok elérése, pontosság, tiltott zóna..." % nev)
        try:
            tcp = tcp_fuggveny(robot)
            poz = Pozicio(p, tcp)
            elemzes = celpont_elemzes(p, d["utasitasok"], tcp, poz)
            if elemzes:
                celpontok = elemzes.pop("latogatasok")
                stat.update(elemzes)
            if zonak:
                zona_tavok, stat["zona"] = zona_elemzes(robot, zonak, p, poz)
        except Exception as e:
            figy.append("%s: a célpont- / zónaelemzés nem sikerült (%s)" % (nev, e))

    fajlnev = egyedi_nev("palya_" + ascii_nev(nev, "program"), foglalt)
    palya_csv(os.path.join(kimenet, fajlnev + ".csv"), p, zona_tavok)
    d["palya"] = {
        "csv": fajlnev + ".csv", "idolepes_s": dt, "uzenet": str(uzenet), "allapot": allapot,
        "statisztika": stat,
    }
    if celpontok:
        d["palya"]["celpontok"] = celpontok
    kep = os.path.join("kepek", fajlnev + ".png")
    d["palya"]["kep"] = kep.replace("\\", "/")  # kézzel ide mentett kép is bekerül a jegyzőkönyvbe
    if not palyakep(RDK, robot, p, os.path.join(kimenet, kep), figy) and KEPERNYOKEPEK:
        figy.append("%s: a pályakép nem készült el - mentsd kézzel ide: %s" % (nev, os.path.join(kimenet, kep)))
    return d


def megnevezes_bekerese():
    """A mérés neve (opcionális). None = a felhasználó a Mégse gombot nyomta."""
    kerdes = ("A mérés megnevezése (nem kötelező), pl. „v = 300 mm/s” vagy „végleges változat”.\n"
              "Több mérésnél a jegyzőkönyv ezek alapján hasonlítja össze őket.")
    try:
        from robodk import robodialogs
        return robodialogs.InputDialog(kerdes, "", title="Mérések rögzítése")
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import simpledialog
        ablak = tkinter.Tk()
        ablak.withdraw()
        ablak.attributes("-topmost", True)
        valasz = simpledialog.askstring("Mérések rögzítése", kerdes, initialvalue="", parent=ablak)
        ablak.destroy()
        return valasz
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Főprogram
# ---------------------------------------------------------------------------
def main():
    RDK = robolink.Robolink()
    figy = []
    megnevezes = megnevezes_bekerese() if MEGNEVEZES_KERESE else ""
    if megnevezes is None:  # Mégse
        print("A mérés megszakítva.")
        return
    gyoker, allomas_nev = adatmappa(RDK)
    idobelyeg = datetime.datetime.now()
    kimenet = os.path.join(gyoker, "meres_" + idobelyeg.strftime("%Y%m%d_%H%M%S"))
    i = 2
    while os.path.exists(kimenet):  # ugyanabban a másodpercben indított második mérés
        kimenet = os.path.join(gyoker, "meres_%s_%d" % (idobelyeg.strftime("%Y%m%d_%H%M%S"), i))
        i += 1
    os.makedirs(os.path.join(kimenet, "kepek"))

    try:
        RDK.ShowMessage("Mérések rögzítése folyamatban...", False)
    except Exception:
        pass
    print("Mérések rögzítése ide: " + kimenet)

    try:
        verzio = RDK.Version()
    except Exception:
        verzio = "ismeretlen"
    adat = {
        "formatum_verzio": 1,
        "letrehozva": idobelyeg.strftime("%Y-%m-%d %H:%M:%S"),
        "megnevezes": megnevezes.strip(),
        "allomas": {
            "nev": allomas_nev, "mappa": os.path.dirname(gyoker), "robodk_verzio": verzio,
            "python_verzio": sys.version.split()[0],
        },
        "beallitasok": {"utkozesvizsgalat": UTKOZESVIZSGALAT, "idolepes_s": IDOLEPES_S},
    }
    try:
        adat["allomas"]["fajl"] = str(RDK.getParam("FILE_OPENSTATION") or "")
    except Exception:
        pass

    print("Állomás elemeinek beolvasása...")
    adat["robotok"] = robotok_gyujtese(RDK, figy)
    adat["szerszamok"] = egyszeru_elemek(RDK, ITEM_TYPE_TOOL, figy, tcp=True)
    adat["referenciak"] = egyszeru_elemek(RDK, ITEM_TYPE_FRAME, figy)
    adat["objektumok"] = egyszeru_elemek(RDK, ITEM_TYPE_OBJECT, figy)
    adat["celpontok"] = celpontok_gyujtese(RDK, figy)

    adat["kepek"] = {"allomas": "kepek/allomas.png"}  # kézzel ide mentett kép is bekerül a jegyzőkönyvbe
    if not kepernyokep(RDK, os.path.join(kimenet, "kepek", "allomas.png")) and KEPERNYOKEPEK:
        figy.append("Az állomásról nem készült képernyőkép - mentsd kézzel (Windows: Win+Shift+S) ide: "
                    + os.path.join(kimenet, "kepek", "allomas.png"))

    zonak = zonak_gyujtese(RDK, figy)
    adat["tiltott_zonak"] = [{"nev": z["nev"], "min": z["min"], "max": z["max"]} for z in zonak]

    print("Programok mérése...")
    foglalt = set()
    adat["programok"] = []
    kihagyott = []
    for prog in RDK.ItemList(ITEM_TYPE_PROGRAM):
        if KIHAGYOTT_ELOTAG and prog.Name().lower().startswith(KIHAGYOTT_ELOTAG.lower()):
            kihagyott.append(prog.Name())
            continue
        adat["programok"].append(program_meres(RDK, prog, kimenet, foglalt, figy, zonak))
    if kihagyott:
        adat["kihagyott_programok"] = kihagyott
        print("Kihagyott programok (%s előtag): %s" % (KIHAGYOTT_ELOTAG, ", ".join(kihagyott)))

    # Excel-barát összesítő táblák
    csv_iras(
        os.path.join(kimenet, "celpontok.csv"),
        ["nev", "referencia", "csuklo_target", "X_mm", "Y_mm", "Z_mm", "Rx_fok", "Ry_fok", "Rz_fok", "csuklok_fok"],
        [[c["nev"], c["referencia"], {True: "igen", False: "nem"}.get(c["csuklo_target"], "")]
         + [szam_csv(v, 3) for v in c["poz"]]
         + [" | ".join(szam_csv(v, 3) for v in c["csuklok_fok"])] for c in adat["celpontok"]],
    )
    sorok = []
    for p in adat["programok"]:
        f, u = p.get("frissites", {}), p.get("utkozes", {})
        s = p.get("palya", {}).get("statisztika", {})
        sorok.append([
            p["nev"], p["robot"], len(p["utasitasok"]), szam_csv(f.get("ciklusido_s"), 3),
            szam_csv(f.get("palyahossz_mm"), 1), szam_csv(100.0 * f["ervenyesseg_arany"], 1) if f else "",
            {True: "nincs", False: "VAN"}.get(u.get("utkozesmentes"), "nem vizsgált"),
            szam_csv(s.get("tcp_max_sebesseg_mm_s"), 1), szam_csv(s.get("felveteltol_lerakasig_s"), 3),
            szam_csv(s.get("max_elteres_megallo_mm"), 4), szam_csv(s.get("max_palya_elteres_mm"), 3),
            szam_csv(s.get("kezdo_veg_elteres_mm"), 4), szam_csv((s.get("zona") or {}).get("min_tavolsag_mm"), 2),
            f.get("uzenet", ""),
        ])
    csv_iras(
        os.path.join(kimenet, "programok.csv"),
        ["program", "robot", "utasitasok", "ciklusido_s", "palyahossz_mm", "ervenyesseg_szazalek",
         "utkozes", "tcp_max_sebesseg_mm_s", "felveteltol_lerakasig_s", "max_celpont_elteres_mm",
         "max_palya_elteres_mm", "kezdo_veg_elteres_mm", "zona_min_tavolsag_mm", "robodk_uzenet"],
        sorok,
    )
    for p in adat["programok"]:  # célpontonkénti részletek programonként
        cp = (p.get("palya") or {}).get("celpontok")
        if cp:
            csv_iras(
                os.path.join(kimenet, p["palya"]["csv"].replace("palya_", "celpontok_", 1)),
                ["sorszam", "celpont", "mozgas", "megallt", "erkezes_s", "indulas_s", "szakaszido_s",
                 "szakasz_hossz_mm", "elteres_mm", "felbontas_mm", "palya_elteres_mm"]
                + ["dJ%d_fok" % (k + 1) for k in range(len(cp[0]["csuklo_valtozas_fok"]))],
                [[c["sorszam"], c["celpont"], c["mozgas"], "igen" if c["megallt"] else "nem",
                  szam_csv(c["erkezes_s"], 3), szam_csv(c["indulas_s"], 3), szam_csv(c["szakaszido_s"], 3),
                  szam_csv(c["szakasz_hossz_mm"], 2), szam_csv(c["elteres_mm"], 4), szam_csv(c["felbontas_mm"], 3),
                  szam_csv(c.get("palya_elteres_mm"), 3)] + [szam_csv(v, 3) for v in c["csuklo_valtozas_fok"]]
                 for c in cp],
            )

    adat["figyelmeztetesek"] = figy
    with open(os.path.join(kimenet, "meresek.json"), "w", encoding="utf-8") as f:
        json.dump(adat, f, ensure_ascii=False, indent=2)

    osszegzes = "Mérések elmentve (%d program, %d célpont):\n%s" % (
        len(adat["programok"]), len(adat["celpontok"]), kimenet)
    if figy:
        osszegzes += "\n\nFigyelmeztetések (%d db) - részletek a meresek.json-ban." % len(figy)
    print(osszegzes)
    for w in figy:
        print("  ! " + w)
    try:
        RDK.ShowMessage(osszegzes, True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
