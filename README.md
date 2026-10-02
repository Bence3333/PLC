# RoboDK mérési feladatok: megvalósítás és dokumentálás

Három RoboDK-s egyetemi mérési feladat megoldása, mérése és dokumentálása Word- és PDF-jegyzőkönyvben.

## Szkriptek nélkül, lépésről lépésre (ajánlott)

| Feladat | Útmutató | Word-sablon a jegyzőkönyvhöz |
|---|---|---|
| **1. Pick & Place** (Universal Robots UR5e) | [`feladat1/UTMUTATO.md`](feladat1/UTMUTATO.md), nyomtatható: [`UTMUTATO.pdf`](feladat1/UTMUTATO.pdf) | [`feladat1/jegyzokonyv_sablon.docx`](feladat1/jegyzokonyv_sablon.docx) |
| 2. Pályakövetés (ABB IRB 120) | később készül | – |
| 3. Precíziós mozgás (KUKA LBR iiwa 7) | később készül | – |

Az útmutatóhoz **nem kell semmilyen szkript vagy programozás**:

- a cellát és a programokat a RoboDK menüiből építed fel, kattintásról kattintásra;
- a mérési eredményeket a RoboDK kijelzőiről olvasod le: az állapotsorban a program idejét és a pálya hosszát,
  a robotpanelen a TCP helyzetét és a csuklószögeket;
- a részidőket (pl. a felvételtől a lerakásig) kis mérőprogramokkal méred;
- a sebességeket és az időket egyszerű képlettel (trapéz sebességprofil) ki is számolod, ellenőrzésként;
- a jegyzőkönyvet a Word-sablonba írod, amelyben minden fejezet és mérési táblázat előre el van készítve.

**Így kezdj hozzá:**

1. Töltsd le a repót: a GitHubon **Code → Download ZIP**, majd csomagold ki.
2. Nyisd meg a `feladat1/UTMUTATO.pdf`-et, és haladj fejezetről fejezetre.
3. A sablont (`feladat1/jegyzokonyv_sablon.docx`) mentsd el a saját nevedre, és menet közben ebbe dolgozz.

## Opcionális: automatizált út szkriptekkel

A repóban olyan szkriptek is vannak, amelyek a méréseket és a jegyzőkönyvet automatikusan elkészítik. **A kézi
úthoz nincs rájuk szükség.**

- Leírásuk: [`SZKRIPTES_UT.md`](SZKRIPTES_UT.md).
- A hozzájuk tartozó, mindhárom feladatot lefedő útmutató: [`UTMUTATO.md`](UTMUTATO.md)
  ([PDF](UTMUTATO.pdf)).
- Az így készült minta-jegyzőkönyv (fiktív adatokkal): [`pelda/MINTA_jegyzokonyv.pdf`](pelda/MINTA_jegyzokonyv.pdf).

## Hasznos RoboDK-dokumentáció

- [Basic Guide](https://robodk.com/doc/en/Basic-Guide.html) és [Getting Started](https://robodk.com/doc/en/Getting-Started.html): a RoboDK alapjai
- [A Simple Pick and Place Example](https://robodk.com/doc/en/Example-Pick-place-A-Simple-Pick-Place-Example.html): a RoboDK saját pick & place példája
- [Cycle Time](https://robodk.com/doc/en/General-Cycle-Time.html): hogyan számolja a RoboDK a ciklusidőt
- [Robot panel](https://robodk.com/doc/en/Interface-Robot-Panel.html): csuklószögek és TCP-helyzet
- [Program instructions](https://robodk.com/doc/en/Robot-Programs-Program-Instructions.html) és [Simulation event](https://robodk.com/doc/en/Robot-Programs-Simulation-event.html): programutasítások, megfogás és elengedés
