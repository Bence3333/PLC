# RoboDK mérési feladatok: megvalósítás és dokumentálás (Word/PDF jegyzőkönyv)

Eszközkészlet három RoboDK-s mérési feladathoz:

1. Pick & Place modern robottal
2. Pályakövetés csuklós robottal
3. Precíziós mozgás orvosi robottal, tiltott zónával

A RoboDK-ban elvégzett **munkalépéseket képernyőképpel**, a **méréseket automatikusan** rögzíti. Ezekből egyetlen
paranccsal **kész Word (.docx) és PDF jegyzőkönyvet** készít, amelyben van címlap, tartalomjegyzék, táblázatok,
grafikonok és automatikus értékelés. Neked a megoldást kell elkészítened a RoboDK-ban, és a jegyzőkönyvben
sárgával kiemelt `[KITÖLTENDŐ]` részeket kell megírnod.

> **Itt kezdd: [UTMUTATO.md](UTMUTATO.md)** (nyomtatható változat: [UTMUTATO.pdf](UTMUTATO.pdf)).
> Lépésről lépésre, kattintásról kattintásra leírja mindhárom feladat megoldását, a mérést, a jegyzőkönyv
> elkészítését és azt, hogy mit írj az értékelésbe. Ez a README az eszközök részletes leírása.

**Így néz ki a végeredmény:** [`pelda/MINTA_jegyzokonyv.pdf`](pelda/MINTA_jegyzokonyv.pdf), mindhárom feladattal.
A minta **szimulált, fiktív adatokkal** készült, a képek helyén vázlatok vannak. Csak a formát mutatja, beadni nem lehet.

| Fájl | Mire való | Hol fut |
|---|---|---|
| [`UTMUTATO.md`](UTMUTATO.md), [`UTMUTATO.pdf`](UTMUTATO.pdf) | **Lépésről lépésre útmutató** a 3 feladathoz | olvasd el |
| [`robodk_scripts/cella_epito.py`](robodk_scripts/cella_epito.py) | **Mintamegoldás:** felépíti a választott feladat celláját (szerszám, keret, asztal, munkadarab, tiltott zóna), célpontjait és a sebességváltozatokat tartalmazó programjait | a RoboDK-ban |
| [`robodk_scripts/doboz_letrehozasa.py`](robodk_scripts/doboz_letrehozasa.py) | Megadott méretű, színű doboz (asztallap, munkadarab, tiltott zóna) a kijelölt keretben, a kézi megoldáshoz | a RoboDK-ban |
| [`robodk_scripts/lepes_rogzitese.py`](robodk_scripts/lepes_rogzitese.py) | Lépésnapló: rövid leírás és képernyőkép minden munkalépésről | a RoboDK-ban |
| [`robodk_scripts/meresek_rogzitese.py`](robodk_scripts/meresek_rogzitese.py) | Mérések: idők, utak, sebességek, célpontok elérésének pontossága, tengelyek elfordulása, ütközés, tiltott zóna, képek | a RoboDK-ban |
| [`dokumentacio/jegyzokonyv_keszito.py`](dokumentacio/jegyzokonyv_keszito.py) | Word- és PDF-jegyzőkönyv a rögzített adatokból | a saját gépeden, Pythonnal |
| [`pelda/`](pelda/) | Mintajegyzőkönyv és mintaadatok (**fiktív**) | – |
| [`teszt/`](teszt/) | RoboDK nélküli tesztkörnyezet (szimulált állomás) | a saját gépeden |

---

## A munkafolyamat röviden

```
 0. Előkészületek        RoboDK + Python, feladatonként külön .rdk állomás
 1. Megvalósítás          kézzel az UTMUTATO.md szerint             ┐ minden fontos lépés után:
                          (vagy mintamegoldás: cella_epito.py)      ┘ lepes_rogzitese.py
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
  │   ├── feladat.txt             ← a feladat címe és szövege (a cella_epito.py megírja, kézzel is megírhatod)
  │   ├── lepesek.json + kepek/   ← lépésnapló
  │   └── meres_20261002_143512/  ← mérések (minden futtatás egy új mappa)
  ├── Feladat2_dokumentacio/
  └── Feladat3_dokumentacio/
  ```
  Az állomás neve a RoboDK fa gyökéreleme. Mentés után ez általában megegyezik az `.rdk` fájl nevével.
  **Az első lépés rögzítése előtt mentsd el az állomást.**

A szkripteket úgy futtatod, hogy behúzod a `.py` fájlt a RoboDK ablakába (vagy **File → Open**), majd duplán
kattintasz a fában megjelenő elemre. A szkript az állomásba mentődik, ezért elég egyszer behúzni.

---

## 1. Megvalósítás a RoboDK-ban

A három feladat kattintásról kattintásra az **[UTMUTATO.md](UTMUTATO.md)** 1–3. fejezetében található,
koordinátákkal, sebességekkel és programlistákkal. A leggyakoribb műveletek:

| Lépés | Hogyan (RoboDK, angol menü) |
|---|---|
| Robot betöltése | **File → Open online library** (Ctrl+Shift+O) → szűrés gyártóra → **Open** |
| Szerszám | jelöld ki a robotot → **Program → Add Empty Tool**, a TCP a szerszámra duplán kattintva állítható; vagy egy könyvtári megfogót húzz rá a robotra a fában |
| Referencia keret | **Program → Add Reference Frame**, a helyzete a keret ablakában adható meg |
| Doboz (asztal, munkadarab, tiltott zóna) | jelöld ki a keretet → `doboz_letrehozasa.py`; vagy **File → Open** (STL/STEP), majd a fában húzd a keret alá |
| Célpontok | állítsd a robotot a kívánt helyzetbe (robot ablaka: *Tool … w.r.t. Reference*), majd **Program → Teach Target** (Ctrl+T) |
| Program | **Program → Add Program**, utána **Move Joint Instruction** / **Move Linear Instruction** |
| Sebesség, lekerekítés, várakozás | **Program → Set Speed / Set Rounding / Pause Instruction** |
| Megfogás szimulációja | **Program → Simulation Event Instruction** → *Attach object* / *Detach object* |
| Szimuláció | dupla kattintás a programra. A becsült ciklusidő a futás végén a jobb alsó sarokban látszik |
| Ellenőrzés | jobb klikk a programra → **Check path** (F5), illetve **Check path and collisions** (Shift+F5) |
| Ütközésvizsgálat | **Tools → Check collisions**, a vizsgált párok: **Tools → Collision map** (Shift+X) |
| Mentés | **File → Save Station** (Ctrl+S) |

### Mintamegoldás: `cella_epito.py`

Az új állomásba töltsd be a javasolt robotot, mentsd el az állomást, majd futtasd a szkriptet, és válaszd ki a
feladat számát:

| Feladat | Javasolt robot | Amit felépít |
|---|---|---|
| 1. Pick & Place | Universal Robots UR5e | megfogó, asztal, 50 mm-es kocka, lerakóhely; `PP_MoveJ_*` és `PP_MoveL_*` 3 sebességgel, `PP_ismetles_3x`; megfogás és elengedés (Python-makrók) |
| 2. Pályakövetés | ABB IRB 120-3/0.6 | toll, `Palya` keret, rajzlap; 150 mm-es négyzet: `Negyzet_lassu`/`_gyors`, pontos és lekerekített sarkokkal |
| 3. Precíziós mozgás | KUKA LBR iiwa 7 R800 | műszer, műtőasztal, 60 mm-es tiltott zóna, C1–C3 célpontok biztonsági pontokkal; `Precizios_*` 3 sebességgel + lekerekített változat |

Más 6 vagy 7 tengelyes robottal is működik: a szkript megkeresi azt a távolságot a robottól, ahol minden pont
elérhető és minden mozgás végrehajtható. Ha a cellát újraépíted, előtte törli a korábban létrehozott elemeket.
A feladat szövegét a `feladat.txt`-be írja.

### Lépések rögzítése: `lepes_rogzitese.py`

1. **Minden fontos lépés után** állítsd be a 3D nézetet, majd kattints duplán a `lepes_rogzitese` elemre.
2. Írd be röviden, mit csináltál, például: *„Asztal referencia keret létrehozása, X = 400 mm”*.
   A szkript elmenti a leírást, a 3D nézet képét és az előző lépés óta létrejött új elemek nevét (ezeket
   javaslatként fel is kínálja).

A lépések a `<állomás>_dokumentacio/lepesek.json` fájlba kerülnek. Ezt Jegyzettömbbel utólag is javíthatod:
a leírás szövegét átírhatod, egy rossz lépést törölhetsz. A képek a `kepek/lepes_NN.png` fájlokba kerülnek.
Ha egy kép nem készült el (régebbi RoboDK esetén előfordulhat), mentsd el kézzel pontosan ezen a néven,
és a jegyzőkönyvbe automatikusan bekerül.

---

## 2. Mérések: `meresek_rogzitese.py`

Amikor a megoldás kész, állítsd be a 3D nézetet (erről készülnek a képek), és futtasd a `meresek_rogzitese`
elemet. Megkérdezi a mérés nevét. Ez nem kötelező, de hasznos, például *„v = 300 mm/s”* vagy *„végleges változat”*.

A szkript **minden programot** végigmér, az eredmények új `meres_ÉÉÉÉHHNN_ÓÓPPMM/` mappába kerülnek.
Mérés előtt a robotot a program első célpontjába állítja, így a ciklusidő nem függ attól, hol állt a robot, és a
végén visszaállítja. Az **`x_` kezdetű nevű programokat** (például próbaprogramokat) kihagyja.

**Ha több változatot próbálsz ki** (más sebesség, lekerekítés, MoveJ vagy MoveL), mindegyik után futtasd le újra.
A jegyzőkönyv a legutolsó mérést részletezi, az összes mérést pedig táblázatban és grafikonon összehasonlítja.
Ha egy mérést nem akarsz a jegyzőkönyvbe, nevezd át a mappáját, például `x_meres_...` névre.

### Mit mér, és hol ellenőrizheted kézzel?

| Mérés | Honnan (RoboDK Python API) | Kézi ellenőrzés a RoboDK-ban |
|---|---|---|
| Becsült ciklusidő, TCP-pályahossz | `program.Update()` | program futtatása után a jobb alsó sarokban |
| Végrehajtható rész (érvényesség, %) | `program.Update()` | F5 (Check path) |
| Ütközés | `program.Update(COLLISION_ON)` | Shift+F5, Tools → Check collisions |
| Célpontok helyzete (X, Y, Z, Rx, Ry, Rz) és csuklószögei | `target.Pose()`, `target.Joints()` | dupla kattintás a célpontra |
| Csuklószögek, szögsebességek és -gyorsulások az idő függvényében | `program.InstructionListJoints(flags=4)` (időalapú pálya) | a robot ablaka szimuláció közben |
| TCP-pályasebesség (átlag, maximum), felül- és oldalnézeti pálya | a pálya TCP-pozícióiból számolva | – |
| Célpontonként: érkezés, szakaszidő, szakaszhossz, a tengelyek elfordulása (ΔJ) | a pályából, a célpont TCP-helyzete alapján | – |
| A célpont elérésének pontossága (eltérés, mm), MoveL-nél az egyenestől való eltérés | a célpont és a pálya legkisebb távolsága | – |
| Ugyanazon célpont ismételt elérésének eltérése, a program kezdő- és végpontjának távolsága | a pályából | – |
| Idő a felvételtől a lerakásig (1. feladat) | a felvételi és a lerakási célpont neve alapján | – |
| A TCP legkisebb távolsága a tiltott zónától (3. feladat) | a „tiltott”, „zona” vagy „akadaly” nevű dobozokhoz | Tools → Measure |
| Csuklóhatárok, kihasználtság, szingularitás, elérhetetlen pont | `robot.JointLimits()` + a pálya hibakódjai | a robot ablaka, F5 üzenetei |
| Képernyőképek (állomás, pálya „szellemrobotokkal”) | `Cam2D_Snapshot()`, `ShowSequence()` | – |

**Kimenet:** `meresek.json` (minden adat), `programok.csv`, `celpontok.csv`, valamint programonként
`palya_<program>.csv` és `celpontok_<program>.csv`. Ezek pontosvesszővel tagolt, tizedesvesszős fájlok, amelyeket
a magyar Excel közvetlenül megnyit. A képek a `kepek/` mappába kerülnek. A szkript elején néhány beállítás
módosítható (`IDOLEPES_S`, `UTKOZESVIZSGALAT`, `KEPERNYOKEPEK`, `SZELLEM_ROBOTOK`, `CELPONT_TUR_MM`,
`ZONA_KULCSSZAVAK`, `KIHAGYOTT_ELOTAG`).

> **A szimuláció korlátja (az értékelésbe is írd bele).** A RoboDK ideális kinematikai modellel számol. A megálló
> (pontos) célpontokat a robot sebességtől függetlenül pontosan eléri, és ugyanaz a program mindig ugyanazt adja,
> ezért a szimulációban mért pontosság és ismételhetőség ideális. Eltérést csak a lekerekítés (blending) okoz,
> amelynek mértéke nem a sebességtől függ. Valódi robotnál a nagyobb sebesség dinamikai pályahibát okoz, és az
> ismételhetőséget az adatlap adja meg (ISO 9283). A ciklusidő a beállított sebességekből és gyorsulásokból
> számolt becslés. Részletesen: [UTMUTATO.md, 0.5](UTMUTATO.md#05-fontos-szakmai-háttér-mit-mér-a-szimuláció-és-mit-nem).

---

## 3. A jegyzőkönyv elkészítése: `jegyzokonyv_keszito.py`

Minden adatmappában legyen egy **`feladat.txt`** fájl (UTF-8). Ezt a `cella_epito.py` megírja. Kézi megoldásnál
másold bele a feladat szövegét: az első sor a feladat címe, a többi sor a feladat szövege. A `- ` kezdetű
sorokból felsorolás lesz.

```
Modern robot: Pick & Place rendszer
Feladat: Programozz be egy modern, 6 tengelyes robotkart, amely egy munkadarabot felvesz egy kiindulási pontról, majd egy másik helyre áthelyezi.
Mérendő adatok:
- A robot által megtett idő a felvételtől a lerakásig.
- A mozgás során megtett út.
```

Ezután a 3 feladatot egy közös jegyzőkönyvbe teheted (Windows-parancssor, ebben a mappában):

```
python dokumentacio\jegyzokonyv_keszito.py ^
    "C:\RoboDK_feladatok\Feladat1_dokumentacio" ^
    "C:\RoboDK_feladatok\Feladat2_dokumentacio" ^
    "C:\RoboDK_feladatok\Feladat3_dokumentacio" ^
    --nev "Vezetéknév Keresztnév" --neptun ABC123 --targy "Tantárgy neve" ^
    --intezmeny "Egyetem, kar, tanszék" --oktato "Oktató neve" ^
    --cim "RoboDK mérési feladatok" -o jegyzokonyv.docx --pdf
```

PowerShellben a sorok végén `^` helyett `` ` `` (backtick) kell, vagy írd az egészet egy sorba.

| Kapcsoló | Jelentés |
|---|---|
| `-o`, `--kimenet` | a Word-fájl neve (alapértelmezés: `jegyzokonyv.docx`) |
| `--cim`, `--targy`, `--intezmeny`, `--nev`, `--neptun`, `--oktato` | a címlap adatai |
| `--betutipus`, `--betumeret` | például `--betutipus "Times New Roman" --betumeret 12`, ha ez az előírás |
| `--reszletes` | programonként a csuklósebesség- és a csuklótartomány-grafikon is bekerül (hosszabb jegyzőkönyv) |
| `--pdf` | PDF is készül (Microsoft Word + `docx2pdf`, vagy telepített LibreOffice kell hozzá) |

**A jegyzőkönyv felépítése:**

- **Bevezetés**, benne *Mérési módszer és korlátai*
- **Feladatonként egy fejezet:**
  1. A feladat leírása (a `feladat.txt` szövege)
  2. A szimulációs környezet: RoboDK-verzió, robot, szerszám, csuklóhatárok
  3. Az állomás felépítése: kép, referencia keretek, szerszám-TCP, objektumok, tiltott zóna
  4. A megvalósítás lépései: minden lépés képpel és időponttal
  5. Célpontok: koordináták, orientáció, csuklószögek
  6. Programok és mérési eredmények, programonként:
     - utasításlista és fő eredmények
     - a célpontok elérése: érkezés, szakaszidő, úthossz, eltérés
     - a tengelyek elfordulása
     - pályakép
     - grafikonok: csuklószögek, TCP-sebesség, TCP-pálya, a tiltott zónától mért távolság
     - csuklóstatisztika
  7. Programok összehasonlítása: ciklusidők, MoveJ és MoveL, sebességszintek, pontosság, felülnézeti pályák
  8. Mérések összehasonlítása (ha több mérés van)
  9. Értékelés: a mérésekből automatikusan összeállított megállapítások és a saját értékelésed helye
- **Összefoglalás** és **Mellékletek** (az adatfájlok listája)

---

## 4. Befejezés Wordben

1. **Töltsd ki a sárga `[KITÖLTENDŐ: …]` részeket.** Keresd meg őket a Ctrl+F `KITÖLTENDŐ` kereséssel, és
   töröld a kiemelést. Az automatikus értékelő mondatokat nyugodtan fogalmazd át a saját szavaiddal. Segítség:
   [UTMUTATO.md, 6. fejezet](UTMUTATO.md#6-mit-írj-az-értékelésbe).
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
| A `cella_epito.py` nem talál elrendezést | Más robotnál a pontok elérhetetlenek lehetnek. Használd a javasolt robotot, vagy módosítsd a koordinátákat a szkriptben. |
| „A program nem ellenőrizhető” figyelmeztetés | Például olyan főprogram, amely csak más programokat hív meg. Ilyenkor az alprogramok külön is mérve vannak. |
| A megoldás Python-szkript, amely közvetlenül mozgatja a robotot | Ilyenkor nincs mérhető program. A szkript hozzon létre RoboDK-programot (`RDK.AddProgram(...)`, `prog.MoveJ(...)`, `prog.MoveL(...)`), és azt mérd. |
| Túl hosszú a jegyzőkönyv | A próbaprogramok nevét kezdd `x_`-szel, és a régi `meres_*` mappákat nevezd át (`x_meres_…`). |
| `ModuleNotFoundError: docx` vagy `matplotlib` | `python -m pip install -r requirements.txt` |
| Excelben a CSV egyetlen oszlopban jelenik meg | Adatok → Szövegből/CSV-ből, határoló: pontosvessző. |
| Nem készült PDF | Wordben: Fájl → Mentés másként → PDF. |
| Hiányzó mérés a jegyzőkönyvben | A jegyzőkönyv-készítő a `meres_*` mappákat keresi az adatmappában. Ellenőrizd, hogy a jó mappát adtad-e meg. |

További hibák és megoldásuk: [UTMUTATO.md, 5. fejezet](UTMUTATO.md#5-gyakori-hibák).

---

## Tesztelés RoboDK nélkül

A `teszt/robodk_szimulacio.py` a RoboDK API-t utánozza (egyszerűsített kinematikával, a valódi `robodk` csomag
függvényaláírásaival). A teszt mindhárom feladatnál végigfuttatja a teljes folyamatot: lépésnapló →
`cella_epito.py` → `meresek_rogzitese.py` → ellenőrzések. Az adatok **fiktívek**.

```
python -m pip install robodk numpy
python teszt/teszt_futtatas.py teszt/kimenet
python teszt/teszt_futtatas.py teszt/kimenet --feladat 2 --xyz-allomasban
python dokumentacio/jegyzokonyv_keszito.py teszt/kimenet/Feladat1_dokumentacio teszt/kimenet/Feladat2_dokumentacio teszt/kimenet/Feladat3_dokumentacio -o teszt/kimenet/teszt.docx
```

A `--feladat` kapcsolóval csak a megadott feladatok futnak. Az `--xyz-allomasban` kapcsoló a direkt kinematikás
ágat teszteli, amikor a pályaadat XYZ oszlopai nem a robot bázisához képest értendők.

A mintajegyzőkönyv (`pelda/`) újragenerálása:

```
cd pelda
python ../dokumentacio/jegyzokonyv_keszito.py Feladat1_dokumentacio Feladat2_dokumentacio Feladat3_dokumentacio -o MINTA_jegyzokonyv.docx --minta --nev "Minta Hallgató" --neptun MINTA1 --targy "Ipari robotok programozása" --cim "RoboDK mérési feladatok" --pdf
```

## Hasznos RoboDK-dokumentáció

- [Getting Started](https://robodk.com/doc/en/Getting-Started.html): állomás felépítése lépésről lépésre
- [Program menü](https://robodk.com/doc/en/Interface-Program-Menu.html): célpontok, programok, mozgásutasítások
- [Program instructions](https://robodk.com/doc/en/Robot-Programs-Program-Instructions.html): Set Speed, Set Rounding, Pause
- [Simulation event](https://robodk.com/doc/en/Robot-Programs-Simulation-event.html): tárgy megfogása és elengedése
- [Collision Detection](https://robodk.com/doc/en/Collision-Avoidance.html): ütközésvizsgálat
- [Export simulation](https://robodk.com/doc/en/General-Export-simulation.html): 3D HTML és 3D PDF export
- [Measure tool](https://robodk.com/doc/en/General-Measure-tool.html): mérés a 3D nézetben
- [RoboDK Python API](https://robodk.com/doc/en/PythonAPI/robodk.html): a szkriptek által használt függvények
