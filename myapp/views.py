from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, connection, transaction
from django.shortcuts import redirect, render

from .permisos import (
    ROLES,
    USAR_BASE_DE_DATOS,
    USUARIOS_DEMO,
    contexto_usuario,
    puede_modificar,
)



def dictfetchall(cursor):
    """Convierte el resultado de un cursor en una lista de diccionarios."""
    columnas = [col[0] for col in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def renderizar(request, plantilla, datos=None):
    """
    render() que además agrega usuario, rol y permisos al contexto,
    para que los templates sepan qué botones mostrar.
    """
    contexto = contexto_usuario(request)
    contexto.update(datos or {})
    return render(request, plantilla, contexto)


def _sesion_valida(request):
    return 'admin_id' in request.session and 'rol' in request.session


def login_requerido(vista):
    """Reemplazo casero de @login_required: mira la sesión, no request.user."""
    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        if not _sesion_valida(request):
            return redirect('login')
        return vista(request, *args, **kwargs)
    return envoltorio


def permiso_requerido(seccion, solo_post=False):
    """
    Deja pasar solo a los roles que pueden modificar `seccion`.
    - solo_post=False: se bloquea siempre (por ejemplo, eliminar).
    - solo_post=True: se bloquea solo al enviar el formulario (POST);
      ver la lista (GET) queda permitido para todos los roles.
    """
    def decorador(vista):
        @wraps(vista)
        def envoltorio(request, *args, **kwargs):
            es_escritura = (request.method == 'POST') if solo_post else True
            if es_escritura and not puede_modificar(request.session.get('rol'), seccion):
                messages.error(request, 'Tu rol no tiene permiso para realizar esta acción.')
                return redirect(seccion)
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador


# ---------- PÁGINA PÚBLICA ----------

def _estado_venta(fecha_inicio, fecha_fin):
    hoy = date.today()
    if fecha_fin and fecha_fin < hoy:
        return 'Finalizado'
    if fecha_inicio and fecha_inicio > hoy:
        return 'Próximo'
    return 'En curso'


def home_publico(request):
    """
    Página institucional, sin login. Es una vidriera: no muestra costes
    ni precios, solo proyectos, clientes y actividad reciente.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM proyecto")
        total_proyectos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM empresa_cliente")
        total_empresas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM consultor")
        total_consultores = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM venta")
        total_ventas = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT p.id, p.descripcion,
                   COUNT(v.id) AS veces_vendido,
                   MIN(v.fecha_inicio) AS primer_inicio,
                   MAX(v.fecha_fin) AS ultimo_fin
            FROM proyecto p
            LEFT JOIN venta v ON v.proyecto_id = p.id
            GROUP BY p.id, p.descripcion
            ORDER BY veces_vendido DESC, p.id DESC
            LIMIT 6
            """
        )
        proyectos_destacados = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.id, e.nombre, e.direccion,
                   COUNT(v.id) AS proyectos_contratados
            FROM empresa_cliente e
            LEFT JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre, e.direccion
            ORDER BY proyectos_contratados DESC, e.nombre
            LIMIT 12
            """
        )
        empresas_clientes = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.nombre AS empresa, p.descripcion AS proyecto,
                   v.fecha_inicio, v.fecha_fin
            FROM venta v
            JOIN empresa_cliente e ON v.empresa_id = e.id
            JOIN proyecto p ON v.proyecto_id = p.id
            ORDER BY v.fecha_inicio DESC
            LIMIT 8
            """
        )
        ventas_recientes = dictfetchall(cursor)

    for v in ventas_recientes:
        v['estado'] = _estado_venta(v['fecha_inicio'], v['fecha_fin'])

    return renderizar(request, 'myapp/home.html', {
        'total_proyectos': total_proyectos,
        'total_empresas': total_empresas,
        'total_consultores': total_consultores,
        'total_ventas': total_ventas,
        'proyectos_destacados': proyectos_destacados,
        'empresas_clientes': empresas_clientes,
        'ventas_recientes': ventas_recientes,
    })


# ---------- LOGIN / LOGOUT ----------

def autenticar(usuario, contrasena):
    """
    Devuelve {'id', 'usuario', 'rol'} si las credenciales son válidas, o None.
    Es el ÚNICO lugar que cambia al conectar el login con la base de datos
    (ver instrucciones en permisos.py).
    """
    if not USAR_BASE_DE_DATOS:
        datos = USUARIOS_DEMO.get(usuario)
        if datos and datos['contrasena'] == contrasena:
            return {'id': datos['id'], 'usuario': usuario, 'rol': datos['rol']}
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, usuario, contrasena, rol FROM administrador WHERE usuario = %s",
            [usuario],
        )
        filas = dictfetchall(cursor)

    if filas and check_password(contrasena, filas[0]['contrasena']):
        return {
            'id': filas[0]['id'],
            'usuario': filas[0]['usuario'],
            'rol': filas[0]['rol'],
        }
    return None


def login_view(request):
    if _sesion_valida(request):
        return redirect('inicio')

    if request.method == 'POST':
        persona = autenticar(request.POST.get('username'), request.POST.get('password'))
        if persona:
            request.session.cycle_key()
            request.session['admin_id'] = persona['id']
            request.session['admin_usuario'] = persona['usuario']
            request.session['rol'] = persona['rol']
            return redirect('inicio')
        messages.error(request, 'Usuario o contraseña incorrectos.')

    return renderizar(request, 'myapp/login.html', {
        'modo_demo': not USAR_BASE_DE_DATOS,
        'usuarios_demo': [
            {'usuario': u, 'contrasena': d['contrasena'], 'rol_nombre': ROLES[d['rol']]}
            for u, d in USUARIOS_DEMO.items()
        ],
    })


def logout_view(request):
    request.session.flush()
    return redirect('home')


# ---------- INICIO ----------

@login_requerido
def inicio(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM consultor")
        total_consultores = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM empresa_cliente")
        total_empresas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM proyecto")
        total_proyectos = cursor.fetchone()[0]

    return renderizar(request, 'myapp/inicio.html', {
        'total_consultores': total_consultores,
        'total_empresas': total_empresas,
        'total_proyectos': total_proyectos,
    })


# ---------- CONSULTORES (administrador y RRHH modifican) ----------

@login_requerido
@permiso_requerido('consultores', solo_post=True)
def consultores(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO consultor (codigo_empleado, nombre, sueldo, categoria_id, jefe_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    request.POST.get('codigo_empleado'),
                    request.POST.get('nombre'),
                    request.POST.get('sueldo'),
                    request.POST.get('categoria'),
                    request.POST.get('jefe') or None,
                ],
            )
        messages.success(request, 'Consultor cargado correctamente.')
        return redirect('consultores')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.codigo_empleado, c.nombre, c.sueldo,
                   cat.nombre AS categoria_nombre,
                   jefe.nombre AS jefe_nombre
            FROM consultor c
            JOIN categoria_profesional cat ON c.categoria_id = cat.id
            LEFT JOIN consultor jefe ON c.jefe_id = jefe.codigo_empleado
            """
        )
        lista_consultores = dictfetchall(cursor)

        cursor.execute("SELECT id, nombre FROM categoria_profesional")
        categorias = dictfetchall(cursor)

        cursor.execute("SELECT codigo_empleado, nombre FROM consultor")
        posibles_jefes = dictfetchall(cursor)

    return renderizar(request, 'myapp/consultores.html', {
        'consultores': lista_consultores,
        'categorias': categorias,
        'posibles_jefes': posibles_jefes,
    })


@login_requerido
@permiso_requerido('consultores')
def eliminar_consultor(request, pk):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM consultor WHERE codigo_empleado = %s", [pk])
        messages.success(request, 'Consultor eliminado.')
    except IntegrityError:
        messages.error(
            request,
            'No se puede eliminar: el consultor tiene ventas a cargo o personas que dependen de él.',
        )
    return redirect('consultores')


# ---------- EMPRESAS (solo administrador modifica) ----------

@login_requerido
@permiso_requerido('empresas', solo_post=True)
def empresas(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO empresa_cliente (nombre, direccion, cif) VALUES (%s, %s, %s)",
                [request.POST.get('nombre'), request.POST.get('direccion'), request.POST.get('cif')],
            )
            empresa_id = cursor.lastrowid
            telefono = request.POST.get('telefono')
            if telefono:
                cursor.execute(
                    "INSERT INTO telefono (numero, empresa_id) VALUES (%s, %s)",
                    [telefono, empresa_id],
                )
        messages.success(request, 'Empresa cargada correctamente.')
        return redirect('empresas')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT e.id, e.nombre, e.direccion, e.cif,
                   COUNT(v.id) AS proyectos_contratados
            FROM empresa_cliente e
            LEFT JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre, e.direccion, e.cif
            ORDER BY e.nombre
            """
        )
        lista_empresas = dictfetchall(cursor)

        cursor.execute("SELECT numero, empresa_id FROM telefono")
        telefonos = dictfetchall(cursor)

    telefonos_por_empresa = {}
    for t in telefonos:
        telefonos_por_empresa.setdefault(t['empresa_id'], []).append(t['numero'])

    for e in lista_empresas:
        e['telefonos'] = telefonos_por_empresa.get(e['id'], [])

    return renderizar(request, 'myapp/empresas.html', {'empresas': lista_empresas})


@login_requerido
@permiso_requerido('empresas')
def eliminar_empresa(request, pk):
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM telefono WHERE empresa_id = %s", [pk])
                cursor.execute("DELETE FROM empresa_cliente WHERE id = %s", [pk])
        messages.success(request, 'Empresa eliminada.')
    except IntegrityError:
        messages.error(request, 'No se puede eliminar: la empresa tiene proyectos contratados.')
    return redirect('empresas')


# ---------- PROYECTOS (solo administrador modifica) ----------

@login_requerido
@permiso_requerido('proyectos', solo_post=True)
def proyectos(request):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO proyecto (descripcion, coste) VALUES (%s, %s)",
                [request.POST.get('descripcion'), request.POST.get('coste')],
            )
        messages.success(request, 'Proyecto cargado correctamente.')
        return redirect('proyectos')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.descripcion, p.coste,
                   COUNT(v.id) AS veces_vendido,
                   GROUP_CONCAT(DISTINCT e.nombre ORDER BY e.nombre SEPARATOR ', ') AS clientes
            FROM proyecto p
            LEFT JOIN venta v ON v.proyecto_id = p.id
            LEFT JOIN empresa_cliente e ON v.empresa_id = e.id
            GROUP BY p.id, p.descripcion, p.coste
            ORDER BY p.id DESC
            """
        )
        lista_proyectos = dictfetchall(cursor)

    return renderizar(request, 'myapp/proyectos.html', {'proyectos': lista_proyectos})


@login_requerido
@permiso_requerido('proyectos')
def eliminar_proyecto(request, pk):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM proyecto WHERE id = %s", [pk])
        messages.success(request, 'Proyecto eliminado.')
    except IntegrityError:
        messages.error(request, 'No se puede eliminar: el proyecto ya fue vendido a alguna empresa.')
    return redirect('proyectos')


# ---------- SOLO DEBUG: contenido crudo de administrador ----------
# Solo para administradores. Borrala (y su ruta en urls.py) antes de entregar.

@login_requerido
def ver_admins(request):
    if request.session.get('rol') != 'administrador':
        messages.error(request, 'Solo los administradores pueden ver esta página.')
        return redirect('inicio')

    with connection.cursor() as cursor:
        cursor.execute("SELECT id, usuario, contrasena FROM administrador")
        admins = dictfetchall(cursor)
    return renderizar(request, 'myapp/admins.html', {'admins': admins})