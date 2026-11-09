"""
Usuarios, roles y permisos.

- Los USUARIOS y sus contraseñas (hasheadas) viven en la base de datos: tabla "usuarios"
  (ver crear_usuarios.sql). Acá no se guarda ninguno.
- Cada usuario tiene un ROL que trae un conjunto de permisos, y el administrador principal
  puede sumarle PERMISOS EXTRA uno por uno (tabla "usuario_permiso").
- Qué permisos existen y qué trae cada rol se define en este archivo, porque cada permiso
  corresponde a algo que el código controla. A quién se le da cada uno se guarda en la base.
- La cuenta PRINCIPAL (la única con es_principal = 1) tiene todo, más el panel de usuarios.
"""
import re

from django.db import connection

# Si es True, las cuentas nuevas quedan inactivas hasta que el administrador las apruebe.
REGISTRO_REQUIERE_APROBACION = False

ROLES = {
    'administrador': 'Administrador',
    'rrhh': 'Recursos Humanos',
    'operario': 'Operario',
}

PERMISOS = {
    'consultores.modificar': {'etiqueta': 'Modificar consultores',
                              'descripcion': 'Agregar, editar y eliminar consultores (las personas)'},
    'empresas.modificar':    {'etiqueta': 'Modificar empresas',
                              'descripcion': 'Agregar, editar y eliminar empresas clientes'},
    'proyectos.modificar':   {'etiqueta': 'Modificar proyectos',
                              'descripcion': 'Agregar, editar y eliminar proyectos'},
    'sueldos.ver':           {'etiqueta': 'Ver sueldos',
                              'descripcion': 'Ver el sueldo de cada consultor'},
    'finanzas.ver':          {'etiqueta': 'Ver finanzas',
                              'descripcion': 'Ver precios de venta, costes y márgenes'},
    'caja.ver':              {'etiqueta': 'Ver la caja',
                              'descripcion': 'Ver los movimientos y resúmenes de la caja (solo lectura)'},
    'caja.modificar':        {'etiqueta': 'Modificar la caja',
                              'descripcion': 'Agregar, editar y eliminar movimientos de la caja (incluye ver la caja)'},
}

# Permisos que trae cada rol. Operario = solo mirar.
PERMISOS_POR_ROL = {
    'administrador': set(PERMISOS),
    'rrhh': {'consultores.modificar', 'sueldos.ver'},
    'operario': set(),
}

# Tener un permiso implica tener estos otros.
IMPLICA = {'caja.modificar': {'caja.ver'}}

# Solo la cuenta principal lo tiene (no se puede dar desde el panel).
PERMISO_GESTIONAR_USUARIOS = 'usuarios.gestionar'


def permisos_efectivos(rol, extras):
    """Permisos de un usuario: los de su rol + los extra que le dieron (+ lo que implican)."""
    efectivos = set(PERMISOS_POR_ROL.get(rol, set())) | (set(extras) & set(PERMISOS))
    for permiso in list(efectivos):
        efectivos |= IMPLICA.get(permiso, set())
    return efectivos


# ---------- usuario logueado (se lee de la base en cada petición) ----------

def usuario_actual(request):
    """
    Devuelve el usuario logueado como diccionario, o None si no hay sesión válida
    o la cuenta fue desactivada/eliminada. Se lee de la base en cada petición, así que
    un cambio de permisos o de rol vale desde el siguiente clic, sin volver a iniciar sesión.
    """
    if hasattr(request, '_usuario_cache'):
        return request._usuario_cache

    usuario = None
    usuario_id = request.session.get('usuario_id')
    if usuario_id is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, usuario, rol, es_principal, activo FROM usuarios WHERE id = %s",
                [usuario_id],
            )
            fila = cursor.fetchone()
            if fila and fila[4]:
                cursor.execute(
                    "SELECT permiso FROM usuario_permiso WHERE usuario_id = %s", [usuario_id]
                )
                extras = {f[0] for f in cursor.fetchall()}
                es_principal = bool(fila[3])
                if es_principal:
                    permisos = set(PERMISOS) | {PERMISO_GESTIONAR_USUARIOS}
                else:
                    permisos = permisos_efectivos(fila[2], extras)
                usuario = {
                    'id': fila[0], 'usuario': fila[1], 'rol': fila[2],
                    'es_principal': es_principal, 'permisos': permisos,
                }

    request._usuario_cache = usuario
    return usuario


def tiene_permiso(request, permiso):
    usuario = usuario_actual(request)
    return bool(usuario) and permiso in usuario['permisos']


def contexto_usuario(request):
    """Datos del usuario logueado y sus permisos, listos para los templates."""
    usuario = usuario_actual(request)
    permisos = usuario['permisos'] if usuario else set()
    if usuario and usuario['es_principal']:
        rol_nombre = 'Administrador principal'
    else:
        rol_nombre = ROLES.get(usuario['rol'], '') if usuario else ''
    return {
        'admin_usuario': usuario['usuario'] if usuario else None,
        'rol': usuario['rol'] if usuario else None,
        'rol_nombre': rol_nombre,
        'es_principal': bool(usuario and usuario['es_principal']),
        'puede_modificar_consultores': 'consultores.modificar' in permisos,
        'puede_modificar_empresas': 'empresas.modificar' in permisos,
        'puede_modificar_proyectos': 'proyectos.modificar' in permisos,
        'puede_ver_sueldos': 'sueldos.ver' in permisos,
        'puede_ver_finanzas': 'finanzas.ver' in permisos,
        'puede_ver_caja': 'caja.ver' in permisos,
        'puede_modificar_caja': 'caja.modificar' in permisos,
        'puede_gestionar_usuarios': PERMISO_GESTIONAR_USUARIOS in permisos,
    }


# ---------- validación de cuentas ----------

PATRON_USUARIO = re.compile(r'[A-Za-z0-9._-]{3,50}')


def validar_clave(clave, usuario=''):
    errores = []
    if len(clave) < 8:
        errores.append('La contraseña tiene que tener al menos 8 caracteres.')
    elif len(clave) > 128:
        errores.append('La contraseña no puede superar los 128 caracteres.')
    if clave.isdigit():
        errores.append('La contraseña no puede ser solo números.')
    if usuario and clave.lower() == usuario.lower():
        errores.append('La contraseña no puede ser igual al usuario.')
    return errores


def validar_alta(usuario, clave, repetir):
    errores = []
    if not PATRON_USUARIO.fullmatch(usuario):
        errores.append(
            'El usuario tiene que tener entre 3 y 50 caracteres: letras, números, punto, guion o guion bajo.'
        )
    errores += validar_clave(clave, usuario)
    if clave != repetir:
        errores.append('Las contraseñas no coinciden.')
    return errores