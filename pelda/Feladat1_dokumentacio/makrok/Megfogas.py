# -*- coding: utf-8 -*-
# A cella_epito.py hozta létre: szimulációs esemény a(z) Megfogas lépéshez.
try:
    from robodk import robolink, robomath
except ImportError:
    import robolink
    import robodk as robomath
RDK = robolink.Robolink()
darab = RDK.Item('Munkadarab', robolink.ITEM_TYPE_OBJECT)
darab.setParentStatic(RDK.Item('Megfogo', robolink.ITEM_TYPE_TOOL))
