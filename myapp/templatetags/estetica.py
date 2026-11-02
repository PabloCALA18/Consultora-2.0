from django import template

register = template.Library()

# Colores de Bootstrap que se reparten entre empresas, proyectos y consultores.
COLORES = ['primary', 'success', 'danger', 'warning', 'info', 'secondary', 'dark']


@register.filter
def color_por_id(valor):
    """Devuelve siempre el mismo color para el mismo id (para íconos y avatares)."""
    try:
        return COLORES[int(valor) % len(COLORES)]
    except (TypeError, ValueError):
        return 'secondary'


@register.filter
def iniciales(nombre):
    """'María Pérez' -> 'MP'"""
    partes = str(nombre or '').split()
    return ''.join(p[0] for p in partes[:2]).upper() or '?'