"""Validación de los formularios de la aplicación."""

from datetime import datetime
from decimal import Decimal, InvalidOperation


CATEGORIAS_CAJA = {
    'cobro_proyecto': {'nombre': 'Cobro de proyecto', 'tipo': 'ingreso'},
    'cuota':          {'nombre': 'Cobro de cuota',    'tipo': 'ingreso'},
    'otro_ingreso':   {'nombre': 'Otro ingreso',      'tipo': 'ingreso'},
    'aporte':         {'nombre': 'Aporte de capital', 'tipo': 'ingreso'},
    'sueldo':         {'nombre': 'Pago de sueldo',    'tipo': 'egreso'},
    'gasto':          {'nombre': 'Gasto operativo',   'tipo': 'egreso'},
    'impuesto':       {'nombre': 'Impuestos',         'tipo': 'egreso'},
    'inversion':      {'nombre': 'Inversión',         'tipo': 'egreso'},
    'otro_egreso':    {'nombre': 'Otro egreso',       'tipo': 'egreso'},
}
LIMITE_CAJA = Decimal('999999999999.99')


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _decimal(valor):
    try:
        numero = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite() or numero < 0 or numero > LIMITE_CAJA:
        return None
    return numero.quantize(Decimal('0.01'))


def validar_movimiento_caja(post, empresas_lista, consultores_lista, ventas_lista):
    """Valida los datos recibidos para crear o editar un movimiento de caja."""
    errores = []
    try:
        fecha = datetime.strptime(post.get('fecha', ''), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        fecha = None

    categoria = post.get('categoria')
    monto_texto = post.get('monto', '')
    monto = _decimal(monto_texto)
    descripcion = post.get('descripcion', '').strip()
    empresa_id = _entero(post.get('empresa'))
    venta_id = _entero(post.get('venta'))
    consultor_id = _entero(post.get('consultor'))
    cuota_numero = _entero(post.get('cuota_numero'))
    cuotas_total = _entero(post.get('cuotas_total'))

    if fecha is None:
        errores.append('Ingresá una fecha válida.')
    if categoria not in CATEGORIAS_CAJA:
        errores.append('Elegí una categoría.')
    if monto is None or monto <= 0:
        errores.append('El monto tiene que ser un número mayor a 0 (máximo 999.999.999.999,99).')
    if len(descripcion) > 200:
        errores.append('La descripción no puede superar los 200 caracteres.')

    ventas_por_id = {v['id']: v for v in ventas_lista}
    if venta_id is not None:
        if venta_id in ventas_por_id:
            empresa_id = ventas_por_id[venta_id]['empresa_id']
        else:
            errores.append('La contratación elegida no es válida.')
    if empresa_id is not None and empresa_id not in {e['id'] for e in empresas_lista}:
        errores.append('La empresa elegida no es válida.')
    if consultor_id is not None and consultor_id not in {c['codigo_empleado'] for c in consultores_lista}:
        errores.append('El consultor elegido no es válido.')

    if categoria in ('cobro_proyecto', 'cuota') and empresa_id is None:
        errores.append('Un cobro tiene que estar asociado a una empresa (o a una contratación).')
    if categoria == 'sueldo' and consultor_id is None:
        errores.append('Elegí a qué consultor corresponde el sueldo.')

    if categoria == 'cuota' and (cuota_numero or cuotas_total):
        if not (cuota_numero and cuotas_total and 1 <= cuota_numero <= cuotas_total <= 360):
            errores.append('Cuota inválida: completá el número y el total (el número no puede superar al total).')
    if categoria != 'cuota':
        cuota_numero = cuotas_total = None

    datos = {
        'fecha': fecha.isoformat() if fecha else post.get('fecha', ''),
        'categoria': categoria or '',
        'monto_texto': monto_texto,
        'descripcion': descripcion,
        'empresa_id': empresa_id,
        'venta_id': venta_id,
        'consultor_id': consultor_id,
        'cuota_numero': cuota_numero,
        'cuotas_total': cuotas_total,
        'fecha_db': fecha,
        'monto_db': monto,
        'tipo_db': CATEGORIAS_CAJA[categoria]['tipo'] if categoria in CATEGORIAS_CAJA else None,
    }
    return datos, errores
