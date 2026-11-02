from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.contrib.staticfiles import finders
from django.db import IntegrityError, connection, transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.templatetags.static import static

from .fundadores import FUNDADORES
from .permisos import (
    ROLES,
    ROLES_VEN_FINANZAS,
    USAR_BASE_DE_DATOS,
    USUARIOS_DEMO,
    contexto_usuario,
    puede_modificar,
)


# ---------- HELPERS ----------

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
    contexto['ve_finanzas'] = request.session.get('rol') in ROLES_VEN_FINANZAS  
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

        cursor.execute(
            """
            SELECT cat.nombre, COUNT(c.codigo_empleado) AS cantidad
            FROM categoria_profesional cat
            LEFT JOIN consultor c ON c.categoria_id = cat.id
            GROUP BY cat.id, cat.nombre
            ORDER BY cat.id
            """
        )
        categorias_equipo = dictfetchall(cursor)

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
        'categorias_equipo': categorias_equipo,
        'fundadores': _fundadores(),
    })


# ---------- QUIÉNES SOMOS (fundadores) ----------

EXTENSIONES_FOTO = ('jpg', 'jpeg', 'png', 'webp')


def _foto_de(slug):
    """URL de la foto si existe myapp/static/myapp/img/fundadores/<slug>.<ext>, o None."""
    for extension in EXTENSIONES_FOTO:
        ruta = f'myapp/img/fundadores/{slug}.{extension}'
        if finders.find(ruta):
            return static(ruta)
    return None


def _fundadores():
    return [dict(f, foto=_foto_de(f['slug'])) for f in FUNDADORES]


def fundador_detalle(request, slug):
    """Página pública con la biografía completa y los proyectos de un fundador."""
    fundadores = _fundadores()
    fundador = next((f for f in fundadores if f['slug'] == slug), None)
    if fundador is None:
        raise Http404('Fundador no encontrado')

    return renderizar(request, 'myapp/fundador_detalle.html', {
        'fundador': fundador,
        'otros_fundadores': [f for f in fundadores if f['slug'] != slug],
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


# ---------- CONTRATACIONES (consulta compartida) ----------

def _ventas(cursor, filtro='', parametros=None):
    """
    Contrataciones (tabla venta) con los nombres de empresa, proyecto y consultor.
    `filtro` es un WHERE escrito por nosotros (nunca texto del usuario);
    los valores van siempre en `parametros`.
    """
    cursor.execute(
        f"""
        SELECT v.id, v.precio, v.fecha_inicio, v.fecha_fin,
               p.id AS proyecto_id, p.descripcion AS proyecto, p.coste,
               e.id AS empresa_id, e.nombre AS empresa,
               c.codigo_empleado AS consultor_id, c.nombre AS consultor
        FROM venta v
        JOIN proyecto p ON v.proyecto_id = p.id
        JOIN empresa_cliente e ON v.empresa_id = e.id
        JOIN consultor c ON v.consultor_id = c.codigo_empleado
        {filtro}
        ORDER BY v.fecha_inicio DESC, v.id DESC
        """,
        parametros or [],
    )
    ventas = dictfetchall(cursor)
    for v in ventas:
        v['estado'] = _estado_venta(v['fecha_inicio'], v['fecha_fin'])
    return ventas


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

        ventas = _ventas(cursor)

        cursor.execute(
            """
            SELECT p.id, p.descripcion, COUNT(v.id) AS veces_vendido
            FROM proyecto p
            JOIN venta v ON v.proyecto_id = p.id
            GROUP BY p.id, p.descripcion
            ORDER BY veces_vendido DESC, p.id
            LIMIT 5
            """
        )
        proyectos_top = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT e.id, e.nombre, COUNT(v.id) AS contrataciones,
                   COALESCE(SUM(v.precio), 0) AS total
            FROM empresa_cliente e
            JOIN venta v ON v.empresa_id = e.id
            GROUP BY e.id, e.nombre
            ORDER BY contrataciones DESC, e.nombre
            LIMIT 5
            """
        )
        clientes_top = dictfetchall(cursor)

        cursor.execute(
            """
            SELECT cat.id, cat.nombre, COUNT(c.codigo_empleado) AS cantidad
            FROM categoria_profesional cat
            LEFT JOIN consultor c ON c.categoria_id = cat.id
            GROUP BY cat.id, cat.nombre
            ORDER BY cat.id
            """
        )
        por_categoria = dictfetchall(cursor)

    for c in por_categoria:
        c['porcentaje'] = round(100 * c['cantidad'] / total_consultores) if total_consultores else 0

    estados = {'En curso': 0, 'Próximo': 0, 'Finalizado': 0}
    for v in ventas:
        estados[v['estado']] += 1

    datos = {
        'total_consultores': total_consultores,
        'total_empresas': total_empresas,
        'total_proyectos': total_proyectos,
        'total_ventas': len(ventas),
        'en_curso': estados['En curso'],
        'proximas': estados['Próximo'],
        'finalizadas': estados['Finalizado'],
        'ventas_recientes': ventas[:8],
        'proyectos_top': proyectos_top,
        'clientes_top': clientes_top,
        'por_categoria': por_categoria,
    }

    # Los números de dinero solo se calculan y envían si el rol puede verlos.
    if request.session.get('rol') in ROLES_VEN_FINANZAS:
        ingresos = sum((v['precio'] or 0) for v in ventas)
        costes = sum((v['coste'] or 0) for v in ventas)
        datos.update(ingresos=ingresos, costes=costes, margen=ingresos - costes)

    return renderizar(request, 'myapp/inicio.html', datos)


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


# ---------- DETALLES (se abren al hacer clic en cada elemento) ----------

def _primero_o_404(filas, mensaje):
    if not filas:
        raise Http404(mensaje)
    return filas[0]


@login_requerido
def consultor_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.codigo_empleado, c.nombre, c.sueldo,
                   cat.nombre AS categoria_nombre, cat.salario_recomendado,
                   jefe.codigo_empleado AS jefe_id, jefe.nombre AS jefe_nombre
            FROM consultor c
            JOIN categoria_profesional cat ON c.categoria_id = cat.id
            LEFT JOIN consultor jefe ON c.jefe_id = jefe.codigo_empleado
            WHERE c.codigo_empleado = %s
            """,
            [pk],
        )
        consultor = _primero_o_404(dictfetchall(cursor), 'Consultor no encontrado')

        cursor.execute(
            "SELECT codigo_empleado, nombre FROM consultor WHERE jefe_id = %s ORDER BY nombre",
            [pk],
        )
        subordinados = dictfetchall(cursor)

        ventas = _ventas(cursor, 'WHERE v.consultor_id = %s', [pk])

    diferencia = None
    if consultor['sueldo'] is not None and consultor['salario_recomendado'] is not None:
        diferencia = consultor['sueldo'] - consultor['salario_recomendado']

    return renderizar(request, 'myapp/consultor_detalle.html', {
        'consultor': consultor,
        'subordinados': subordinados,
        'ventas': ventas,
        'diferencia': diferencia,
        'diferencia_abs': abs(diferencia) if diferencia is not None else None,
    })


@login_requerido
def empresa_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, nombre, direccion, cif FROM empresa_cliente WHERE id = %s", [pk]
        )
        empresa = _primero_o_404(dictfetchall(cursor), 'Empresa no encontrada')

        cursor.execute("SELECT numero FROM telefono WHERE empresa_id = %s ORDER BY id", [pk])
        telefonos = [fila[0] for fila in cursor.fetchall()]

        ventas = _ventas(cursor, 'WHERE v.empresa_id = %s', [pk])

    datos = {'empresa': empresa, 'telefonos': telefonos, 'ventas': ventas}
    if request.session.get('rol') in ROLES_VEN_FINANZAS:
        datos['total_contratado'] = sum((v['precio'] or 0) for v in ventas)
    return renderizar(request, 'myapp/empresa_detalle.html', datos)


@login_requerido
def proyecto_detalle(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, descripcion, coste FROM proyecto WHERE id = %s", [pk])
        proyecto = _primero_o_404(dictfetchall(cursor), 'Proyecto no encontrado')

        ventas = _ventas(cursor, 'WHERE v.proyecto_id = %s', [pk])

    datos = {'proyecto': proyecto, 'ventas': ventas, 'veces_vendido': len(ventas)}
    if request.session.get('rol') in ROLES_VEN_FINANZAS:
        ingresos = sum((v['precio'] or 0) for v in ventas)
        costes = (proyecto['coste'] or 0) * len(ventas)
        datos.update(ingresos=ingresos, costes=costes, margen=ingresos - costes)
    return renderizar(request, 'myapp/proyecto_detalle.html', datos)


# ---------- EDICIÓN (se abre con el botón "Editar" de cada detalle) ----------

LIMITE_DINERO = Decimal('99999999.99')   # lo que entra en un DECIMAL(10,2)


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _decimal(valor):
    """Devuelve un Decimal entre 0 y LIMITE_DINERO con 2 decimales, o None si no sirve."""
    try:
        numero = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not numero.is_finite() or numero < 0 or numero > LIMITE_DINERO:
        return None
    return numero.quantize(Decimal('0.01'))


def _descendientes(todos, raiz):
    """Ids de todas las personas que dependen (directa o indirectamente) de `raiz`."""
    hijos = {}
    for c in todos:
        hijos.setdefault(c['jefe_id'], []).append(c['codigo_empleado'])
    resultado, pendientes = set(), [raiz]
    while pendientes:
        actual = pendientes.pop()
        for h in hijos.get(actual, []):
            if h not in resultado:
                resultado.add(h)
                pendientes.append(h)
    return resultado


@login_requerido
@permiso_requerido('consultores')
def consultor_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT codigo_empleado, nombre, sueldo, categoria_id, jefe_id "
            "FROM consultor WHERE codigo_empleado = %s",
            [pk],
        )
        consultor = _primero_o_404(dictfetchall(cursor), 'Consultor no encontrado')

        cursor.execute("SELECT id, nombre FROM categoria_profesional ORDER BY id")
        categorias = dictfetchall(cursor)

        cursor.execute("SELECT codigo_empleado, nombre, jefe_id FROM consultor ORDER BY nombre")
        todos = dictfetchall(cursor)

    # Puede depender de cualquiera, menos de sí mismo ni de quienes dependen de él
    # (si no, se armaría un círculo: A es jefe de B y B es jefe de A).
    excluidos = _descendientes(todos, pk) | {pk}
    posibles_jefes = [c for c in todos if c['codigo_empleado'] not in excluidos]

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        sueldo_texto = request.POST.get('sueldo', '')
        sueldo = _decimal(sueldo_texto)
        categoria_id = _entero(request.POST.get('categoria'))
        jefe_id = _entero(request.POST.get('jefe'))

        errores = []
        if not nombre:
            errores.append('El nombre es obligatorio.')
        elif len(nombre) > 100:
            errores.append('El nombre no puede superar los 100 caracteres.')
        if sueldo is None:
            errores.append('El sueldo tiene que ser un número entre 0 y 99.999.999,99.')
        if categoria_id not in {c['id'] for c in categorias}:
            errores.append('Elegí una categoría válida.')
        if jefe_id is not None and jefe_id not in {c['codigo_empleado'] for c in posibles_jefes}:
            errores.append('El jefe elegido no es válido.')

        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE consultor SET nombre = %s, sueldo = %s, categoria_id = %s, jefe_id = %s "
                    "WHERE codigo_empleado = %s",
                    [nombre, sueldo, categoria_id, jefe_id, pk],
                )
            messages.success(request, 'Consultor actualizado correctamente.')
            return redirect('consultor_detalle', pk=pk)

        for e in errores:
            messages.error(request, e)
        # Se vuelve a mostrar el formulario con lo que la persona había escrito.
        consultor.update(nombre=nombre, sueldo=sueldo_texto,
                         categoria_id=categoria_id, jefe_id=jefe_id)

    return renderizar(request, 'myapp/consultor_editar.html', {
        'consultor': consultor,
        'categorias': categorias,
        'posibles_jefes': posibles_jefes,
    })


@login_requerido
@permiso_requerido('empresas')
def empresa_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, nombre, direccion, cif FROM empresa_cliente WHERE id = %s", [pk]
        )
        empresa = _primero_o_404(dictfetchall(cursor), 'Empresa no encontrada')

        cursor.execute("SELECT numero FROM telefono WHERE empresa_id = %s ORDER BY id", [pk])
        telefonos_texto = '\n'.join(fila[0] for fila in cursor.fetchall())

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        cif = request.POST.get('cif', '').strip()
        telefonos_texto = request.POST.get('telefonos', '')
        # Un teléfono por línea, sin vacíos ni repetidos.
        telefonos = list(dict.fromkeys(
            linea.strip() for linea in telefonos_texto.splitlines() if linea.strip()
        ))

        errores = []
        if not nombre:
            errores.append('El nombre es obligatorio.')
        elif len(nombre) > 100:
            errores.append('El nombre no puede superar los 100 caracteres.')
        if len(direccion) > 200:
            errores.append('La dirección no puede superar los 200 caracteres.')
        if not cif:
            errores.append('El CIF es obligatorio.')
        elif len(cif) > 15:
            errores.append('El CIF no puede superar los 15 caracteres.')
        if any(len(t) > 20 for t in telefonos):
            errores.append('Cada teléfono puede tener hasta 20 caracteres.')

        if not errores:
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE empresa_cliente SET nombre = %s, direccion = %s, cif = %s "
                            "WHERE id = %s",
                            [nombre, direccion or None, cif, pk],
                        )
                        cursor.execute("DELETE FROM telefono WHERE empresa_id = %s", [pk])
                        for numero in telefonos:
                            cursor.execute(
                                "INSERT INTO telefono (numero, empresa_id) VALUES (%s, %s)",
                                [numero, pk],
                            )
                messages.success(request, 'Empresa actualizada correctamente.')
                return redirect('empresa_detalle', pk=pk)
            except IntegrityError:
                errores.append('Ya existe otra empresa con ese CIF.')

        for e in errores:
            messages.error(request, e)
        empresa.update(nombre=nombre, direccion=direccion, cif=cif)

    return renderizar(request, 'myapp/empresa_editar.html', {
        'empresa': empresa,
        'telefonos_texto': telefonos_texto,
    })


@login_requerido
@permiso_requerido('proyectos')
def proyecto_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, descripcion, coste FROM proyecto WHERE id = %s", [pk])
        proyecto = _primero_o_404(dictfetchall(cursor), 'Proyecto no encontrado')

    if request.method == 'POST':
        descripcion = request.POST.get('descripcion', '').strip()
        coste_texto = request.POST.get('coste', '')
        coste = _decimal(coste_texto)

        errores = []
        if not descripcion:
            errores.append('La descripción es obligatoria.')
        if coste is None:
            errores.append('El coste tiene que ser un número entre 0 y 99.999.999,99.')

        if not errores:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE proyecto SET descripcion = %s, coste = %s WHERE id = %s",
                    [descripcion, coste, pk],
                )
            messages.success(request, 'Proyecto actualizado correctamente.')
            return redirect('proyecto_detalle', pk=pk)

        for e in errores:
            messages.error(request, e)
        proyecto.update(descripcion=descripcion, coste=coste_texto)

    return renderizar(request, 'myapp/proyecto_editar.html', {'proyecto': proyecto})

# ---------- CAJA (ingresos y egresos de la consultora) ----------

# clave: (nombre que se ve, tipo). El orden es el de los desplegables.
CATEGORIAS_CAJA = {
    'cobro_proyecto': ('Cobro de proyecto', 'ingreso'),
    'cuota':          ('Cobro de cuota', 'ingreso'),
    'aporte_capital': ('Aporte de capital', 'ingreso'),
    'otro_ingreso':   ('Otro ingreso', 'ingreso'),
    'sueldo':         ('Pago de sueldo', 'egreso'),
    'inversion':      ('Inversión', 'egreso'),
    'alquiler':       ('Alquiler y servicios', 'egreso'),
    'impuestos':      ('Impuestos', 'egreso'),
    'otro_gasto':     ('Otro gasto', 'egreso'),
}
LIMITE_CAJA = 200   # cuántos movimientos se listan como máximo


def _categorias_caja(tipo=None):
    return [
        {'clave': clave, 'nombre': nombre}
        for clave, (nombre, t) in CATEGORIAS_CAJA.items()
        if tipo is None or t == tipo
    ]


def _fecha(texto):
    """'2026-11-01' -> date, o None si no sirve."""
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def finanzas_requerido(vista):
    """Solo deja pasar a los roles que pueden ver las finanzas."""
    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        if request.session.get('rol') not in ROLES_VEN_FINANZAS:
            messages.error(request, 'Tu rol no tiene acceso a la caja.')
            return redirect('inicio')
        return vista(request, *args, **kwargs)
    return envoltorio


@login_requerido
@finanzas_requerido
def caja(request):
    if 'caja' not in connection.introspection.table_names():
        return renderizar(request, 'myapp/caja.html', {'falta_tabla': True})

    # --- filtros (solo se guardan los que la persona completó) ---
    filtros, condiciones, parametros = {}, [], []

    desde = _fecha(request.GET.get('desde'))
    if desde:
        filtros['desde'] = desde.isoformat()
        condiciones.append('m.fecha >= %s')
        parametros.append(desde)

    hasta = _fecha(request.GET.get('hasta'))
    if hasta:
        filtros['hasta'] = hasta.isoformat()
        condiciones.append('m.fecha <= %s')
        parametros.append(hasta)

    empresa = _entero(request.GET.get('empresa'))
    if empresa is not None:
        filtros['empresa'] = empresa
        condiciones.append('m.empresa_id = %s')
        parametros.append(empresa)

    consultor = _entero(request.GET.get('consultor'))
    if consultor is not None:
        filtros['consultor'] = consultor
        condiciones.append('m.consultor_id = %s')
        parametros.append(consultor)

    categoria = request.GET.get('categoria')
    if categoria in CATEGORIAS_CAJA:
        filtros['categoria'] = categoria
        condiciones.append('m.categoria = %s')
        parametros.append(categoria)

    donde = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''

    with connection.cursor() as cursor:
        # --- lista de movimientos ---
        cursor.execute(
            f"""
            SELECT m.id, m.fecha, m.categoria, m.tipo, m.monto, m.descripcion,
                   m.cuota_numero, m.cuotas_total,
                   e.id AS empresa_id, e.nombre AS empresa,
                   c.codigo_empleado AS consultor_id, c.nombre AS consultor,
                   p.descripcion AS proyecto
            FROM caja m
            LEFT JOIN empresa_cliente e ON m.empresa_id = e.id
            LEFT JOIN consultor c ON m.consultor_id = c.codigo_empleado
            LEFT JOIN venta v ON m.venta_id = v.id
            LEFT JOIN proyecto p ON v.proyecto_id = p.id
            {donde}
            ORDER BY m.fecha DESC, m.id DESC
            LIMIT %s
            """,
            parametros + [LIMITE_CAJA + 1],
        )
        movimientos = dictfetchall(cursor)

        # --- totales (respetan los filtros, sin límite) ---
        cursor.execute(
            f"""
            SELECT m.categoria, m.tipo, SUM(m.monto) AS total
            FROM caja m
            {donde}
            GROUP BY m.categoria, m.tipo
            """,
            parametros,
        )
        totales = dictfetchall(cursor)

        # --- resumen por empresa (acumulado, sin filtros) ---
        cursor.execute(
            """
            SELECT e.id, e.nombre,
                   (SELECT COALESCE(SUM(v.precio), 0) FROM venta v
                     WHERE v.empresa_id = e.id) AS facturado,
                   (SELECT COALESCE(SUM(m.monto), 0) FROM caja m
                     WHERE m.empresa_id = e.id
                       AND m.categoria IN ('cobro_proyecto', 'cuota')) AS cobrado,
                   (SELECT COALESCE(SUM(m.monto), 0) FROM caja m
                     WHERE m.empresa_id = e.id AND m.tipo = 'egreso') AS gastos
            FROM empresa_cliente e
            ORDER BY e.nombre
            """
        )
        resumen_empresas = dictfetchall(cursor)

        # --- resumen por consultor (acumulado, sin filtros) ---
        cursor.execute(
            """
            SELECT c.codigo_empleado, c.nombre, c.sueldo,
                   (SELECT COALESCE(SUM(m.monto), 0) FROM caja m
                     WHERE m.consultor_id = c.codigo_empleado
                       AND m.categoria = 'sueldo') AS pagado,
                   (SELECT COUNT(*) FROM venta v
                     WHERE v.consultor_id = c.codigo_empleado) AS ventas,
                   (SELECT COALESCE(SUM(v.precio), 0) FROM venta v
                     WHERE v.consultor_id = c.codigo_empleado) AS facturado
            FROM consultor c
            ORDER BY c.nombre
            """
        )
        resumen_consultores = dictfetchall(cursor)

        # --- opciones de los filtros ---
        cursor.execute("SELECT id, nombre FROM empresa_cliente ORDER BY nombre")
        empresas_filtro = dictfetchall(cursor)
        cursor.execute("SELECT codigo_empleado, nombre FROM consultor ORDER BY nombre")
        consultores_filtro = dictfetchall(cursor)

    # Tarjetas de arriba
    cero = Decimal('0')
    ingresos = sum((t['total'] for t in totales if t['tipo'] == 'ingreso'), cero)
    egresos = sum((t['total'] for t in totales if t['tipo'] == 'egreso'), cero)
    por_categoria = {t['categoria']: t['total'] for t in totales}
    inversiones = por_categoria.get('inversion', cero)
    aportes = por_categoria.get('aporte_capital', cero)
    gastos = egresos - inversiones

    resumen = {
        'ingresos': ingresos,
        'gastos': gastos,
        'inversiones': inversiones,
        'saldo': ingresos - egresos,
        'ganancia': (ingresos - aportes) - gastos,
        'cuotas': por_categoria.get('cuota', cero),
    }

    for m in movimientos:
        m['categoria_nombre'] = CATEGORIAS_CAJA.get(m['categoria'], (m['categoria'], ''))[0]
    for e in resumen_empresas:
        e['pendiente'] = e['facturado'] - e['cobrado']
        e['resultado'] = e['cobrado'] - e['gastos']

    return renderizar(request, 'myapp/caja.html', {
        'falta_tabla': False,
        'filtros': filtros,
        'resumen': resumen,
        'movimientos': movimientos[:LIMITE_CAJA],
        'hay_mas': len(movimientos) > LIMITE_CAJA,
        'limite': LIMITE_CAJA,
        'resumen_empresas': resumen_empresas,
        'resumen_consultores': resumen_consultores,
        'empresas_filtro': empresas_filtro,
        'consultores_filtro': consultores_filtro,
        'categorias_filtro': _categorias_caja(),
    })


def _caja_formulario(request, mov, editando, pk=None):
    """Lógica compartida entre 'Nuevo movimiento' y 'Editar movimiento'."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, nombre FROM empresa_cliente ORDER BY nombre")
        empresas_op = dictfetchall(cursor)
        cursor.execute("SELECT codigo_empleado, nombre FROM consultor ORDER BY nombre")
        consultores_op = dictfetchall(cursor)
        ventas_op = _ventas(cursor)

    ventas_por_id = {v['id']: v for v in ventas_op}

    if request.method == 'POST':
        fecha_texto = request.POST.get('fecha', '')
        fecha = _fecha(fecha_texto)
        categoria = request.POST.get('categoria', '')
        monto_texto = request.POST.get('monto', '')
        monto = _decimal(monto_texto)
        descripcion = request.POST.get('descripcion', '').strip()
        empresa_id = _entero(request.POST.get('empresa'))
        consultor_id = _entero(request.POST.get('consultor'))
        venta_id = _entero(request.POST.get('venta'))
        cuota_numero = _entero(request.POST.get('cuota_numero'))
        cuotas_total = _entero(request.POST.get('cuotas_total'))

        errores = []
        if fecha is None:
            errores.append('La fecha no es válida.')
        if categoria not in CATEGORIAS_CAJA:
            errores.append('Elegí una categoría válida.')
        if monto is None or monto <= 0:
            errores.append('El monto tiene que ser mayor que cero (hasta 99.999.999,99).')
        if len(descripcion) > 200:
            errores.append('La descripción no puede superar los 200 caracteres.')

        if venta_id is not None:
            if venta_id in ventas_por_id:
                # Si eligió una contratación, la empresa sale de ahí.
                empresa_id = ventas_por_id[venta_id]['empresa_id']
            else:
                errores.append('La contratación elegida no es válida.')
        if empresa_id is not None and empresa_id not in {e['id'] for e in empresas_op}:
            errores.append('La empresa elegida no es válida.')
        if consultor_id is not None and consultor_id not in {c['codigo_empleado'] for c in consultores_op}:
            errores.append('El consultor elegido no es válido.')

        if categoria in ('cobro_proyecto', 'cuota') and empresa_id is None:
            errores.append('Un cobro necesita una empresa (o una contratación).')
        if categoria == 'sueldo' and consultor_id is None:
            errores.append('El pago de sueldo necesita un consultor.')

        if categoria == 'cuota':
            if (cuota_numero is None or cuotas_total is None
                    or not (1 <= cuota_numero <= cuotas_total <= 360)):
                errores.append('Completá el número de cuota y el total (el número no puede pasar al total).')
        else:
            cuota_numero = cuotas_total = None

        if not errores:
            valores = [
                fecha, categoria, CATEGORIAS_CAJA[categoria][1], monto, descripcion or None,
                empresa_id, consultor_id, venta_id, cuota_numero, cuotas_total,
            ]
            with connection.cursor() as cursor:
                if editando:
                    cursor.execute(
                        """
                        UPDATE caja SET fecha = %s, categoria = %s, tipo = %s, monto = %s,
                               descripcion = %s, empresa_id = %s, consultor_id = %s,
                               venta_id = %s, cuota_numero = %s, cuotas_total = %s
                        WHERE id = %s
                        """,
                        valores + [pk],
                    )
                    messages.success(request, 'Movimiento actualizado correctamente.')
                else:
                    cursor.execute(
                        """
                        INSERT INTO caja (fecha, categoria, tipo, monto, descripcion,
                                          empresa_id, consultor_id, venta_id,
                                          cuota_numero, cuotas_total)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        valores,
                    )
                    messages.success(request, 'Movimiento registrado correctamente.')
            return redirect('caja')

        for e in errores:
            messages.error(request, e)
        # Se vuelve a mostrar el formulario con lo que la persona había escrito.
        mov = {
            'fecha': fecha_texto, 'categoria': categoria, 'monto_texto': monto_texto,
            'descripcion': descripcion, 'empresa_id': empresa_id,
            'consultor_id': consultor_id, 'venta_id': venta_id,
            'cuota_numero': cuota_numero, 'cuotas_total': cuotas_total,
        }

    return renderizar(request, 'myapp/caja_form.html', {
        'titulo': 'Editar movimiento' if editando else 'Nuevo movimiento',
        'editando': editando,
        'mov': mov,
        'categorias_ingreso': _categorias_caja('ingreso'),
        'categorias_egreso': _categorias_caja('egreso'),
        'empresas_op': empresas_op,
        'consultores_op': consultores_op,
        'ventas_op': ventas_op,
    })


@login_requerido
@finanzas_requerido
def caja_nuevo(request):
    # Los botones "Movimientos" de la caja pasan ?empresa= o ?consultor=
    empresa_id = _entero(request.GET.get('empresa'))
    consultor_id = _entero(request.GET.get('consultor'))
    categoria = ''
    if consultor_id is not None:
        categoria = 'sueldo'
    elif empresa_id is not None:
        categoria = 'cobro_proyecto'

    mov = {
        'fecha': date.today().isoformat(), 'categoria': categoria, 'monto_texto': '',
        'descripcion': '', 'empresa_id': empresa_id, 'consultor_id': consultor_id,
        'venta_id': None, 'cuota_numero': None, 'cuotas_total': None,
    }
    return _caja_formulario(request, mov, editando=False)


@login_requerido
@finanzas_requerido
def caja_editar(request, pk):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, fecha, categoria, monto, descripcion, empresa_id,
                   consultor_id, venta_id, cuota_numero, cuotas_total
            FROM caja WHERE id = %s
            """,
            [pk],
        )
        fila = _primero_o_404(dictfetchall(cursor), 'Movimiento no encontrado')

    mov = dict(fila, fecha=fila['fecha'].isoformat(), monto_texto=str(fila['monto']))
    mov['descripcion'] = fila['descripcion'] or ''
    return _caja_formulario(request, mov, editando=True, pk=pk)


@login_requerido
@finanzas_requerido
def caja_eliminar(request, pk):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM caja WHERE id = %s", [pk])
        messages.success(request, 'Movimiento eliminado.')
    return redirect('caja')
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