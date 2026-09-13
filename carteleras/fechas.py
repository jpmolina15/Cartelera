"""La semana de cartelera argentina: de jueves a miércoles.

Los estrenos entran el jueves, así que ésa es la unidad que hay que publicar.
Tomar en cambio "los próximos N días" parte la semana al medio: la corrida del
jueves 10/09/2026 publicó jueves a lunes y dejó afuera el martes y el miércoles.
"""
import datetime

JUEVES = 3  # datetime.weekday(): lunes=0


def semana(hoy=None):
    """Los siete días ISO del jueves al miércoles que contienen a `hoy`."""
    hoy = hoy or datetime.date.today()
    jueves = hoy - datetime.timedelta(days=(hoy.weekday() - JUEVES) % 7)
    return [(jueves + datetime.timedelta(days=i)).isoformat() for i in range(7)]


def ventana(hoy=None):
    """La semana en curso desde hoy.

    Los días ya pasados se descartan: ninguna sala publica sus funciones y el
    Gaumont, que programa por día de semana, las reconstruiría igual dando una
    página con horarios de ayer.
    """
    hoy = hoy or datetime.date.today()
    return [d for d in semana(hoy) if d >= hoy.isoformat()]
