"""
Datos de los fundadores que aparecen en "¿Quiénes somos?".
Para cambiar cualquier texto editá ESTE archivo; no hace falta tocar nada más.

FOTOS: guardá una imagen por persona en
    myapp/static/myapp/img/fundadores/
con el mismo nombre que el 'slug' de abajo: pablo.jpg, misael.jpg y david.jpg
(sirven .jpg, .jpeg, .png y .webp). Conviene una foto cuadrada de unos 600x600 px.
Mientras no haya foto, el círculo muestra la inicial del nombre.

Los textos de abajo son GENÉRICOS: reemplazalos por la biografía y los proyectos reales.
"""

FUNDADORES = [
    {
        'slug': 'pablo',
        'nombre': 'Pablo Calapeña',
        'titulo': 'Ingeniero en Sistemas y Computación · Cofundador',
        'bio_corta': (
            'Ingeniero y cofundador de la consultora. Participa en el diseño y la '
            'dirección de los proyectos que desarrollamos para nuestros clientes.'
        ),
        'bio_larga': [
            'Pablo es ingeniero y uno de los tres fundadores de la consultora, junto a Misael y David.',
            'Trabaja en el diseño y la dirección de proyectos informáticos a medida para empresas clientes.',
        ],
        'email': '',      # ej: 'pabloConsultora@gmail.com'  
        'linkedin': '',   # ej: 'https://www.linkedin.com/in/usuario'
        'github': '',     # ej: 'https://github.com/usuario'
        'proyectos': [
            {'titulo': 'Proyecto de ejemplo 1',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con un proyecto real de Pablo.',
             'enlace': ''},   # si ponés una URL, aparece el botón "Ver proyecto"
            {'titulo': 'Proyecto de ejemplo 2',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con otro proyecto real de Pablo.',
             'enlace': ''},
        ],
    },
    {
        'slug': 'misael',
        'nombre': 'Misael Zanneti',
        'titulo': 'Ingeniero en Informática · Cofundador',
        'bio_corta': (
            'Ingeniero y cofundador de la consultora. Trabaja con cada empresa cliente '
            'para convertir sus necesidades en soluciones informáticas a medida.'
        ),
        'bio_larga': [
            'Misael es ingeniero y uno de los tres fundadores de la consultora, junto a Pablo y David.',
            'Trabaja con las empresas clientes para entender qué necesitan y llevarlo a soluciones informáticas a medida.',
        ],
        'email': '',
        'linkedin': '',
        'github': '',
        'proyectos': [
            {'titulo': 'Proyecto de ejemplo 1',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con un proyecto real de Misael.',
             'enlace': ''},
            {'titulo': 'Proyecto de ejemplo 2',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con otro proyecto real de Misael.',
             'enlace': ''},
        ],
    },
    {
        'slug': 'david',
        'nombre': 'David Rogelio',
        'titulo': 'Ingeniero en Informática y Licenciado en manejo de IA · Fundador',
        'bio_corta': (
            'Ingeniero y cofundador de la consultora. Acompaña el desarrollo de cada '
            'proyecto, desde la idea inicial hasta la entrega.'
        ),
        'bio_larga': [
            'David es ingeniero y uno de los tres fundadores de la consultora, junto a Pablo y Misael.',
            'Acompaña cada proyecto durante todo su desarrollo, desde la idea inicial hasta la entrega al cliente.',
        ],
        'email': '',
        'linkedin': '',
        'github': '',
        'proyectos': [
            {'titulo': 'Proyecto de ejemplo 1',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con un proyecto real de David.',
             'enlace': ''},
            {'titulo': 'Proyecto de ejemplo 2',
             'descripcion': 'Reemplazá este texto desde myapp/fundadores.py con otro proyecto real de David.',
             'enlace': ''},
        ],
    },
]