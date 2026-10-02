# -*- coding: utf-8 -*-
# A cella_epito.py hozta létre: szimulációs esemény a(z) Alaphelyzet lépéshez.
try:
    from robodk import robolink, robomath
except ImportError:
    import robolink
    import robodk as robomath
RDK = robolink.Robolink()
darab = RDK.Item('Munkadarab', robolink.ITEM_TYPE_OBJECT)
darab.setParent(RDK.Item('Asztal', robolink.ITEM_TYPE_FRAME))
darab.setPose(robomath.transl(0, -200, 0))
