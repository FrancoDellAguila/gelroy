
{
    'name': "Franchise Manager",

    'summary': "Plataforma diseñada para automatizar y optimizar los procesos administrativos relacionados con la gestión de franquicias",

    'description': """
Herramienta digital que centraliza y automatiza la administración de franquicias. Diseñada para franquiciantes y franquiciados, la app optimiza tareas como la gestión de contratos, el cálculo de regalías, la facturación y el monitoreo de indicadores clave de desempeño (KPIs). Su diseño intuitivo y modular permite personalizar funciones según las necesidades específicas del usuario, asegurando una experiencia eficiente y escalable.
    """,

    'author': "Franco Dell Aguila Ureña",
    'website': "https://www.linkedin.com/in/franco-dell-aguila/",
    'category': 'Franchising',
    'version': '17.0.1.0.0',
    'depends': ['base'],
    'data': [
        'security/franchise_security.xml',
        'security/ir.model.access.csv',
        'views/templates.xml',
    ],
    'assets': {
    'web.assets_backend': [
        'web/static/src/xml/**/*',
    ],
           },
     'demo': ['demo/demo.xml'],
}
