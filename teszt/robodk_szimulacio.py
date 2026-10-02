# -*- coding: utf-8 -*-
"""
RoboDK NÉLKÜLI tesztkörnyezet: egy kitalált "pick and place" állomást szimulál a RoboDK API
felületével, hogy a robodk_scripts/*.py szkriptek és a jegyzőkönyv-készítő RoboDK nélkül is
kipróbálhatók legyenek.

FIGYELEM: az itt keletkező adatok FIKTÍVEK (egyszerűsített kinematikai modell), csak a
szkriptek tesztelésére és a minta-jegyzőkönyvhöz valók - beadandóban NEM használhatók.
"""

import math
import sys
import types

import numpy as np

import robodk
import robodk.robolink as _valodi_robolink
from robodk import robomath

# ---------------------------------------------------------------------------
# Egyszerűsített 6 tengelyes robotmodell (ABB IRB 120-hoz hasonló méretek, standard DH)
# ---------------------------------------------------------------------------
DH_A = [0.0, 270.0, 70.0, 0.0, 0.0, 0.0]
DH_ALPHA = [-math.pi / 2, 0.0, -math.pi / 2, math.pi / 2, -math.pi / 2, 0.0]
DH_D = [290.0, 0.0, 0.0, 302.0, 0.0, 72.0]
DH_OFFSET = [0.0, -math.pi / 2, 0.0, 0.0, 0.0, math.pi]
ALSO = [-165.0, -110.0, -110.0, -160.0, -120.0, -400.0]
FELSO = [165.0, 110.0, 70.0, 160.0, 120.0, 400.0]
VMAX = [250.0, 250.0, 250.0, 320.0, 320.0, 420.0]  # fok/s
AMAX = [800.0] * 6  # fok/s^2
TOOL = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 100.0], [0, 0, 0, 1]])  # megfogó, TCP: Z = 100 mm


def transl(x, y, z):
    T = np.eye(4)
    T[:3, 3] = [x, y, z]
    return T


def rotx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]])


def roty(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


def dh(theta, d, a, alpha):
    ct, st, ca, sa = math.cos(theta), math.sin(theta), math.cos(alpha), math.sin(alpha)
    return np.array([[ct, -st * ca, st * sa, a * ct], [st, ct * ca, -ct * sa, a * st], [0, sa, ca, d], [0, 0, 0, 1.0]])


def fk_lancolat(q_fok):
    """Az egyes csuklók koordináta-rendszerei a bázishoz képest (rajzoláshoz is)."""
    T = np.eye(4)
    lanc = [T.copy()]
    for i in range(6):
        T = T @ dh(math.radians(q_fok[i]) + DH_OFFSET[i], DH_D[i], DH_A[i], DH_ALPHA[i])
        lanc.append(T.copy())
    return lanc


def fk_tcp(q_fok):
    return fk_lancolat(q_fok)[-1] @ TOOL


def forgatasvektor(R):
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    szog = math.acos(c)
    if szog < 1e-9:
        return np.zeros(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return v / (2 * math.sin(szog)) * szog


def ik(T_cel, q_kezdo):
    """Csillapított legkisebb négyzetes inverz kinematika (numerikus Jacobi-mátrix)."""
    q = np.radians(np.array(q_kezdo, dtype=float))

    def hiba(qr):
        T = fk_tcp(np.degrees(qr))
        return np.hstack([T_cel[:3, 3] - T[:3, 3], 200.0 * forgatasvektor(T_cel[:3, :3] @ T[:3, :3].T)])

    for _ in range(200):
        e = hiba(q)
        if np.linalg.norm(e) < 1e-4:
            break
        J = np.zeros((6, 6))
        for k in range(6):
            dq = np.zeros(6)
            dq[k] = 1e-6
            J[:, k] = (e - hiba(q + dq)) / 1e-6
        dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
        q = q + dq * min(1.0, 0.2 / max(1e-12, np.max(np.abs(dq))))  # kis lépések: a kezdőhöz közeli megoldás
    return (np.degrees(q) + 180.0) % 360.0 - 180.0


def trapez(L, vmax, amax):
    """Trapéz sebességprofil: (teljes idő, s(t) függvény)."""
    if L <= 1e-12:
        return 0.0, lambda t: 0.0
    t_gy = vmax / amax
    if amax * t_gy * t_gy >= L:
        t_gy = math.sqrt(L / amax)
        v_csucs, T = amax * t_gy, 2 * t_gy
    else:
        v_csucs, T = vmax, L / vmax + vmax / amax

    def s(t):
        if t <= 0:
            return 0.0
        if t >= T:
            return L
        if t < t_gy:
            return 0.5 * amax * t * t
        if t > T - t_gy:
            return L - 0.5 * amax * (T - t) ** 2
        return 0.5 * amax * t_gy * t_gy + v_csucs * (t - t_gy)

    return T, s


# ---------------------------------------------------------------------------
# Hamis RoboDK elemek
# ---------------------------------------------------------------------------
def mat(np_tomb):
    return robomath.Mat(np.asarray(np_tomb, dtype=float).tolist())


def oszlop(lista):
    return robomath.Mat([float(v) for v in lista])


class Elem(object):
    def __init__(self, allomas, nev, tipus, szulo=None, poz=None):
        self.allomas, self.nev, self.tipus, self.szulo = allomas, nev, tipus, szulo
        self.poz = np.eye(4) if poz is None else poz  # a szülőhöz képest
        self.item = id(self)

    def Name(self):
        return self.nev

    def Valid(self, check_deleted=False):
        return True

    def Type(self):
        return self.tipus

    def Parent(self):
        return self.szulo if self.szulo is not None else NincsElem()

    def abszolut(self):
        return (self.szulo.abszolut() if self.szulo is not None else np.eye(4)) @ self.poz

    def Pose(self):
        return mat(self.poz)

    def PoseAbs(self):
        return mat(self.abszolut())

    def getLink(self, tipus=_valodi_robolink.ITEM_TYPE_ROBOT):
        return self.allomas.robot if tipus == _valodi_robolink.ITEM_TYPE_ROBOT else NincsElem()


class NincsElem(object):
    item = 0

    def Valid(self, check_deleted=False):
        return False

    def Name(self):
        return ""


class Robot(Elem):
    def __init__(self, allomas, nev, szulo, q):
        Elem.__init__(self, allomas, nev, _valodi_robolink.ITEM_TYPE_ROBOT, szulo)
        self.q = list(q)
        self.szellemek = []

    def Joints(self):
        return oszlop(self.q)

    def JointLimits(self):
        return oszlop(ALSO), oszlop(FELSO), 0.0

    def Pose(self):  # aktív szerszám az aktív referenciához képest
        ref = self.allomas.asztal
        return mat(np.linalg.inv(ref.abszolut()) @ self.abszolut() @ fk_tcp(self.q))

    def PoseTool(self):
        return mat(TOOL)

    def getLink(self, tipus=_valodi_robolink.ITEM_TYPE_ROBOT):
        if tipus == _valodi_robolink.ITEM_TYPE_TOOL:
            return self.allomas.szerszam
        if tipus == _valodi_robolink.ITEM_TYPE_FRAME:
            return self.allomas.asztal
        return NincsElem()

    def ShowSequence(self, matrix, display_type=-1, timeout=-1):
        self.szellemek = [list(j) for j in matrix]


class Szerszam(Elem):
    def PoseTool(self):
        return mat(TOOL)

    def Pose(self):
        return mat(TOOL)


class Celpont(Elem):
    def __init__(self, allomas, nev, szulo, q, csuklo_target=False):
        poz = np.linalg.inv(szulo.abszolut()) @ fk_tcp(q)  # a robot bázisa az állomás origójában van
        Elem.__init__(self, allomas, nev, _valodi_robolink.ITEM_TYPE_TARGET, szulo, poz)
        self.q, self.csuklo = list(q), csuklo_target

    def Joints(self):
        return oszlop(self.q)

    def isJointTarget(self):
        return 1 if self.csuklo else 0


class Program(Elem):
    """Utasítások: ('speed', mm/s) | ('movej'|'movel', Celpont) | ('pause', s) | ('event', szöveg)."""

    def __init__(self, allomas, nev, utasitasok, hibas=False):
        Elem.__init__(self, allomas, nev, _valodi_robolink.ITEM_TYPE_PROGRAM)
        self.utasitasok, self.hibas = utasitasok, hibas
        self._palya = None

    def InstructionCount(self):
        return len(self.utasitasok)

    def Instruction(self, i):
        tip, arg = self.utasitasok[i]
        if tip in ("movej", "movel"):
            nev = "%s (%s)" % ("MoveJ" if tip == "movej" else "MoveL", arg.nev)
            return nev, 0, 1 if tip == "movej" else 2, 1 if arg.csuklo else 0, arg.Pose(), oszlop(arg.q)
        if tip == "speed":
            return "Set Speed (%g mm/s)" % arg, 2, None, None, None, None
        if tip == "pause":
            return "Pause (%g ms)" % (arg * 1000), 6, None, None, None, None
        return "Event: %s" % arg, 7, None, None, None, None

    def _szamol(self, dt):
        """Időalapú pálya: mintánként [J1..J6, ERR, MM_STEP, DEG_STEP, MOVE_ID, TIME, X, Y, Z]."""
        q = list(self.allomas.robot.q)
        v_lin, a_lin = 300.0, 1500.0
        sorok = []

        def ment(qk, move_id, hiba=0):
            p = fk_tcp(qk)[:3, 3]
            sorok.append(list(qk) + [hiba, 1, 1, move_id, len(sorok) * dt] + list(p))

        for idx, (tip, arg) in enumerate(self.utasitasok):
            if tip == "speed":
                v_lin = float(arg)
            elif tip == "pause":
                for _ in range(int(round(arg / dt))):
                    ment(q, idx)
            elif tip == "movej":
                cel = np.array(arg.q)
                dq = cel - np.array(q)
                idok = [trapez(abs(dq[k]), VMAX[k] * 0.6, AMAX[k]) for k in range(6)]
                k_lassu = max(range(6), key=lambda k: idok[k][0])
                T, s = idok[k_lassu]
                L = abs(dq[k_lassu])
                lepes = max(1, int(math.ceil(T / dt)))
                for i in range(1, lepes + 1):
                    arany = s(min(T, i * dt)) / L if L > 0 else 1.0
                    ment(list(np.array(q) + dq * arany), idx)
                q = list(cel)
            elif tip == "movel":
                T0, T1 = fk_tcp(q), fk_tcp(arg.q)
                L = float(np.linalg.norm(T1[:3, 3] - T0[:3, 3]))
                T, s = trapez(L, v_lin, a_lin)
                lepes = max(1, int(math.ceil(T / dt)))
                for i in range(1, lepes + 1):
                    arany = s(min(T, i * dt)) / L if L > 0 else 1.0
                    Tc = T0.copy()
                    Tc[:3, 3] = T0[:3, 3] + (T1[:3, 3] - T0[:3, 3]) * arany
                    q = list(ik(Tc, q))
                    hiba = 0
                    if self.hibas and 0.4 < arany < 0.6:  # mesterséges hiba a hibakezelés teszteléséhez
                        hiba = 100 if arany < 0.5 else 100100  # csukló-szingularitás, ill. + ütközés
                    ment(q, idx, hiba)
                q = list(arg.q)
        return sorok

    def _palyaadatok(self, dt):
        if self._palya is None or self._palya[0] != dt:
            self._palya = (dt, self._szamol(dt))
        return self._palya[1]

    def Update(self, check_collisions=0, timeout_sec=3600, mm_step=-1, deg_step=-1):
        sorok = self._palyaadatok(0.01)
        ido = sorok[-1][10] if sorok else 0.0
        tav = sum(float(np.linalg.norm(np.array(sorok[i][11:14]) - np.array(sorok[i - 1][11:14])))
                  for i in range(1, len(sorok)))
        if self.hibas:
            arany = 0.62 if check_collisions else 0.8
            uzenet = "Wrist singularity (MINTA)" + ("; collision: Robot link 4 - Doboz" if check_collisions else "")
            return float(len(self.utasitasok) - 2), ido, tav, arany, uzenet
        return float(len(self.utasitasok)), ido, tav, 1.0, "Program OK (MINTA - szimulált adat)"

    def InstructionListJoints(self, mm_step=10, deg_step=5, save_to_file=None, collision_check=0, flags=0, time_step=0.1):
        sorok = self._palyaadatok(time_step)
        J = np.array([s[:6] for s in sorok])
        v = np.gradient(J, time_step, axis=0)
        a = np.gradient(v, time_step, axis=0)
        teljes = [s + list(v[i]) + list(a[i]) for i, s in enumerate(sorok)]
        matrix = robomath.Mat([list(oszl) for oszl in zip(*teljes)])  # minden minta egy oszlop
        allapot = -1 if self.hibas else len(self.utasitasok)
        return ("Szingularitás a pályán (MINTA)" if self.hibas else ""), matrix, allapot


class Allomas(object):
    def __init__(self, hibas_program=False):
        R = robodk.robolink
        self.bazis = Elem(self, "ABB IRB 120 alap", R.ITEM_TYPE_FRAME)
        self.robot = Robot(self, "ABB IRB 120-3/0.6", self.bazis, [0, -10, 10, 0, 90, 0])
        self.szerszam = Szerszam(self, "Megfogo", R.ITEM_TYPE_TOOL, self.robot)
        self.asztal = Elem(self, "Asztal", R.ITEM_TYPE_FRAME, None, transl(250, 0, 20))
        self.targyak = [
            Elem(self, "Asztallap", R.ITEM_TYPE_OBJECT, self.asztal, transl(0, -250, -20)),
            Elem(self, "Doboz", R.ITEM_TYPE_OBJECT, self.asztal, transl(100, -150, 0)),
        ]
        le = roty(math.pi)  # lefelé néző szerszám (mint a Home helyzetben)
        home = [0.0, -10.0, 10.0, 0.0, 90.0, 0.0]

        def cel(nev, x, y, z, seed):
            T = self.asztal.abszolut() @ transl(x, y, z) @ le
            return Celpont(self, nev, self.asztal, ik(T, seed))

        self.home = Celpont(self, "Home", self.asztal, home, csuklo_target=True)
        f_felett = cel("Felvetel_felett", 100, -150, 130, home)
        f = cel("Felvetel", 100, -150, 30, f_felett.q)
        l_felett = cel("Lerakas_felett", 100, 150, 130, home)
        l = cel("Lerakas", 100, 150, 30, l_felett.q)
        self.celpontok = [self.home, f_felett, f, l_felett, l]
        self.programok = [Program(self, "PickAndPlace", [
            ("speed", 300), ("movej", self.home), ("movej", f_felett), ("movel", f), ("pause", 0.3),
            ("event", "Attach Doboz -> Megfogo"), ("movel", f_felett), ("movej", l_felett), ("movel", l),
            ("pause", 0.3), ("event", "Detach Doboz"), ("movel", l_felett), ("movej", self.home),
        ])]
        if hibas_program:
            k1 = cel("Szing_A", 150, -60, 200, home)
            k2 = cel("Szing_B", 150, 60, 200, home)
            self.celpontok += [k1, k2]
            self.programok.append(Program(self, "Hibas_teszt", [("movej", k1), ("movel", k2)], hibas=True))

    def elemek(self, tipus=None):
        R = robodk.robolink
        osszes = [self.bazis, self.robot, self.szerszam, self.asztal] + self.targyak + self.celpontok + self.programok
        return [e for e in osszes if tipus is None or e.tipus == tipus or (tipus == R.ITEM_TYPE_ROBOT and isinstance(e, Robot))]


class HamisRobolink(object):
    """A robodk.robolink.Robolink helyettesítője."""

    allomas = None
    mappa = None
    kep_rajzolo = None  # függvény(fajl, allomas) - a "képernyőképekhez"

    def __init__(self, *args, **kwargs):
        self.ST = HamisRobolink.allomas

    def ActiveStation(self):
        return Elem(self.ST, "Minta_pick_and_place", 1)

    def getParam(self, nev="PATH_OPENSTATION", str_type=True):
        return {"PATH_OPENSTATION": HamisRobolink.mappa, "FILE_OPENSTATION": "Minta_pick_and_place.rdk",
                "PATH_DESKTOP": HamisRobolink.mappa}.get(nev)

    def Version(self):
        return "5.9.0 (MINTA - szimulált)"

    def ShowMessage(self, uzenet, popup=True):
        print("[RoboDK üzenet] " + uzenet)

    def ItemList(self, filter=None, list_names=False):
        elemek = self.ST.elemek(filter)
        return [e.nev for e in elemek] if list_names else elemek

    def Cam2D_Snapshot(self, file_save_img="", cam_handle=0, params=""):
        if HamisRobolink.kep_rajzolo is None:
            return 0
        HamisRobolink.kep_rajzolo(file_save_img, self.ST)
        return 1


def telepites(mappa, hibas_program=False, kep_rajzolo=None):
    """A hamis robolink modul betöltése 'robodk.robolink' néven."""
    HamisRobolink.allomas = Allomas(hibas_program)
    HamisRobolink.mappa = mappa
    HamisRobolink.kep_rajzolo = kep_rajzolo
    hamis = types.ModuleType("robodk.robolink")
    for k in dir(_valodi_robolink):
        if k.isupper():
            setattr(hamis, k, getattr(_valodi_robolink, k))
    hamis.Robolink = HamisRobolink
    sys.modules["robodk.robolink"] = hamis
    robodk.robolink = hamis
    return HamisRobolink.allomas
