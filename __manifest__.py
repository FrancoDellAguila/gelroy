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
    'license': 'LGPL-3',
    'depends': [
        'base', 
        'mail', 
        'account',
        'sale',
        'product',
        'stock',
        'board',
    ],
    'data': [
        'security/franchise_security.xml',
        'security/ir.model.access.csv',
        'views/franchise_views.xml', 
        'views/royalty_payment_views.xml',
        'views/stock_order_views.xml', 
        'views/product_views.xml',
        'views/recipe_views.xml',
        'views/production_views.xml',
        'views/franchise_dashboard_views.xml',
        'views/menu_views.xml',        
    ],
    'assets': {
        'web.assets_backend': [
            'web/static/src/xml/**/*',
        ],
    },
    'demo': ['demo/demo.xml'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
