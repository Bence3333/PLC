# RoboDK-feladatok megvalósítása és dokumentálása (Word/PDF jegyzőkönyv)

Eszközkészlet RoboDK-s egyetemi feladatokhoz. A RoboDK-ban elvégzett **munkalépéseket képernyőképpel**,
a **méréseket automatikusan** rögzíti, majd egyetlen paranccsal **kész Word (.docx) és PDF jegyzőkönyvet**
készít belőlük: címlap, tartalomjegyzék, táblázatok, grafikonok és automatikus értékelés. Neked a megoldást
kell elkészítened a RoboDK-ban, és a jegyzőkönyvben sárgával kiemelt `[KITÖLTENDŐ]` részeket kell megírnod.

**Így néz ki a végeredmény:** [`pelda/MINTA_jegyzokonyv.pdf`](pelda/MINTA_jegyzokonyv.pdf).
A minta **kitalált, szimulált adatokkal** készült, és csak a formát mutatja, beadni nem lehet.

| Fájl | Mire való | Hol fut |
|---|---|---|
| [`robodk_scripts/lepes_rogzitese.py`](robodk_scripts/lepes_rogzitese.py) | Lépésnapló: rövid leírás és képernyőkép minden munkalépésről | a RoboDK-ban |
| [`robodk_scripts/meresek_rogzitese.py`](robodk_scripts/meresek_rogzitese.py) | Mérések: ciklusidő, pályahossz, célpontok, csuklószögek, sebességek, gyorsulások, csuklóhatárok, szingularitás, ütközés, képek | a RoboDK-ban |
| [`dokumentacio/jegyzokonyv_keszito.py`](dokumentacio/jegyzokonyv_keszito.py) | Word- és PDF-jegyzőkönyv a rögzített adatokból | a saját gépeden, Pythonnal |
| [`pelda/`](pelda/) | Mintajegyzőkönyv és mintaadatok (**fiktív**) | – |
| [`teszt/`](teszt/) | RoboDK nélküli tesztkörnyezet (szimulált állomás) | a saját gépeden |

---

## A munkafolyamat röviden

```
 0. Előkészületek        RoboDK + Python, feladatonként külön .rdk állomás
 1. Megvalósítás          állomás felépítése, célpontok, program, szimuláció   ┐ minden fontos lépés után:
                                                                               ┘ lepes_rogzitese.py
 2. Mérések               a kész megoldáson: meresek_rogzitese.py (több változatnál többször is)
 3. Jegyzőkönyv           python dokumentacio/jegyzokonyv_keszito.py ... --pdf
 4. Befejezés Wordben     a [KITÖLTENDŐ] részek kitöltése, mezők frissítése, PDF mentése
```

---

## 0. Előkészületek

- **RoboDK.** Ha az egyetemnek van licence, azt használd. Különben letöltheted a 30 napos próbaverziót a
  [robodk.com](https://robodk.com/download) oldalról. A próbaidő lejárta után a mentés és az export korlátozott
  lehet, de egyetemi e-mail-címmel a RoboDK-tól kérhetsz hosszabbítást.
- **Python a RoboDK-n belül.** A RoboDK telepítője a saját Pythonját és a `robodk` csomagot is felteszi, így a
  `robodk_scripts/` szkriptekhez nem kell semmit telepítened.
- **Python a jegyzőkönyvhöz.** Python 3.8 vagy újabb kell ([python.org](https://www.python.org/downloads/)).
  Telepítéskor jelöld be az „Add Python to PATH” opciót, majd ebben a mappában futtasd egyszer:
  ```
  python -m pip install -r requirements.txt
  ```
- **Feladatonként külön állomás (.rdk).** A szkriptek az adatokat az állomás neve alapján, az `.rdk` fájl mellé
  mentik. Így a 3 feladat adatai nem keverednek:
  ```
  RoboDK_feladatok/
  ├── Feladat1.rdk
  ├── Feladat2.rdk
  ├── Feladat3.rdk
  ├── Feladat1_dokumentacio/      ← automatikusan jön létre
  │   ├── feladat.txt             ← ezt te írod bele (a feladat címe és szövege, lásd 3. pont)
  │   ├── lepesek.json + kepek/   ← lépésnapló
  │   └── meres_20261002_143512/  ← mérések (minden futtatás egy új mappa)
  ├── Feladat2_dokumentacio/
  └── Feladat3_dokumentacio/
  ```
  Az állomás neve a RoboDK fa gyökéreleme. Mentés után ez általában megegyezik az `.rdk` fájl nevével.
  **Az első lépés rögzítése előtt mentsd el az állomást.**

---

## 1. Megvalósítás a RoboDK-ban és a lépések rögzítése

### Tipikus lépések és menüpontok

| Lépés | Hogyan (RoboDK, angol menü) |
|---|---|
| Robot betöltése | **File → Open online library** (Ctrl+Shift+O) → szűrés gyártóra → **Open** |
| Szerszám (megfogó) | a könyvtárból letöltött vagy betöltött szerszámot a fában **húzd rá a robotra**; a TCP a szerszámra duplán kattintva állítható |
| Referencia keret | **Program → Add Reference Frame**, a helyzete a keret ablakában adható meg |
| Objektumok (asztal, munkadarab) | **File → Open** (STL/STEP…), majd a fában húzd a megfelelő keret alá |
| Célpontok | mozgasd a robotot a kívánt helyzetbe, majd **Program → Teach Target** (Ctrl+T) |
| Program | **Program → Add Program**, utána **Move Joint Instruction** / **Move Linear Instruction** |
| Megfogás szimulációja | **Program → Simulation Event Instruction** → *Attach object* / *Detach object* |
| Szimuláció | dupla kattintás a programra. A becsült ciklusidő a futás végén a jobb alsó sarokban látszik |
| Ellenőrzés | jobb klikk a programra → **Check path** (F5), illetve **Check path and collisions** (Shift+F5) |
| Ütközésvizsgálat | **Tools → Check collisions**, a vizsgált párok: **Tools → Collision map** (Shift+X) |
| Mentés | **File → Save Station** (Ctrl+S) |

### Lépések rögzítése: `lepes_rogzitese.py`

1. Húzd be a `robodk_scripts/lepes_rogzitese.py` fájlt a RoboDK ablakába (vagy **File → Open**). A fában
   megjelenik egy `lepes_rogzitese` nevű Python-elem.
2. **Minden fontos lépés után** állítsd be a 3D nézetet, majd kattints duplán erre az elemre.
3. Írd be röviden, mit csináltál, például: *„Asztal referencia keret létrehozása, X = 250 mm, Z = 20 mm”*.
   A szkript elmenti a leírást, a 3D nézet képét és az előző lépés óta létrejött új elemek nevét (ezeket
   javaslatként fel is kínálja).

A lépések a `<állomás>_dokumentacio/lepesek.json` fájlba kerülnek. Ezt Jegyzettömbbel utólag is javíthatod:
a leírás szövegét átírhatod, egy rossz lépést törölhetsz. A képek a `kepek/lepes_NN.png` fájlokba kerülnek.
Ha egy kép nem készült el (régebbi RoboDK esetén előfordulhat), mentsd el kézzel pontosan ezen a néven,
és a jegyzőkönyvbe automatikusan bekerül.

---

## 2. Mérések: `meresek_rogzitese.py`

Amikor a megoldás kész:

1. Állítsd be a 3D nézetet, mert erről készülnek a képek.
2. Húzd be a `robodk_scripts/meresek_rogzitese.py` fájlt a RoboDK-ba, és kattints rá duplán.
3. Megkérdezi a mérés nevét. Ez nem kötelező, de hasznos, például *„v = 300 mm/s”* vagy *„végleges változat”*.

A szkript **minden programot** végigmér, az eredmények új `meres_ÉÉÉÉHHNN_ÓÓPPMM/` mappába kerülnek.
**Ha több változatot próbálsz ki** (más sebesség, lekerekítés, MoveJ vagy MoveL, máshová tett célpont),
mindegyik után futtasd le újra. A jegyzőkönyv a legutolsó mérést részletezi, az összes mérést pedig
táblázatban és grafikonon összehasonlítja. Ha egy mérést nem akarsz a jegyzőkönyvbe, nevezd át a mappáját,
például `x_meres_...` névre.

### Mit mér, és hol ellenőrizheted kézzel?

| Mérés | Honnan (RoboDK Python API) | Kézi ellenőrzés a RoboDK-ban |
|---|---|---|
| Becsült ciklusidő, TCP-pályahossz | `program.Update()` | program futtatása után a jobb alsó sarokban |
| Végrehajtható rész (érvényesség, %) | `program.Update()` | F5 (Check path) |
| Ütközés | `program.Update(COLLISION_ON)` | Shift+F5, Tools → Check collisions |
| Célpontok helyzete (X, Y, Z, Rx, Ry, Rz) és csuklószögei | `target.Pose()`, `target.Joints()` | dupla kattintás a célpontra |
| Csuklószögek, szögsebességek és -gyorsulások az idő függvényében | `program.InstructionListJoints(flags=4)` (időalapú pálya) | a robot ablaka szimuláció közben |
| TCP pályasebesség (átlag, maximum), felül- és oldalnézeti pálya | a pálya TCP-pozícióiból számolva | – |
| Csuklóhatárok, kihasználtság, tartalék a határig | `robot.JointLimits()` + a pálya | a robot ablaka (dupla kattintás a robotra) |
| Szingularitás, elérhetetlen pont | a pálya hibakódjai (magyarul értelmezve) | F5 üzenetei |
| Mozgásszakaszok ideje és úthossza | a pálya mozgásazonosítói szerint | – |
| Robotok, szerszámok (TCP), referencia keretek, objektumok helyzete | `Pose()`, `PoseAbs()`, `PoseTool()` | dupla kattintás az elemre |
| Képernyőképek (állomás, pálya „szellemrobotokkal”) | `Cam2D_Snapshot()`, `ShowSequence()` | – |

**Kimenet:** `meresek.json` (minden adat), `programok.csv`, `celpontok.csv` és `palya_<program>.csv`
(pontosvesszővel tagolt, tizedesvesszős, a magyar Excel közvetlenül megnyitja), valamint a `kepek/` mappa.
A szkript elején néhány beállítás módosítható (`IDOLEPES_S`, `UTKOZESVIZSGALAT`, `KEPERNYOKEPEK`,
`SZELLEM_ROBOTOK`, `MEGNEVEZES_KERESE`).

> **Megjegyzés a ciklusidőhöz.** A RoboDK becslése a robot beállított sebesség- és gyorsulásértékein
> alapul, ezért a valódi robotnál eltérhet. Pontosabb becsléshez pontos (lekerekítés nélküli) mozgásokat és a
> robot valós sebességhatárait kell beállítani.

---

## 3. A jegyzőkönyv elkészítése: `jegyzokonyv_keszito.py`

Tegyél minden adatmappába egy **`feladat.txt`** fájlt (UTF-8). Az első sora a feladat címe, a többi sor a
feladat szövege. A `- ` kezdetű sorokból felsorolás lesz.

```
Pick and place cella
Készítsen RoboDK-állomást egy ABB IRB 120 robottal és egy megfogóval!
- A robot vegyen fel egy dobozt az asztalról, és helyezze át egy másik pontra.
- Határozza meg a ciklusidőt!
```

Ezután a 3 feladatot egy közös jegyzőkönyvbe teheted (Windows-parancssor, ebben a mappában):

```
python dokumentacio\jegyzokonyv_keszito.py ^
    "C:\RoboDK_feladatok\Feladat1_dokumentacio" ^
    "C:\RoboDK_feladatok\Feladat2_dokumentacio" ^
    "C:\RoboDK_feladatok\Feladat3_dokumentacio" ^
    --nev "Vezetéknév Keresztnév" --neptun ABC123 --targy "Tantárgy neve" ^
    --intezmeny "Egyetem, kar, tanszék" --oktato "Oktató neve" ^
    --cim "RoboDK szimulációs feladatok" -o jegyzokonyv.docx --pdf
```

PowerShellben a sorok végén `^` helyett `` ` `` (backtick) kell, vagy írd az egészet egy sorba.

| Kapcsoló | Jelentés |
|---|---|
| `-o`, `--kimenet` | a Word-fájl neve (alapértelmezés: `jegyzokonyv.docx`) |
| `--cim`, `--targy`, `--intezmeny`, `--nev`, `--neptun`, `--oktato` | a címlap adatai |
| `--betutipus`, `--betumeret` | például `--betutipus "Times New Roman" --betumeret 12`, ha ez az előírás |
| `--pdf` | PDF is készül (Microsoft Word + `docx2pdf`, vagy telepített LibreOffice kell hozzá) |

**A jegyzőkönyv felépítése** (feladatonként egy fejezet):

1. A feladat leírása (a `feladat.txt` szövege)
2. A szimulációs környezet: RoboDK-verzió, robot, szerszám, csuklóhatárok
3. Az állomás felépítése: kép, referencia keretek, szerszám-TCP, objektumok
4. A megvalósítás lépései: minden lépés képpel és időponttal
5. Célpontok: koordináták, orientáció, csuklószögek
6. Programok és mérési eredmények (programonként):
   - utasításlista és fő eredmények
   - pályakép
   - csuklószög-, csuklósebesség- és TCP-sebesség-grafikon, TCP-pálya
   - csuklóstatisztika, csuklótartomány-kihasználtság, mozgásszakaszok, hibák
7. Mérések összehasonlítása (ha több mérés van)
8. Értékelés: a mérésekből automatikusan összeállított megállapítások és a saját értékelésed helye

A végén összefoglaló táblázat és a mellékletek (adatfájlok) listája következik.

---

## 4. Befejezés Wordben

1. **Töltsd ki a sárga `[KITÖLTENDŐ: …]` részeket.** Keresd meg őket a Ctrl+F `KITÖLTENDŐ` kereséssel, és
   töröld a kiemelést. Az automatikus értékelő mondatokat nyugodtan fogalmazd át a saját szavaiddal.
2. Megnyitáskor a Word megkérdezi, frissítse-e a mezőket. Válaszolj **Igen**-nel, ekkor a tartalomjegyzékbe
   bekerülnek az oldalszámok. Később is frissítheted: jobb klikk a tartalomjegyzékre → **Mező frissítése** (F9).
3. **PDF:** Fájl → Mentés másként → PDF (vagy a `--pdf` kapcsoló).
4. **Opcionális melléklet:** a RoboDK a szimulációt interaktív **3D HTML** vagy **3D PDF** fájlba is ki tudja
   exportálni: jobb klikk a programra → **Export Simulation** (Ctrl+E). A 3D PDF csak a Windowsos RoboDK-ban
   érhető el.

---

## Ha nem akarsz Pythont használni (kézi út)

Ugyanez a jegyzőkönyv kézzel is összeállítható, csak lassabban:

- **Képernyőképek:** Windowson a Win+Shift+S billentyűkkel, minden lépés után egyet.
- **Ciklusidő:** futtasd a programot, és olvasd le a jobb alsó sarokból.
- **Pálya ellenőrzése:** F5 / Shift+F5.
- **Célpont-koordináták:** dupla kattintás a célpontra.
- **Távolságok:** **Tools → Measure**.
- A mintajegyzőkönyv fejezetszerkezetét érdemes követni.

---

## Hibaelhárítás

| Probléma | Megoldás |
|---|---|
| Nem készül képernyőkép | Régebbi RoboDK esetén előfordul. Mentsd el kézzel a hibaüzenetben megadott néven, és a jegyzőkönyvbe bekerül. |
| Nem jelenik meg a szövegbeviteli ablak | A lépés „N. lépés (leírás pótlandó)” leírással mentődik. Javítsd a `lepesek.json`-ban. |
| „A program nem ellenőrizhető” figyelmeztetés | Például olyan főprogram, amely csak más programokat hív meg. Ilyenkor az alprogramok külön is mérve vannak. |
| A megoldás Python-szkript, amely közvetlenül mozgatja a robotot | Ilyenkor nincs mérhető program. A szkript hozzon létre RoboDK-programot (`RDK.AddProgram(...)`, `prog.MoveJ(...)`, `prog.MoveL(...)`), és azt mérd. |
| `ModuleNotFoundError: docx` vagy `matplotlib` | `python -m pip install -r requirements.txt` |
| Excelben a CSV egyetlen oszlopban jelenik meg | Adatok → Szövegből/CSV-ből, határoló: pontosvessző. |
| Nem készült PDF | Wordben: Fájl → Mentés másként → PDF. |
| Hiányzó mérés a jegyzőkönyvben | A jegyzőkönyv-készítő a `meres_*` mappákat keresi az adatmappában. Ellenőrizd, hogy a jó mappát adtad-e meg. |

---

## Tesztelés RoboDK nélkül

A `teszt/` mappában egy kitalált pick-and-place állomás található. Ez a RoboDK API viselkedését utánozza,
így a szkriptek RoboDK nélkül is kipróbálhatók:

```
python -m pip install robodk
python teszt/teszt_futtatas.py teszt/kimenet --hibas --ket-meres
python dokumentacio/jegyzokonyv_keszito.py teszt/kimenet/Minta_pick_and_place_dokumentacio -o teszt/kimenet/teszt.docx
```

A mintajegyzőkönyv (`pelda/`) újragenerálása:

```
cd pelda
python ../dokumentacio/jegyzokonyv_keszito.py Minta_pick_and_place_dokumentacio -o MINTA_jegyzokonyv.docx --minta --pdf
```

## Hasznos RoboDK-dokumentáció

- [Getting Started](https://robodk.com/doc/en/Getting-Started.html): állomás felépítése lépésről lépésre
- [Program menü](https://robodk.com/doc/en/Interface-Program-Menu.html): célpontok, programok, mozgásutasítások
- [Simulation event](https://robodk.com/doc/en/Robot-Programs-Simulation-event.html): tárgy megfogása és elengedése
- [Collision Detection](https://robodk.com/doc/en/Collision-Avoidance.html): ütközésvizsgálat
- [Export simulation](https://robodk.com/doc/en/General-Export-simulation.html): 3D HTML és 3D PDF export
- [Measure tool](https://robodk.com/doc/en/General-Measure-tool.html): mérés a 3D nézetben
- [RoboDK Python API](https://robodk.com/doc/en/PythonAPI/robodk.html): a szkriptek által használt függvények
