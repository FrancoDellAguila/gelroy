# -*- coding: utf-8 -*-
# from odoo import http


# class Franquicias(http.Controller):
#     @http.route('/franquicias/franquicias', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/franquicias/franquicias/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('franquicias.listing', {
#             'root': '/franquicias/franquicias',
#             'objects': http.request.env['franquicias.franquicias'].search([]),
#         })

#     @http.route('/franquicias/franquicias/objects/<model("franquicias.franquicias"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('franquicias.object', {
#             'object': obj
#         })

