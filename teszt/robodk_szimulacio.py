# -*- coding: utf-8 -*-
"""
RoboDK NÉLKÜLI tesztkörnyezet: a RoboDK API (robodk.robolink) egyszerűsített utánzata, amellyel a
robodk_scripts/ szkriptjei (cellaépítő, lépésnapló, mérőszkript) RoboDK nélkül is lefuttathatók.

* Minden hívást a VALÓDI robodk.robolink függvények paraméterlistájához ellenőriz, így az elírt vagy
  rosszul paraméterezett API-hívások már itt hibát okoznak.
* Egyszerűsített kinematikai modellek: UR5e, ABB IRB 120, KUKA LBR iiwa 7 (DH-paraméterekkel).
* Programok szimulációja: MoveJ (szinkronizált trapéz profil), MoveL (egyenes pálya trapéz profillal,
  lekerekítéssel a sarkokban), szünet, sebesség/gyorsulás, programhívás.

FIGYELEM: az itt keletkező adatok FIKTÍVEK - csak a szkriptek tesztelésére és a mintajegyzőkönyvhöz
valók, beadandóban NEM használhatók.
"""

import functools
import inspect
import math
import os
import sys
import types

import numpy as np

import robodk
import robodk.robolink as valodi
from robodk import robomath

R = valodi
PI = math.pi

# ---------------------------------------------------------------------------
# Robotmodellek (standard DH): a, alpha, d, offset; határok [fok]; max. csuklósebesség [fok/s]
# ---------------------------------------------------------------------------
MODELLEK = {
    "UR5e": dict(a=[0, -425, -392.2, 0, 0, 0], alpha=[PI / 2, 0, 0, PI / 2, -PI / 2, 0],
                 d=[162.5, 0, 0, 133.3, 99.7, 99.6], offset=[0] * 6, also=[-360] * 6, felso=[360] * 6,
                 vmax=[180] * 6, home=[0, -90, 0, -90, 0, 0]),
    "ABB IRB 120-3/0.6": dict(a=[0, 270, 70, 0, 0, 0], alpha=[-PI / 2, 0, -PI / 2, PI / 2, -PI / 2, 0],
                              d=[290, 0, 0, 302, 0, 72], offset=[0, -PI / 2, 0, 0, 0, PI],
                              also=[-165, -110, -110, -160, -120, -400], felso=[165, 110, 70, 160, 120, 400],
                              vmax=[250, 250, 250, 320, 320, 420], home=[0, 0, 0, 0, 30, 0]),
    "KUKA LBR iiwa 7 R800": dict(a=[0] * 7, alpha=[-PI / 2, PI / 2, PI / 2, -PI / 2, -PI / 2, PI / 2, 0],
                                 d=[340, 0, 400, 0, 400, 0, 126], offset=[0] * 7,
                                 also=[-170, -120, -170, -120, -170, -120, -175],
                                 felso=[170, 120, 170, 120, 170, 120, 175],
                                 vmax=[98, 98, 100, 130, 140, 180, 180], home=[0, 0, 0, 0, 0, 0, 0]),
}


def np_m(m):
    if isinstance(m, robomath.Mat):
        return np.array(m.rows, dtype=float)
    return np.array(m, dtype=float)


def mat(a):
    return robomath.Mat(np.asarray(a, dtype=float).tolist())


def oszlop(v):
    return robomath.Mat([float(x) for x in v])


def lista(m):
    if isinstance(m, robomath.Mat):
        return [float(r[0]) for r in m.rows]
    return [float(x) for x in m]


def dh(theta, d, a, alpha):
    ct, st, ca, sa = math.cos(theta), math.sin(theta), math.cos(alpha), math.sin(alpha)
    return np.array([[ct, -st * ca, st * sa, a * ct], [st, ct * ca, -ct * sa, a * st], [0, sa, ca, d], [0, 0, 0, 1.0]])


def forgatasvektor(Rm):
    c = max(-1.0, min(1.0, (np.trace(Rm) - 1) / 2))
    szog = math.acos(c)
    if szog < 1e-9:
        return np.zeros(3)
    if szog > PI - 1e-6:  # 180°-os forgatás
        B = (Rm + np.eye(3)) / 2
        k = int(np.argmax(np.diag(B)))
        v = B[:, k] / math.sqrt(max(B[k, k], 1e-12))
        return v / np.linalg.norm(v) * szog
    v = np.array([Rm[2, 1] - Rm[1, 2], Rm[0, 2] - Rm[2, 0], Rm[1, 0] - Rm[0, 1]])
    return v / (2 * math.sin(szog)) * szog


def rodrigues(w):
    szog = np.linalg.norm(w)
    if szog < 1e-12:
        return np.eye(3)
    k = w / szog
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(szog) * K + (1 - math.cos(szog)) * K @ K


def trapez(L, vmax, amax):
    """Trapéz sebességprofil: (teljes idő, s(t))."""
    if L <= 1e-12:
        return 0.0, lambda t: 0.0
    vmax, amax = max(vmax, 1e-6), max(amax, 1e-6)
    t_gy = vmax / amax
    if amax * t_gy * t_gy >= L:
        t_gy = math.sqrt(L / amax)
        v_cs, T = amax * t_gy, 2 * t_gy
    else:
        v_cs, T = vmax, L / vmax + vmax / amax

    def s(t):
        if t <= 0:
            return 0.0
        if t >= T:
            return L
        if t < t_gy:
            return 0.5 * amax * t * t
        if t > T - t_gy:
            return L - 0.5 * amax * (T - t) ** 2
        return 0.5 * amax * t_gy * t_gy + v_cs * (t - t_gy)
    return T, s


# ---------------------------------------------------------------------------
# Paraméterlista-ellenőrzés a valódi API-hoz
# ---------------------------------------------------------------------------
def api_ellenorzes(osztaly, valodi_osztaly):
    """Minden olyan metódust, amely a valódi osztályban is létezik, a valódi paraméterlistával ellenőriz."""
    for nev, fv in list(vars(osztaly).items()):
        if nev.startswith("_") or not callable(fv) or not hasattr(valodi_osztaly, nev):
            continue
        sig = inspect.signature(getattr(valodi_osztaly, nev))

        def burkolo(fv=fv, sig=sig, nev=nev):
            @functools.wraps(fv)
            def h(self, *args, **kwargs):
                try:
                    sig.bind(self, *args, **kwargs)
                except TypeError as e:
                    raise TypeError("A(z) %s() hívás nem illeszkedik a valódi RoboDK API-hoz: %s" % (nev, e))
                return fv(self, *args, **kwargs)
            return h
        setattr(osztaly, nev, burkolo())
    return osztaly


# ---------------------------------------------------------------------------
# Hamis állomás és elemek
# ---------------------------------------------------------------------------
class Allomas(object):
    def __init__(self, nev, mappa):
        self.nev, self.mappa = nev, mappa
        self.elemek = []
        self.utkozes_parok = {}
        self.utkozes_aktiv = False
        self.kep_rajzolo = None
        self.xyz_bazisban = True  # False: a pályaadat XYZ oszlopai az állomás rendszerében (teszteléshez)
        self.rdk = None
        self.gyoker = Elem(self, nev, R.ITEM_TYPE_STATION, None)

    def uj(self, nev, tipus, szulo=None, poz=None):
        e = Elem(self, nev, tipus, szulo if szulo is not None else self.gyoker, poz)
        self.elemek.append(e)
        return e

    def robot_hozzaadasa(self, modell, bazis_poz=None):
        bazis = self.uj(modell + " Base", R.ITEM_TYPE_FRAME, None, bazis_poz)
        r = self.uj(modell, R.ITEM_TYPE_ROBOT, bazis)
        r.modell = MODELLEK[modell]
        r.q = list(r.modell["home"])
        return r

    def elo(self, tipus=None):
        return [e for e in self.elemek if not e.torolve and (tipus is None or e.tipus == tipus)]


class Elem(object):
    """A robolink.Item utánzata (minden elemtípus egy osztály, mint a valódi API-ban)."""

    def __init__(self, allomas, nev, tipus, szulo, poz=None):
        self.ST, self.nev, self.tipus, self.szulo = allomas, nev, tipus, szulo
        self.poz = np.eye(4) if poz is None else np.array(poz, dtype=float)
        self.torolve = False
        self.item = id(self)
        self.szin = [0.6, 0.6, 0.6, 1.0]
        self.lathato = True
        self.parameterek = {}
        self.haromszogek = []  # (N x 3 csúcsok a saját rendszerben, szín)
        self.gorbe = None
        self.robot = None  # célpont/program robotja
        self.modell, self.q, self.aktiv_szerszam, self.aktiv_keret, self.szellemek = None, None, None, None, []
        self.tcp = np.eye(4)
        self.csuklo_cel, self.cel_q = False, None
        self.utasitasok = []
        self._palya = {}
        self.fajl = None

    # --- általános --------------------------------------------------------
    def Name(self):
        return self.nev

    def setName(self, name):
        self.nev = name
        return self

    def Valid(self, check_deleted=False):
        return not self.torolve

    def Type(self):
        return self.tipus

    def Parent(self):
        return self.szulo if self.szulo is not None else NincsElem()

    def Childs(self):
        return [e for e in self.ST.elo() if e.szulo is self]

    def _abs(self):
        return (self.szulo._abs() if self.szulo is not None else np.eye(4)) @ self.poz

    def Pose(self):
        if self.tipus == R.ITEM_TYPE_ROBOT:
            return mat(np.linalg.inv(self._keret_bazisban()) @ self._fk(self.q) @ self._tcp())
        if self.tipus == R.ITEM_TYPE_TOOL:
            return mat(self.tcp)
        if self.tipus == R.ITEM_TYPE_TARGET and self.csuklo_cel and self.robot is not None:
            T = self.robot._abs() @ self.robot._fk(self.cel_q) @ self.robot._tcp()
            return mat(np.linalg.inv(self.szulo._abs()) @ T)
        return mat(self.poz)

    def setPose(self, pose):
        self.poz = np_m(pose)
        return self

    def PoseAbs(self):
        return mat(self._abs())

    def setPoseAbs(self, pose):
        szulo = self.szulo._abs() if self.szulo is not None else np.eye(4)
        self.poz = np.linalg.inv(szulo) @ np_m(pose)
        return self

    def setParent(self, parent):
        self.szulo = parent
        return self

    def setParentStatic(self, parent):
        A = self._abs()
        self.szulo = parent
        self.setPoseAbs(A)
        return self

    def Delete(self):
        for e in self.Childs():
            e.Delete()
        self.torolve = True

    def setColor(self, tocolor):
        self.szin = list(tocolor) + ([1.0] if len(tocolor) == 3 else [])

    def setVisible(self, visible, visible_frame=None):
        self.lathato = bool(visible)
        return self

    def setParam(self, param, value="", skip_result=False):
        self.parameterek[param] = value
        return True

    def getParam(self, param):
        v = self.parameterek.get(param, b"")
        return v if isinstance(v, bytes) else str(v).encode("utf-8")

    def getLink(self, type_linked=R.ITEM_TYPE_ROBOT):
        if self.tipus == R.ITEM_TYPE_ROBOT:
            if type_linked == R.ITEM_TYPE_TOOL and isinstance(self.aktiv_szerszam, Elem):
                return self.aktiv_szerszam
            if type_linked == R.ITEM_TYPE_FRAME and isinstance(self.aktiv_keret, Elem):
                return self.aktiv_keret
            return NincsElem()
        if type_linked == R.ITEM_TYPE_ROBOT and self.robot is not None:
            return self.robot
        return NincsElem()

    def AddShape(self, triangle_points):
        return self.ST.rdk.AddShape(triangle_points, self)

    def AddGeometry(self, fromitem, pose):
        P = np_m(pose)
        for pontok, szin in fromitem.haromszogek:
            h = np.c_[pontok[:, :3], np.ones(len(pontok))] @ P.T
            self.haromszogek.append((h[:, :3], szin))

    # --- robot ------------------------------------------------------------
    def _fk(self, q):
        m = self.modell
        T = np.eye(4)
        for i in range(len(m["a"])):
            T = T @ dh(math.radians(q[i]) + m["offset"][i], m["d"][i], m["a"][i], m["alpha"][i])
        return T

    def _lanc(self, q):
        m = self.modell
        T, lanc = np.eye(4), [np.eye(4)]
        for i in range(len(m["a"])):
            T = T @ dh(math.radians(q[i]) + m["offset"][i], m["d"][i], m["a"][i], m["alpha"][i])
            lanc.append(T.copy())
        return lanc

    def _tcp(self):
        if isinstance(self.aktiv_szerszam, Elem):
            return self.aktiv_szerszam.tcp
        if self.aktiv_szerszam is not None:
            return self.aktiv_szerszam
        return np.eye(4)

    def _keret_bazisban(self):
        if isinstance(self.aktiv_keret, Elem):
            return np.linalg.inv(self._abs()) @ self.aktiv_keret._abs()
        if self.aktiv_keret is not None:
            return self.aktiv_keret
        return np.eye(4)

    def _ik(self, T_karima, mag, ref=None):
        """Csillapított legkisebb négyzetes IK (a karima helyzetére), a maghoz közeli megoldás.
        7 tengelyes robotnál először a J3 (könyökszög) rögzítésével próbálkozik: így a megoldás egyértelmű és a
        pálya sima; ha így nem megy, mind a 7 tengelyt használja."""
        n = len(self.modell["a"])
        if n == 7:
            q = self._ik_dls(T_karima, mag, [0, 1, 3, 4, 5, 6])
            if q is not None:
                return q
        return self._ik_dls(T_karima, mag, list(range(n)))

    def _ik_dls(self, T_karima, mag, aktiv):
        n = len(self.modell["a"])
        q = np.radians(np.array(mag[:n], dtype=float))

        def hiba(qr):
            T = self._fk(np.degrees(qr))
            return np.hstack([T_karima[:3, 3] - T[:3, 3], 200.0 * forgatasvektor(T_karima[:3, :3] @ T[:3, :3].T)])

        for _ in range(300):
            e = hiba(q)
            if np.linalg.norm(e) < 1e-7:
                break
            J = np.zeros((6, len(aktiv)))
            for c, k in enumerate(aktiv):
                dq = np.zeros(n)
                dq[k] = 1e-6
                J[:, c] = (e - hiba(q + dq)) / 1e-6
            lepes = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), e)
            lepes *= min(1.0, 0.2 / max(1e-12, np.max(np.abs(lepes))))
            q[aktiv] = q[aktiv] + lepes
        e = hiba(q)
        if np.linalg.norm(e[:3]) > 1e-3 or np.linalg.norm(e[3:]) > 1e-2:
            return None
        qd = np.degrees(q)
        also, felso = self.modell["also"], self.modell["felso"]
        for i in range(n):  # 360°-os többértelműség: a maghoz legközelebbi, határon belüli érték
            while qd[i] - mag[i] > 180 and qd[i] - 360 >= also[i]:
                qd[i] -= 360
            while mag[i] - qd[i] > 180 and qd[i] + 360 <= felso[i]:
                qd[i] += 360
        if any(qd[i] < also[i] - 1e-6 or qd[i] > felso[i] + 1e-6 for i in range(n)):
            return None
        return list(qd)

    def Joints(self):
        if self.tipus == R.ITEM_TYPE_ROBOT:
            return oszlop(self.q)
        if self.tipus == R.ITEM_TYPE_TARGET:
            return oszlop(self.cel_q if self.cel_q is not None else [0])
        return oszlop([0])

    def setJoints(self, joints):
        if self.tipus == R.ITEM_TYPE_ROBOT:
            self.q = lista(joints)[:len(self.modell["a"])]
        else:
            self.cel_q = lista(joints)
        return self

    def JointsHome(self):
        return oszlop(self.modell["home"])

    def JointLimits(self):
        return oszlop(self.modell["also"]), oszlop(self.modell["felso"]), 0.0

    def SolveFK(self, joints, tool=None, reference=None):
        T = self._fk(lista(joints))
        if tool is not None:
            T = T @ np_m(tool)
        if reference is not None:
            T = np.linalg.inv(np_m(reference)) @ T
        return mat(T)

    def SolveIK(self, pose, joints_approx=None, tool=None, reference=None):
        T = np_m(pose)
        if tool is not None:
            T = T @ np.linalg.inv(np_m(tool))
        if reference is not None:
            T = np_m(reference) @ T
        q = self._ik(T, lista(joints_approx) if joints_approx is not None else self.q)
        return oszlop(q) if q is not None else oszlop([0])

    def PoseTool(self):
        if self.tipus == R.ITEM_TYPE_TOOL:
            return mat(self.tcp)
        return mat(self._tcp())

    def PoseFrame(self):
        return mat(self._keret_bazisban())

    def setPoseTool(self, tool):
        if self.tipus == R.ITEM_TYPE_PROGRAM:
            self.utasitasok.append({"t": "tool", "arg": tool})
        elif isinstance(tool, Elem):
            self.aktiv_szerszam = tool
        else:
            self.aktiv_szerszam = np_m(tool)
        return self

    def setPoseFrame(self, frame):
        if self.tipus == R.ITEM_TYPE_PROGRAM:
            self.utasitasok.append({"t": "frame", "arg": frame})
        elif isinstance(frame, Elem):
            self.aktiv_keret = frame
        else:
            self.aktiv_keret = np_m(frame)
        return self

    def AddTool(self, tool_pose, tool_name="New TCP"):
        t = self.ST.uj(tool_name, R.ITEM_TYPE_TOOL, self)
        t.tcp = np_m(tool_pose)
        self.aktiv_szerszam = t
        return t

    def MoveJ_Test(self, j1, j2, minstep_deg=-1):
        self.q = lista(j2)
        return 0

    def MoveL_Test(self, j1, pose, minstep_mm=-1):
        q = lista(j1)
        T0 = self._fk(q) @ self._tcp()
        T1 = self._keret_bazisban() @ np_m(pose)
        for f in np.linspace(0, 1, 25)[1:]:
            T = T0.copy()
            T[:3, 3] = T0[:3, 3] + (T1[:3, 3] - T0[:3, 3]) * f
            T[:3, :3] = T0[:3, :3] @ rodrigues(forgatasvektor(T0[:3, :3].T @ T1[:3, :3]) * f)
            q = self._ik(T @ np.linalg.inv(self._tcp()), q)
            if q is None:
                return -2 if f == 1 else -1
        self.q = q
        return 0

    def ShowSequence(self, matrix, display_type=-1, timeout=-1):
        self.szellemek = [lista(j) for j in matrix]

    # --- célpont ------------------------------------------------------------
    def setAsCartesianTarget(self):
        self.csuklo_cel = False
        return self

    def setAsJointTarget(self):
        self.csuklo_cel = True
        return self

    def isJointTarget(self):
        return 1 if self.csuklo_cel else 0

    # --- program ------------------------------------------------------------
    def MoveJ(self, target, blocking=True):
        self.utasitasok.append({"t": "movej", "arg": target})

    def MoveL(self, target, blocking=True):
        self.utasitasok.append({"t": "movel", "arg": target})

    def setSpeed(self, speed_linear, speed_joints=-1, accel_linear=-1, accel_joints=-1):
        self.utasitasok.append({"t": "speed", "arg": (speed_linear, speed_joints, accel_linear, accel_joints)})
        return self

    def setRounding(self, rounding_mm):
        self.utasitasok.append({"t": "rounding", "arg": rounding_mm})
        return self

    def Pause(self, time_ms=-1):
        self.utasitasok.append({"t": "pause", "arg": time_ms})

    def RunInstruction(self, code, run_type=R.INSTRUCTION_CALL_PROGRAM):
        self.utasitasok.append({"t": "call", "arg": code})
        return 0

    def InstructionCount(self):
        return len(self.utasitasok)

    def Instruction(self, ins_id=-1):
        u = self.utasitasok[ins_id]
        t, arg = u["t"], u["arg"]
        if t in ("movej", "movel"):
            nev = "%s (%s)" % ("MoveJ" if t == "movej" else "MoveL", arg.nev)
            return (nev, R.INS_TYPE_MOVE, R.MOVE_TYPE_JOINT if t == "movej" else R.MOVE_TYPE_LINEAR,
                    arg.isJointTarget(), arg.Pose(), oszlop(arg.cel_q))
        if t == "speed":
            return "Set Speed (%g mm/s)" % arg[0], R.INS_TYPE_CHANGESPEED, None, None, None, None
        if t == "rounding":
            return "Set Rounding (%g)" % arg, R.INS_TYPE_ROUNDING, None, None, None, None
        if t == "pause":
            return "Pause (%g ms)" % arg, R.INS_TYPE_PAUSE, None, None, None, None
        if t == "call":
            return arg, R.INS_TYPE_CODE, None, None, None, None
        if t == "frame":
            return "Set Reference Frame (%s)" % getattr(arg, "nev", "pose"), R.INS_TYPE_CHANGEFRAME, None, None, None, None
        return "Set Tool (%s)" % getattr(arg, "nev", "pose"), R.INS_TYPE_CHANGETOOL, None, None, None, None

    def _szegmensek(self):
        """A program mozgásszakaszai pontos időtartammal: (időtartam, kiértékelő(t) -> (q, move_id), FK-úthossz)."""
        rob = self.robot
        n = len(rob.modell["a"])
        q = list(rob.q)
        tcp = rob._tcp()
        v_lin, a_lin, w, alfa = 100.0, 500.0, 60.0, 200.0
        kerekites = -1.0
        szegmensek = []

        def cel_T(cel):
            """A célpont TCP-helyzete a robot bázisában."""
            return np.linalg.inv(rob._abs()) @ cel.szulo._abs() @ np_m(cel.Pose())

        i = 0
        while i < len(self.utasitasok):
            u = self.utasitasok[i]
            t = u["t"]
            if t == "tool":
                tcp = u["arg"].tcp if isinstance(u["arg"], Elem) else np_m(u["arg"])
            elif t == "speed":
                sl, sj, al, aj = u["arg"]
                v_lin = sl if sl > 0 else v_lin
                w = sj if sj > 0 else w
                a_lin = al if al > 0 else a_lin
                alfa = aj if aj > 0 else alfa
            elif t == "rounding":
                kerekites = u["arg"]
            elif t == "pause":
                qp = list(q)
                szegmensek.append((u["arg"] / 1000.0, lambda tt, qp=qp, i=i: (qp, i), 0.0, tcp))
            elif t == "movej":
                cel = np.array(u["arg"].cel_q[:n], dtype=float)
                q0 = np.array(q)
                dq = cel - q0
                vm = [min(w, rob.modell["vmax"][k]) for k in range(n)]
                idok = [trapez(abs(dq[k]), vm[k], alfa) for k in range(n)]
                k_l = max(range(n), key=lambda k: idok[k][0])
                T, sfv = idok[k_l]
                L = abs(dq[k_l])

                def ertek(tt, q0=q0, dq=dq, sfv=sfv, L=L, i=i):
                    return list(q0 + dq * (sfv(tt) / L if L > 0 else 1.0)), i
                P = np.array([(rob._fk(list(q0 + dq * f)) @ tcp)[:3, 3] for f in np.linspace(0, 1, 60)])
                szegmensek.append((T, ertek, float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1))), tcp))
                q = list(cel)
            elif t == "movel":
                # egymást követő MoveL-ek láncba fűzése, amíg a célpont lekerekített (nem megálló)
                lanc, j, r_akt = [], i, kerekites
                while j < len(self.utasitasok):
                    uj = self.utasitasok[j]
                    if uj["t"] == "rounding":
                        r_akt = uj["arg"]
                    elif uj["t"] == "movel":
                        lanc.append((j, uj["arg"], r_akt))
                        if r_akt <= 0:
                            break
                    else:
                        break
                    j += 1
                kerekites = r_akt
                T0 = rob._fk(q) @ tcp
                pontok = [T0[:3, 3]] + [cel_T(c)[:3, 3] for _, c, _ in lanc]
                R_cel = cel_T(lanc[-1][1])[:3, :3]
                ut, mid = [], []  # sűrű pontsor + mozgásazonosító, lekerekített sarkokkal
                for k in range(1, len(pontok)):
                    a, b = pontok[k - 1], pontok[k]
                    hossz_ab = np.linalg.norm(b - a)
                    r_be = min(lanc[k - 2][2], 0.45 * hossz_ab) if k >= 2 and lanc[k - 2][2] > 0 else 0
                    r_ki = min(lanc[k - 1][2], 0.45 * hossz_ab) if k < len(pontok) - 1 and lanc[k - 1][2] > 0 else 0
                    irany = (b - a) / max(hossz_ab, 1e-12)
                    kezd, veg = a + irany * r_be, b - irany * r_ki
                    for f in np.linspace(0, 1, 40):
                        ut.append(kezd + (veg - kezd) * f)
                        mid.append(lanc[k - 1][0])
                    if r_ki > 0:
                        c = pontok[k + 1]
                        r_c = min(lanc[k - 1][2], 0.45 * np.linalg.norm(c - b))
                        ki = b + (c - b) / max(np.linalg.norm(c - b), 1e-12) * r_c
                        for f in np.linspace(0, 1, 20)[1:-1]:
                            ut.append((1 - f) ** 2 * veg + 2 * (1 - f) * f * b + f ** 2 * ki)
                            mid.append(lanc[k - 1][0])
                ut = np.array(ut)
                hossz = np.r_[0, np.cumsum(np.linalg.norm(np.diff(ut, axis=0), axis=1))]
                T, sfv = trapez(hossz[-1], v_lin, a_lin)
                allapot = {"q": list(q)}
                q_ref = list(q)  # a nulltér rögzített referenciája: a minták és a végállapot egyezik
                q_veg = list(q)  # a pálya végén elért csuklóállás folyamatos követéssel (7 tengelynél nem egyértelmű)
                for pp in ut[::4].tolist() + [ut[-1].tolist()]:
                    Tc = np.eye(4)
                    Tc[:3, :3] = R_cel
                    Tc[:3, 3] = pp
                    qn = rob._ik(Tc @ np.linalg.inv(tcp), q_veg, q_ref)
                    q_veg = qn if qn is not None else q_veg

                def ertek(tt, ut=ut, hossz=hossz, mid=mid, sfv=sfv, T=T, R_cel=R_cel, tcp=tcp, allapot=allapot, q_veg=q_veg,
                          q_ref=q_ref):
                    if tt >= T - 1e-12:
                        allapot["q"] = list(q_veg)
                        return list(q_veg), mid[-1]
                    sv = sfv(tt)
                    idx = min(int(np.searchsorted(hossz, sv)), len(ut) - 1)
                    if idx > 0 and hossz[idx] > hossz[idx - 1]:
                        f = (sv - hossz[idx - 1]) / (hossz[idx] - hossz[idx - 1])
                        pp = ut[idx - 1] + (ut[idx] - ut[idx - 1]) * f
                    else:
                        pp = ut[idx]
                    Tc = np.eye(4)
                    Tc[:3, :3] = R_cel
                    Tc[:3, 3] = pp
                    qn = rob._ik(Tc @ np.linalg.inv(tcp), allapot["q"], q_ref)
                    if qn is not None:
                        allapot["q"] = qn
                    return list(allapot["q"]), mid[idx]
                szegmensek.append((T, ertek, float(hossz[-1]), tcp))
                q = q_veg
                i = lanc[-1][0]
            i += 1
        return szegmensek

    def _palyaadatok(self, dt):
        """Időalapú mintavétel globális időrácson: mintánként [J..., ERR, MM_STEP, DEG_STEP, MOVE_ID, TIME, X, Y, Z]."""
        allapot = (tuple(self.robot.q), len(self.utasitasok), round(dt, 6))
        if self._palya.get("allapot") == allapot:
            return self._palya["sorok"]
        rob = self.robot
        szegm = self._szegmensek()
        vegek = np.cumsum([s[0] for s in szegm]) if szegm else np.array([0.0])
        teljes = float(vegek[-1]) if szegm else 0.0
        idopontok = list(np.arange(0.0, teljes, dt)) + [teljes]
        sorok = []
        for t in idopontok:
            k = min(int(np.searchsorted(vegek, t, side="right")), len(szegm) - 1) if szegm else 0
            if not szegm:
                q, mid, tcp = list(rob.q), 0, rob._tcp()
            else:
                kezdet = vegek[k] - szegm[k][0]
                q, mid = szegm[k][1](min(t - kezdet, szegm[k][0]))
                tcp = szegm[k][3]
            T = rob._fk(q) @ tcp
            p = T[:3, 3] if self.ST.xyz_bazisban else (rob._abs() @ T)[:3, 3]
            sorok.append(list(q) + [0, 1, 1, mid, float(t)] + list(p))
        self._palya = {"allapot": allapot, "sorok": sorok}
        return sorok

    def Update(self, check_collisions=R.COLLISION_OFF, timeout_sec=3600, mm_step=-1, deg_step=-1):
        szegm = self._szegmensek()
        ido = float(sum(s[0] for s in szegm))
        tav = float(sum(s[2] for s in szegm))
        mozgas = sum(1 for u in self.utasitasok if u["t"] in ("movej", "movel"))
        if check_collisions:
            n = len(self.robot.modell["a"])
            sorok = self._palyaadatok(0.05)
            for idx, s in enumerate(sorok):
                if self.ST.rdk._tcp_zonaban(self.robot, s[:n]):
                    return float(mozgas), ido, tav, idx / float(len(sorok)), "Collision detected (MINTA)"
        return float(mozgas), ido, tav, 1.0, "Program OK (MINTA - szimulált adat)"

    def InstructionListJoints(self, mm_step=10, deg_step=5, save_to_file=None, collision_check=R.COLLISION_OFF,
                              flags=0, time_step=0.1):
        sorok = self._palyaadatok(time_step)
        n = len(self.robot.modell["a"])
        J = np.array([s[:n] for s in sorok])
        t = np.array([s[n + 4] for s in sorok])
        v = np.gradient(J, t, axis=0) if len(J) > 2 else np.zeros_like(J)
        a = np.gradient(v, t, axis=0) if len(J) > 2 else np.zeros_like(J)
        teljes = [s + list(v[i]) + list(a[i]) for i, s in enumerate(sorok)]
        return "", robomath.Mat([list(o) for o in zip(*teljes)]), len(self.utasitasok)


api_ellenorzes(Elem, valodi.Item)


class NincsElem(object):
    item = 0
    nev = ""

    def Valid(self, check_deleted=False):
        return False

    def Name(self):
        return ""


class HamisRobolink(object):
    """A robodk.robolink.Robolink utánzata."""

    allomas = None

    def __init__(self, *args, **kwargs):
        self.ST = HamisRobolink.allomas
        self.ST.rdk = self

    def ActiveStation(self):
        return self.ST.gyoker

    def getParam(self, param="PATH_OPENSTATION", str_type=True):
        return {"PATH_OPENSTATION": self.ST.mappa, "FILE_OPENSTATION": self.ST.nev + ".rdk",
                "PATH_DESKTOP": self.ST.mappa}.get(param)

    def Version(self):
        return "5.9.0 (MINTA - szimulált)"

    def ShowMessage(self, message, popup=True):
        print("[RoboDK üzenet] " + message)

    def Render(self, always_render=False):
        pass

    def Item(self, name, itemtype=None):
        for e in self.ST.elo(itemtype):
            if e.nev == name:
                return e
        return NincsElem()

    def ItemList(self, filter=None, list_names=False):
        elemek = self.ST.elo(filter)
        return [e.nev for e in elemek] if list_names else elemek

    def Selection(self):
        return list(getattr(self.ST, "kijeloles", []))

    def ItemUserPick(self, message="Pick one item", itemtype_or_list=None):
        jeloltek = self.ST.elo(itemtype_or_list) if isinstance(itemtype_or_list, int) else list(itemtype_or_list or [])
        return jeloltek[-1] if jeloltek else NincsElem()

    def AddFrame(self, name, itemparent=0):
        return self.ST.uj(name, R.ITEM_TYPE_FRAME, itemparent if isinstance(itemparent, Elem) else None)

    def AddTarget(self, name, itemparent=0, itemrobot=0):
        t = self.ST.uj(name, R.ITEM_TYPE_TARGET, itemparent if isinstance(itemparent, Elem) else None)
        t.robot = itemrobot if isinstance(itemrobot, Elem) else (self.ST.elo(R.ITEM_TYPE_ROBOT) or [None])[0]
        t.cel_q = list(t.robot.q)
        T = t.robot._abs() @ t.robot._fk(t.cel_q) @ t.robot._tcp()
        t.poz = np.linalg.inv(t.szulo._abs()) @ T
        return t

    def AddProgram(self, name, itemrobot=0):
        p = self.ST.uj(name, R.ITEM_TYPE_PROGRAM)
        p.robot = itemrobot if isinstance(itemrobot, Elem) else (self.ST.elo(R.ITEM_TYPE_ROBOT) or [None])[0]
        return p

    def AddShape(self, triangle_points, add_to=0, override_shapes=False):
        P = np.array(triangle_points, dtype=float)
        if P.shape[0] in (3, 6) and P.shape[1] not in (3, 6):
            P = P.T
        assert len(P) % 3 == 0, "AddShape: a csúcsok száma 3 többszöröse kell legyen"
        if isinstance(add_to, Elem):
            add_to.haromszogek.append((P[:, :3], None))
            return add_to
        obj = self.ST.uj("Object", R.ITEM_TYPE_OBJECT)
        obj.haromszogek.append((P[:, :3], None))
        return obj

    def AddCurve(self, curve_points, reference_object=0, add_to_ref=False,
                 projection_type=R.PROJECTION_ALONG_NORMAL_RECALC):
        obj = self.ST.uj("Curve", R.ITEM_TYPE_OBJECT)
        obj.gorbe = np.array(curve_points, dtype=float)[:, :3]
        return obj

    def AddFile(self, filename, parent=0):
        nev, kit = os.path.splitext(os.path.basename(filename))
        assert kit.lower() == ".py", "A tesztkörnyezet csak .py fájlokat tud betölteni"
        p = self.ST.uj(nev, R.ITEM_TYPE_PROGRAM_PYTHON)
        p.fajl = filename
        return p

    def setCollisionActive(self, check_state=R.COLLISION_ON):
        self.ST.utkozes_aktiv = bool(check_state)
        return 0

    def setCollisionActivePair(self, check_state, item1, item2, id1=0, id2=0):
        self.ST.utkozes_parok[(id(item1), id(item2), id1, id2)] = bool(check_state)
        return 1

    def _tcp_zonaban(self, robot, q):
        """Egyszerűsített ütközésvizsgálat: a TCP benne van-e olyan objektumban, amelyre a szerszám
        ütközésvizsgálata be van kapcsolva."""
        P = (robot._abs() @ robot._fk(q) @ robot._tcp())[:3, 3]
        for z in self.ST.elo(R.ITEM_TYPE_OBJECT):
            if not any(v and k[1] == id(z) for k, v in self.ST.utkozes_parok.items()) or not z.haromszogek:
                continue
            pts = np.vstack([h[0] for h in z.haromszogek])
            lok = np.linalg.inv(z._abs()) @ np.r_[P, 1]
            if np.all(lok[:3] >= pts.min(0) - 1e-9) and np.all(lok[:3] <= pts.max(0) + 1e-9):
                return True
        return False

    def Cam2D_Snapshot(self, file_save_img="", cam_handle=0, params=""):
        if self.ST.kep_rajzolo is None:
            return 0
        self.ST.kep_rajzolo(file_save_img, self.ST)
        return 1


api_ellenorzes(HamisRobolink, valodi.Robolink)


def telepites(mappa, allomas_nev, modell=None, kep_rajzolo=None, bazis_poz=None):
    """Új hamis állomás (opcionálisan egy robottal), és a hamis robolink betöltése 'robodk.robolink' néven."""
    st = Allomas(allomas_nev, mappa)
    st.kep_rajzolo = kep_rajzolo
    if modell:
        st.robot_hozzaadasa(modell, bazis_poz)
    HamisRobolink.allomas = st
    hamis = types.ModuleType("robodk.robolink")
    for k in dir(valodi):
        if k.isupper():
            setattr(hamis, k, getattr(valodi, k))
    hamis.Robolink = HamisRobolink
    sys.modules["robodk.robolink"] = hamis
    robodk.robolink = hamis
    return st
