# -*- coding: utf-8 -*-
"""
CELLAÉPÍTŐ - a 3 mérési feladat RoboDK-cellájának és programjainak automatikus felépítése
==========================================================================================

Ez a szkript MINTAMEGOLDÁST épít: a cellát (keretek, asztal, munkadarab, tiltott zóna, szerszám),
a célpontokat és a sebességváltozatokat tartalmazó programokat. Az UTMUTATO.md leírja, hogyan
csinálod meg ugyanezt kézzel. A szkripttel ellenőrizheted a saját megoldásodat, vagy időt
spórolhatsz vele.

Használat:
  1. File -> New Station, majd töltsd be a robotot (File -> Open online library):
        1. feladat: Universal Robots UR5e           (modern, 6 tengelyes kollaboratív robot)
        2. feladat: ABB IRB 120-3/0.6               (6 tengelyes csuklós ipari robot)
        3. feladat: KUKA LBR iiwa 7 R800            (7 tengelyes; erre épül az orvosi KUKA LBR Med)
     Más 6 vagy 7 tengelyes robottal is működik: a szkript a robot hatótávolságához igazítja a cellát.
  2. Mentsd el az állomást (pl. Feladat1.rdk), hogy a feladat.txt a jó helyre kerüljön.
  3. Húzd be ezt a fájlt a RoboDK-ba, kattints rá duplán, és válaszd ki a feladat számát.

A szkript a feladat szövegét a <állomás>_dokumentacio/feladat.txt fájlba írja, így az a
jegyzőkönyvbe is bekerül. Ha a cellát újraépíted, a korábban létrehozott elemeket törli.
"""

import json
import math
import os
import re
import unicodedata

try:
    from robodk import robolink, robomath  # RoboDK 5.4 és újabb
except ImportError:  # régebbi RoboDK verziók
    import robolink
    import robodk as robomath

FELADAT = None  # 1, 2 vagy 3 - None esetén a szkript megkérdezi
ADATMAPPA_UTOTAG = "_dokumentacio"

ITEM_TYPE_ROBOT = robolink.ITEM_TYPE_ROBOT
ITEM_TYPE_FRAME = robolink.ITEM_TYPE_FRAME
ITEM_TYPE_TOOL = robolink.ITEM_TYPE_TOOL
ITEM_TYPE_OBJECT = robolink.ITEM_TYPE_OBJECT
ITEM_TYPE_PROGRAM = robolink.ITEM_TYPE_PROGRAM
ITEM_TYPE_PROGRAM_PYTHON = getattr(robolink, "ITEM_TYPE_PROGRAM_PYTHON", 10)
COLLISION_ON = getattr(robolink, "COLLISION_ON", 1)
COLLISION_OFF = getattr(robolink, "COLLISION_OFF", 0)
PROGRAMHIVAS = getattr(robolink, "INSTRUCTION_CALL_PROGRAM", 0)

# Színek [R, G, B, átlátszatlanság]
SZURKE = [0.82, 0.82, 0.80, 1.0]
FEHER = [0.97, 0.97, 0.95, 1.0]
KEK = [0.16, 0.47, 0.84, 1.0]
ZOLD = [0.05, 0.64, 0.05, 0.7]
PIROS_ATLATSZO = [0.82, 0.23, 0.23, 0.35]
SZERSZAM_SZIN = [0.35, 0.35, 0.38, 1.0]

# Sebességszintek: (lineáris [mm/s], lineáris gyorsulás [mm/s²], csukló [°/s], csuklógyorsulás [°/s²])
SEBESSEG_F1 = {"lassu": (100, 250, 30, 60), "kozepes": (300, 800, 90, 180), "gyors": (800, 2000, 180, 400)}
SEBESSEG_F2 = {"lassu": (50, 200, 30, 100), "gyors": (500, 2000, 180, 500)}
SEBESSEG_F3 = {"lassu": (10, 50, 10, 40), "kozepes": (50, 250, 30, 100), "gyors": (200, 1000, 90, 300)}
LEKEREKITES_F2_MM = 10  # 2. feladat: lekerekítés a négyzet sarkainál (a pontosság-sebesség kísérlethez)
LEKEREKITES_F3_MM = 15  # 3. feladat: lekerekítés csak az átmeneti (biztonsági) pontokban

FELADATSZOVEGEK = {
    1: """Modern robot: Pick & Place rendszer
Feladat: Programozz be egy modern, 6 tengelyes robotkart, amely egy munkadarabot felvesz egy kiindulási pontról, majd egy másik helyre áthelyezi.
A feladat célja:
- a robot mozgásának megismerése,
- pozíciók rögzítése,
- a movej és movel mozgások használata,
- a robot sebességének és gyorsulásának vizsgálata.
Mérendő adatok:
- A robot által megtett idő a felvételtől a lerakásig.
- A mozgás során megtett út.
- A robot maximális sebessége.
- A movej és movel mozgások végrehajtási idejének különbsége.
Feladat menete:
- Helyezz el egy munkadarabot a kezdőpozícióban.
- Programozd be a robotot úgy, hogy megközelítse a munkadarabot.
- Fogja meg, majd emelje fel.
- Vigye át a megadott célpozícióba.
- Engedje el.
- Ismételd meg a feladatot különböző sebességértékekkel.
- Jegyezd fel a mérési eredményeket, majd hasonlítsd össze őket.
Értékelés: A feladat akkor sikeres, ha a robot ütközés nélkül, pontosan és ismételhető módon helyezi át a munkadarabot.""",
    2: """Csuklós robot: pályakövetés
Feladat: Programozz egy csuklós robotot úgy, hogy a robot végrehajtó szerve egy előre meghatározott, például négyzet vagy háromszög alakú pályát kövessen.
A feladat célja:
- a csuklós robot tengelyeinek megismerése,
- a koordinátarendszer használata,
- pontos pozíciók meghatározása,
- a robot pályakövetési pontosságának vizsgálata.
Mérendő adatok:
- Az egyes pályaszakaszok végrehajtási ideje.
- A kezdő- és végpozíció közötti eltérés.
- A robot egyes tengelyeinek elfordulása.
- A különböző sebességek hatása a pályakövetés pontosságára.
Feladat menete:
- Határozz meg négy pontot egy négyzet alakú pályán.
- Programozd be a robotot, hogy a pontokat sorrendben érintse.
- Először lassú sebességgel hajtsd végre a mozgást.
- Mérd meg a végrehajtási időt.
- Ismételd meg nagyobb sebességgel.
- Hasonlítsd össze a két mérés eredményét.
- Vizsgáld meg, hogy a nagyobb sebesség okoz-e nagyobb pozicionálási eltérést.
Értékelés: Értékeld a robot pontosságát, ismételhetőségét és a sebességváltoztatás hatását a mozgásra.""",
    3: """Orvosi robot: precíziós mozgás
Feladat: Szimulálj egy orvosi robotkarhoz hasonló precíziós feladatot. A robotnak egy virtuális műtéti területen meghatározott pontokat kell egymás után elérnie úgy, hogy közben ne érintse meg a tiltott területet.
A feladat célja:
- a nagy pontosságú robotmozgás gyakorlása,
- a kis mozgások és sebességek vizsgálata,
- az akadálykerülés megismerése,
- az ismételhetőség vizsgálata.
Mérendő adatok:
- Az egyes pontok elérésének pontossága.
- A teljes feladat végrehajtási ideje.
- A végrehajtó szerv maximális eltérése a kívánt pozíciótól.
- A különböző sebességbeállítások hatása a pontosságra.
Feladat menete:
- Jelölj ki egy kiindulási pontot és három célpontot.
- Helyezz el egy virtuális akadályt vagy tiltott zónát.
- Programozd be a robotot úgy, hogy a három célpontot megfelelő sorrendben érje el.
- A robot nem léphet be a tiltott területre.
- Végezze el a mozgást alacsony sebességgel.
- Ismételd meg nagyobb sebességgel.
- Hasonlítsd össze a pontosságot és a végrehajtási időt.
Értékelés: A robotnak minden célpontot a lehető legkisebb eltéréssel kell elérnie, miközben az akadályt elkerüli. A mérés alapján állapítsd meg, hogyan befolyásolja a sebesség a precíziós robotmozgást.""",
}


# ---------------------------------------------------------------------------
# Általános segédfüggvények
# ---------------------------------------------------------------------------
def ascii_nev(szoveg, alap="elem"):
    s = unicodedata.normalize("NFKD", str(szoveg))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")
    return s or alap


def lista(m):
    """robodk Mat (oszlopvektor) -> lista; üres vagy hibás eredménynél üres lista."""
    try:
        return [float(sor[0]) for sor in m.rows if len(sor) > 0]
    except Exception:
        try:
            return [float(v) for v in m.list()]
        except Exception:
            return []


def nev_szerint(RDK, nev, tipus):
    """Pontos névegyezés (az RDK.Item() hasonló nevű elemet is visszaadhatna)."""
    for it in RDK.ItemList(tipus):
        if it.Name() == nev:
            return it
    return None


def le_szerszam():
    """Lefelé néző szerszám: a szerszám Z tengelye a keret -Z irányába mutat."""
    return robomath.rotx(math.pi)


def poz(x, y, z):
    return robomath.transl(x, y, z) * le_szerszam()


def adatmappa(RDK):
    allomas_nev = ""
    try:
        allomas_nev = RDK.ActiveStation().Name()
    except Exception:
        pass
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


def feladat_valasztas(RDK):
    if FELADAT in (1, 2, 3):
        return FELADAT
    opciok = ["1. Pick & Place (UR5e)", "2. Négyzet alakú pálya (ABB IRB 120)", "3. Precíziós mozgás tiltott zónával (KUKA LBR iiwa)"]
    try:
        from robodk import robodialogs
        v = robodialogs.InputDialog("Melyik feladat celláját építsem fel?", [0, opciok], title="Cellaépítő")
        if v is None:
            return None
        valasztott = v[0] if isinstance(v, (list, tuple)) else v
        if isinstance(valasztott, str):
            return opciok.index(valasztott) + 1 if valasztott in opciok else int(valasztott.strip()[0])
        return int(valasztott) + 1
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import simpledialog
        ablak = tkinter.Tk()
        ablak.withdraw()
        v = simpledialog.askinteger("Cellaépítő", "Melyik feladat? (1, 2 vagy 3)\n" + "\n".join(opciok),
                                    minvalue=1, maxvalue=3, parent=ablak)
        ablak.destroy()
        return v
    except Exception:
        pass
    m = re.search(r"([123])", RDK.ActiveStation().Name())  # végső eset: az állomás nevéből
    return int(m.group(1)) if m else None


def igen_nem(kerdes):
    try:
        from robodk import robodialogs
        return bool(robodialogs.ShowMessageYesNo(kerdes, "Cellaépítő"))
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import messagebox
        ablak = tkinter.Tk()
        ablak.withdraw()
        v = messagebox.askyesno("Cellaépítő", kerdes, parent=ablak)
        ablak.destroy()
        return v
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Geometria: dobozok, hengerek háromszöghálója (normálvektorokkal)
# ---------------------------------------------------------------------------
def _sokszog_haromszogek(csucsok, normal):
    """Konvex sokszög -> háromszögek (legyező), a körüljárás a normálhoz igazítva. [x,y,z,nx,ny,nz] pontok."""
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


def doboz_haromszogek(dx, dy, dz, kx=0.0, ky=0.0, z0=0.0):
    """Doboz: x ∈ kx±dx/2, y ∈ ky±dy/2, z ∈ [z0, z0+dz]."""
    x0, x1, y0, y1, z1 = kx - dx / 2.0, kx + dx / 2.0, ky - dy / 2.0, ky + dy / 2.0, z0 + dz
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
        pontok += _sokszog_haromszogek(csucsok, normal)
    return pontok


def henger_haromszogek(r, z0, z1, oldalak=12):
    """Henger közelítése szabályos sokszög alapú hasábbal (tengelye a Z tengely)."""
    kor = [(r * math.cos(2 * math.pi * i / oldalak), r * math.sin(2 * math.pi * i / oldalak)) for i in range(oldalak)]
    pontok = _sokszog_haromszogek([(x, y, z0) for x, y in kor], (0, 0, -1))
    pontok += _sokszog_haromszogek([(x, y, z1) for x, y in kor], (0, 0, 1))
    for i in range(oldalak):
        (xa, ya), (xb, yb) = kor[i], kor[(i + 1) % oldalak]
        szog = 2 * math.pi * (i + 0.5) / oldalak
        pontok += _sokszog_haromszogek([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)],
                                       (math.cos(szog), math.sin(szog), 0))
    return pontok


def objektum(RDK, nev, haromszogek, szulo, pose, szin):
    obj = RDK.AddShape(haromszogek)
    obj.setName(nev)
    obj.setParent(szulo)
    obj.setPose(pose)
    obj.setColor(list(szin))
    return obj


def doboz(RDK, nev, dx, dy, dz, szulo, x, y, z, szin, zona=False):
    """Doboz objektum; az origója az alaplap közepe (x, y, z a szülő keretben)."""
    obj = objektum(RDK, nev, doboz_haromszogek(dx, dy, dz), szulo, robomath.transl(x, y, z), szin)
    if zona:  # a mérőszkript ebből tudja a tiltott zóna pontos méretét
        adat = {"min": [-dx / 2.0, -dy / 2.0, 0.0], "max": [dx / 2.0, dy / 2.0, float(dz)]}
        try:
            obj.setParam("ZonaDoboz", json.dumps(adat).encode("utf-8"))
        except Exception:
            pass
    return obj


def szerszam_letrehozasa(RDK, robot, nev, hossz, alak):
    """Egyszerű szerszám geometriával. A TCP a karimától (flange) 'hossz' mm-re, a Z tengelyen van."""
    tool = robot.AddTool(robomath.transl(0, 0, hossz), nev)
    if alak == "megfogo":
        h = doboz_haromszogek(60, 40, hossz - 50, z0=0)
        h += doboz_haromszogek(10, 30, 55, kx=-35, z0=hossz - 50)
        h += doboz_haromszogek(10, 30, 55, kx=35, z0=hossz - 50)
    elif alak == "toll":
        h = henger_haromszogek(10, 0, hossz - 30) + henger_haromszogek(4, hossz - 30, hossz)
    else:  # műszer: tartó + vékony szár + tű
        h = henger_haromszogek(12, 0, 40) + henger_haromszogek(5, 40, hossz - 30) + henger_haromszogek(1.5, hossz - 30, hossz)
    try:
        forma = RDK.AddShape(h)
        tool.AddGeometry(forma, robomath.eye(4))
        forma.Delete()
        tool.setColor(list(SZERSZAM_SZIN))
    except Exception as e:
        print("A szerszám geometriája nem hozható létre (%s) - a szerszám csak TCP-ként működik." % e)
    return tool


# ---------------------------------------------------------------------------
# Inverz kinematika és elrendezés
# ---------------------------------------------------------------------------
class Cella(object):
    """A robot, a szerszám és a cella-keret közös adatai; IK a keretben megadott TCP-helyzetekhez."""

    def __init__(self, robot, tool, robot_abs):
        self.robot, self.tool, self.robot_abs = robot, tool, robot_abs
        self.dof = len(lista(robot.Joints()))
        lim = robot.JointLimits()
        self.also, self.felso = lista(lim[0])[:self.dof], lista(lim[1])[:self.dof]
        try:
            self.home = lista(robot.JointsHome())[:self.dof]
        except Exception:
            self.home = lista(robot.Joints())[:self.dof]
        if len(self.home) < self.dof:
            self.home = [0.0] * self.dof
        self.tool_pose = robot.PoseTool()  # a main() előtte aktívvá teszi a szerszámot

    def ik(self, keret_abs, pose_keretben, mag):
        """A keretben megadott TCP-helyzet csuklószögei (a 'mag' megoldáshoz legközelebbi), vagy None."""
        karima = self.robot_abs.invH() * keret_abs * pose_keretben * self.tool_pose.invH()
        q = lista(self.robot.SolveIK(karima, list(mag)))
        if len(q) < self.dof:
            return None
        q = q[:self.dof]
        if any(q[i] < self.also[i] - 1e-6 or q[i] > self.felso[i] + 1e-6 for i in range(self.dof)):
            return None
        return q

    def elso_megoldas(self, keret_abs, pose_keretben):
        """Az első (Home) célpont: több kiinduló becslésből a robot alaphelyzetéhez legközelebbi megoldás."""
        magok = [self.home, lista(self.robot.Joints())[:self.dof]]
        if self.dof == 6:
            magok += [[0, -90, 90, -90, -90, 0], [0, 0, 0, 0, 90, 0], [0, 30, 30, 0, 60, 0]]
        elif self.dof == 7:
            magok += [[0, 30, 0, -90, 0, 60, 0], [0, 45, 0, -60, 0, 75, 0]]
        legjobb, pont = None, None
        for mag in magok:
            if len(mag) != self.dof:
                continue
            q = self.ik(keret_abs, pose_keretben, mag)
            if q is None:
                continue
            tav = sum(((q[i] - self.home[i]) / max(1.0, self.felso[i] - self.also[i])) ** 2 for i in range(self.dof))
            if pont is None or tav < pont:
                legjobb, pont = q, tav
        return legjobb


def elrendezes_keresese(RDK, cella, tavolsagok, celpontok, mozgasok):
    """Megkeresi azt a robottól mért távolságot (x), amelynél minden célpont elérhető és minden
    mozgás végrehajtható. celpontok: [(név, pose_keretben)], mozgasok: [("J"/"L", név1, név2)]."""
    for d in tavolsagok:
        keret_abs = cella.robot_abs * robomath.transl(d, 0, 0)
        q = {}
        elozo = None
        for nev, pose in celpontok:
            q[nev] = cella.elso_megoldas(keret_abs, pose) if elozo is None else cella.ik(keret_abs, pose, q[elozo])
            if q[nev] is None:
                break
            elozo = nev
        if len(q) < len(celpontok) or any(v is None for v in q.values()):
            continue
        rendben = True
        cella.robot.setPoseTool(cella.tool)
        cella.robot.setPoseFrame(robomath.transl(d, 0, 0))  # a robot bázisához képest
        pozok = dict(celpontok)
        for tipus, a, b in mozgasok:
            try:
                if tipus == "J":
                    hiba = cella.robot.MoveJ_Test(q[a], q[b])
                else:
                    hiba = cella.robot.MoveL_Test(q[a], pozok[b])
            except Exception:
                hiba = 0  # régebbi RoboDK: a teszt nem érhető el, a program frissítése úgyis ellenőriz
            if hiba != 0:
                rendben = False
                break
        if rendben:
            return d, q
    return None, None


def celpont(RDK, nev, keret, pose, robot, q, csuklo=False):
    t = RDK.AddTarget(nev, keret, robot)
    if csuklo:
        t.setAsJointTarget()
    else:
        t.setAsCartesianTarget()
        t.setPose(pose)
    t.setJoints(q)
    return t


def program(RDK, nev, robot, keret, tool, seb, lepesek):
    """lepesek: ("J"|"L", célpont) | ("szunet", ms) | ("hivas", név) | ("kerekites", mm)."""
    v, a, w, alfa = seb
    tiszta, utolso = [], None  # ugyanarra a célpontra kétszer egymás után nem mozgunk
    for lepes in lepesek:
        if lepes[0] in ("J", "L"):
            if lepes[1] is utolso:
                continue
            utolso = lepes[1]
        tiszta.append(lepes)
    lepesek = tiszta
    prog = RDK.AddProgram(nev, robot)
    prog.setPoseFrame(keret)
    prog.setPoseTool(tool)
    prog.setSpeed(v, w, a, alfa)
    prog.setRounding(-1)  # pontos (megálló) célpontok
    for tipus, arg in lepesek:
        if tipus == "J":
            prog.MoveJ(arg)
        elif tipus == "L":
            prog.MoveL(arg)
        elif tipus == "szunet":
            prog.Pause(arg)
        elif tipus == "hivas":
            prog.RunInstruction(arg, PROGRAMHIVAS)
        elif tipus == "kerekites":
            prog.setRounding(arg)
    return prog


def makro(RDK, mappa, nev, kod):
    """Kis Python program (szimulációs esemény), amelyet a robotprogram programhívással indít."""
    os.makedirs(mappa, exist_ok=True)
    fajl = os.path.join(mappa, nev + ".py")
    with open(fajl, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n# A cella_epito.py hozta létre: szimulációs esemény a(z) %s lépéshez.\n" % nev)
        f.write("try:\n    from robodk import robolink, robomath\nexcept ImportError:\n"
                "    import robolink\n    import robodk as robomath\nRDK = robolink.Robolink()\n")
        f.write(kod)
    regi = nev_szerint(RDK, nev, ITEM_TYPE_PROGRAM_PYTHON)
    if regi is not None:
        regi.Delete()
    return RDK.AddFile(fajl)


def utkozes_par(RDK, allapot, a, b, a_linkek=1):
    for link in range(a_linkek):
        try:
            RDK.setCollisionActivePair(allapot, a, b, link, 0)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# A három feladat
# ---------------------------------------------------------------------------
def feladat1(RDK, cella, mappa):
    """Pick & Place: munkadarab áthelyezése, MoveJ/MoveL × 3 sebesség + ismétlés."""
    celok = [("Home", poz(-50, 0, 300)), ("Felvetel_felett", poz(0, -200, 125)), ("Felvetel", poz(0, -200, 25)),
             ("Lerakas_felett", poz(0, 200, 125)), ("Lerakas", poz(0, 200, 25))]
    mozg = [("J", "Home", "Felvetel_felett"), ("L", "Felvetel_felett", "Felvetel"), ("L", "Felvetel", "Felvetel_felett"),
            ("J", "Felvetel_felett", "Lerakas_felett"), ("L", "Lerakas_felett", "Lerakas"), ("L", "Lerakas", "Lerakas_felett"),
            ("J", "Lerakas_felett", "Home"), ("L", "Home", "Felvetel_felett"), ("L", "Felvetel_felett", "Lerakas_felett"),
            ("L", "Lerakas_felett", "Home")]
    d, q = elrendezes_keresese(RDK, cella, [400, 450, 350, 500, 300, 550], celok, mozg)
    if d is None:
        return None
    keret = RDK.AddFrame("Asztal")
    keret.setPoseAbs(cella.robot_abs * robomath.transl(d, 0, 0))
    doboz(RDK, "Asztallap", 500, 800, 20, keret, 0, 0, -20, SZURKE)
    doboz(RDK, "Munkadarab", 50, 50, 50, keret, 0, -200, 0, KEK)
    doboz(RDK, "Lerakohely", 70, 70, 1, keret, 0, 200, 0, ZOLD)
    t = {nev: celpont(RDK, nev, keret, pose, cella.robot, q[nev], nev == "Home") for nev, pose in celok}

    sz = "RDK.Item(%r, robolink.ITEM_TYPE_TOOL)" % cella.tool.Name()
    makro(RDK, mappa, "Megfogas", "darab = RDK.Item('Munkadarab', robolink.ITEM_TYPE_OBJECT)\n"
          "darab.setParentStatic(%s)\n" % sz)
    makro(RDK, mappa, "Elengedes", "darab = RDK.Item('Munkadarab', robolink.ITEM_TYPE_OBJECT)\n"
          "darab.setParentStatic(RDK.Item('Asztal', robolink.ITEM_TYPE_FRAME))\n")
    makro(RDK, mappa, "Alaphelyzet", "darab = RDK.Item('Munkadarab', robolink.ITEM_TYPE_OBJECT)\n"
          "darab.setParent(RDK.Item('Asztal', robolink.ITEM_TYPE_FRAME))\n"
          "darab.setPose(robomath.transl(0, -200, 0))\n")

    def ciklus(atvitel, honnan, hova):
        return [(atvitel, t[honnan + "_felett"]), ("L", t[honnan]), ("szunet", 300), ("hivas", "Megfogas"),
                ("L", t[honnan + "_felett"]), (atvitel, t[hova + "_felett"]), ("L", t[hova]), ("szunet", 300),
                ("hivas", "Elengedes"), ("L", t[hova + "_felett"])]

    programok = []
    for mozgas in ("MoveJ", "MoveL"):
        for szint, seb in SEBESSEG_F1.items():
            m = mozgas[-1]
            lepesek = [("hivas", "Alaphelyzet"), ("J", t["Home"])] + ciklus(m, "Felvetel", "Lerakas") + [(m, t["Home"])]
            programok.append(program(RDK, "PP_%s_%s" % (mozgas, szint), cella.robot, keret, cella.tool, seb, lepesek))
    lepesek = [("hivas", "Alaphelyzet"), ("J", t["Home"])]
    for _ in range(3):
        lepesek += ciklus("J", "Felvetel", "Lerakas") + ciklus("J", "Lerakas", "Felvetel")
    lepesek.append(("J", t["Home"]))
    programok.append(program(RDK, "PP_ismetles_3x", cella.robot, keret, cella.tool, SEBESSEG_F1["kozepes"], lepesek))
    return d, keret, programok


def feladat2(RDK, cella):
    """Pályakövetés: 150 mm oldalú négyzet; lassú/gyors × pontos/lekerekített sarkok."""
    a = 75.0
    celok = [("Home", poz(0, 0, 200)), ("P1_felett", poz(-a, -a, 50)), ("P1", poz(-a, -a, 0)), ("P2", poz(a, -a, 0)),
             ("P3", poz(a, a, 0)), ("P4", poz(-a, a, 0))]
    mozg = [("J", "Home", "P1_felett"), ("L", "P1_felett", "P1"), ("L", "P1", "P2"), ("L", "P2", "P3"),
            ("L", "P3", "P4"), ("L", "P4", "P1"), ("L", "P1", "P1_felett"), ("J", "P1_felett", "Home")]
    d, q = elrendezes_keresese(RDK, cella, [330, 300, 360, 270, 400, 450], celok, mozg)
    if d is None:
        return None
    keret = RDK.AddFrame("Palya")
    keret.setPoseAbs(cella.robot_abs * robomath.transl(d, 0, 0))
    doboz(RDK, "Asztallap", 400, 500, 20, keret, 0, 0, -21, SZURKE)
    rajzlap = doboz(RDK, "Rajzlap", 297, 210, 1, keret, 0, 0, -1, FEHER)
    try:
        gorbe = RDK.AddCurve([[-a, -a, 0.5], [a, -a, 0.5], [a, a, 0.5], [-a, a, 0.5], [-a, -a, 0.5]])
        gorbe.setName("Negyzet_palya")
        gorbe.setParent(keret)
    except Exception:
        pass
    t = {nev: celpont(RDK, nev, keret, pose, cella.robot, q[nev], nev == "Home") for nev, pose in celok}
    utkozes_par(RDK, COLLISION_OFF, cella.tool, rajzlap)  # a toll hegye érinti a papírt: ez nem ütközés

    programok = []
    for kerekites, utotag in ((-1, ""), (LEKEREKITES_F2_MM, "_lekerekitett")):
        for szint, seb in SEBESSEG_F2.items():
            lepesek = [("J", t["Home"]), ("J", t["P1_felett"]), ("L", t["P1"]), ("kerekites", kerekites),
                       ("L", t["P2"]), ("L", t["P3"]), ("L", t["P4"]), ("kerekites", -1), ("L", t["P1"]),
                       ("L", t["P1_felett"]), ("J", t["Home"])]
            programok.append(program(RDK, "Negyzet_%s%s" % (szint, utotag), cella.robot, keret, cella.tool, seb, lepesek))
    return d, keret, programok


def feladat3(RDK, cella):
    """Precíziós mozgás: 3 célpont a műtéti területen, köztük tiltott zóna; több sebesség."""
    h = 100.0  # biztonsági (átmeneti) magasság - a tiltott zóna 60 mm magas
    pontok = {"C1": (-80, -60), "C2": (80, -60), "C3": (0, 70)}
    celok = [("Kiindulas", poz(0, 0, 150))]
    for nev, (x, y) in pontok.items():
        celok += [(nev + "_felett", poz(x, y, h)), (nev, poz(x, y, 0))]
    sorrend = ["Kiindulas", "C1_felett", "C1", "C1_felett", "C2_felett", "C2", "C2_felett", "C3_felett", "C3",
               "C3_felett", "Kiindulas"]
    mozg = [("L", sorrend[i], sorrend[i + 1]) for i in range(len(sorrend) - 1)]
    d, q = elrendezes_keresese(RDK, cella, [500, 450, 550, 400, 600, 350], celok, mozg)
    if d is None:
        return None
    keret = RDK.AddFrame("Muteti_terulet")
    keret.setPoseAbs(cella.robot_abs * robomath.transl(d, 0, 0))
    lap = doboz(RDK, "Mutoasztal", 300, 300, 20, keret, 0, 0, -20, [0.75, 0.82, 0.86, 1.0])
    zona = doboz(RDK, "Tiltott_zona", 60, 60, 60, keret, 0, -60, 0, PIROS_ATLATSZO, zona=True)
    for nev, (x, y) in pontok.items():
        doboz(RDK, "Jelolo_" + nev, 8, 8, 0.5, keret, x, y, 0, ZOLD)
    t = {nev: celpont(RDK, nev, keret, pose, cella.robot, q[nev], False) for nev, pose in celok}

    # Ütközésvizsgálat: robot és műszer a tiltott zónával igen, a műszer és az asztallap között nem
    try:
        RDK.setCollisionActive(COLLISION_ON)
    except Exception:
        pass
    utkozes_par(RDK, COLLISION_ON, cella.robot, zona, cella.dof + 1)
    utkozes_par(RDK, COLLISION_ON, cella.tool, zona)
    utkozes_par(RDK, COLLISION_OFF, cella.tool, lap)

    programok = []
    valtozatok = [(szint, seb, False) for szint, seb in SEBESSEG_F3.items()] + [("gyors", SEBESSEG_F3["gyors"], True)]
    for szint, seb, kerekitett in valtozatok:
        lepesek = [("J", t["Kiindulas"])]
        for nev in sorrend[1:]:
            if kerekitett:  # lekerekítés csak az átmeneti pontokban, a célpontokban pontos megállás
                lepesek.append(("kerekites", LEKEREKITES_F3_MM if nev.endswith("_felett") else -1))
            lepesek.append(("L", t[nev]))
        nev = "Precizios_%s%s" % (szint, "_lekerekitett" if kerekitett else "")
        programok.append(program(RDK, nev, cella.robot, keret, cella.tool, seb, lepesek))
    return d, keret, programok


# ---------------------------------------------------------------------------
# Főprogram
# ---------------------------------------------------------------------------
GENERALT = {
    1: {"keret": ["Asztal"], "eszkoz": "Megfogo", "programok": ["PP_%s_%s" % (m, s) for m in ("MoveJ", "MoveL") for s in SEBESSEG_F1]
        + ["PP_ismetles_3x"], "makrok": ["Megfogas", "Elengedes", "Alaphelyzet"]},
    2: {"keret": ["Palya"], "eszkoz": "Toll", "programok": ["Negyzet_%s%s" % (s, u) for u in ("", "_lekerekitett") for s in SEBESSEG_F2],
        "makrok": []},
    3: {"keret": ["Muteti_terulet"], "eszkoz": "Muszer",
        "programok": ["Precizios_%s" % s for s in SEBESSEG_F3] + ["Precizios_gyors_lekerekitett"], "makrok": []},
}
SZERSZAMOK = {1: ("Megfogo", 160, "megfogo"), 2: ("Toll", 120, "toll"), 3: ("Muszer", 180, "muszer")}


def main():
    RDK = robolink.Robolink()
    robotok = [r for r in RDK.ItemList(ITEM_TYPE_ROBOT) if len(lista(r.Joints())) >= 6]
    if not robotok:
        RDK.ShowMessage("Nincs 6 vagy 7 tengelyes robot az állomásban.\nTöltsd be: File → Open online library "
                        "(1. feladat: UR5e, 2.: ABB IRB 120-3/0.6, 3.: KUKA LBR iiwa 7 R800).")
        return
    robot = robotok[0]
    fsz = feladat_valasztas(RDK)
    if fsz not in (1, 2, 3):
        print("Nincs kiválasztott feladat - kilépés.")
        return

    gen = GENERALT[fsz]
    regiek = [x for x in [nev_szerint(RDK, n, ITEM_TYPE_FRAME) for n in gen["keret"]]
              + [nev_szerint(RDK, n, ITEM_TYPE_PROGRAM) for n in gen["programok"]]
              + [nev_szerint(RDK, n, ITEM_TYPE_PROGRAM_PYTHON) for n in gen["makrok"]] if x is not None]
    if regiek:
        if not igen_nem("A(z) %d. feladat cellája már létezik (%d elem). Töröljem és építsem újra?" % (fsz, len(regiek))):
            return
        for x in regiek:
            x.Delete()

    # Szerszám: a robot aktív szerszáma, vagy ha nincs, egy egyszerű, a feladathoz illő szerszám
    tool = robot.getLink(ITEM_TYPE_TOOL)
    sajat_szerszam = tool.Valid()
    if not sajat_szerszam or tool.Name() == SZERSZAMOK[fsz][0]:
        regi = nev_szerint(RDK, SZERSZAMOK[fsz][0], ITEM_TYPE_TOOL)
        if regi is not None:
            regi.Delete()
        nev, hossz, alak = SZERSZAMOK[fsz]
        tool = szerszam_letrehozasa(RDK, robot, nev, hossz, alak)
        sajat_szerszam = False
    robot.setPoseTool(tool)

    gyoker = adatmappa(RDK)
    os.makedirs(gyoker, exist_ok=True)
    cella = Cella(robot, tool, robot.PoseAbs())
    eredeti = lista(robot.Joints())[:cella.dof]
    print("%d. feladat cellájának felépítése (robot: %s)..." % (fsz, robot.Name()))
    if fsz == 1:
        eredmeny = feladat1(RDK, cella, os.path.join(gyoker, "makrok"))
    elif fsz == 2:
        eredmeny = feladat2(RDK, cella)
    else:
        eredmeny = feladat3(RDK, cella)
    if eredmeny is None:
        robot.setJoints(eredeti)
        RDK.ShowMessage("Nem találtam olyan elrendezést, ahol a robot minden célpontot elér. Próbáld a javasolt "
                        "robottal, vagy módosítsd a célpontok koordinátáit a szkript elején.")
        return
    d, keret, programok = eredmeny
    robot.setPoseFrame(keret)
    robot.setJoints(eredeti)

    with open(os.path.join(gyoker, "feladat.txt"), "w", encoding="utf-8") as f:
        f.write(FELADATSZOVEGEK[fsz] + "\n")

    hibas = []
    for prog in programok:
        try:
            vi, ido, tav, arany, uzenet = prog.Update()
            if arany < 0.999:
                hibas.append("%s (%s)" % (prog.Name(), uzenet))
        except Exception:
            pass
    uzenet = ("Kész: %d. feladat cellája (robot: %s, a cella %d mm-re a robot bázisától), %d program.\n"
              "Szerszám: %s%s.\nA feladat szövege: %s\n\nKövetkező lépés: futtasd a programokat (dupla katt), "
              "majd a meresek_rogzitese.py-t." % (fsz, robot.Name(), d, len(programok), tool.Name(),
                                                   " (a robot saját szerszáma)" if sajat_szerszam else " (létrehozva)",
                                                   os.path.join(gyoker, "feladat.txt")))
    if hibas:
        uzenet += "\n\nFIGYELEM, ezek a programok nem hajthatók végre teljesen: " + "; ".join(hibas)
    print(uzenet)
    RDK.ShowMessage(uzenet, True)


if __name__ == "__main__":
    main()
