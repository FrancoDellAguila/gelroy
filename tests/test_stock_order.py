# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, Form
from odoo.exceptions import UserError, ValidationError
from odoo import fields  # CORRECCIÓN: Agregar import de fields
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class TestStockOrder(TransactionCase):

    def setUp(self):
        """Configuración inicial para las pruebas de pedidos de stock."""
        super(TestStockOrder, self).setUp()
        # Modelos necesarios
        self.Partner = self.env['res.partner']
        self.Franchise = self.env['gelroy.franchise']
        self.StockOrder = self.env['gelroy.stock.order']
        self.StockOrderLine = self.env['gelroy.stock.order.line']
        self.Product = self.env['product.product']
        self.AccountMove = self.env['account.move']
        self.Currency = self.env.ref('base.EUR')
        self.UoM = self.env.ref('uom.product_uom_unit')

        # Crear datos de prueba comunes
        self.franchisee_partner_so = self.Partner.create({'name': 'Franquiciado Prueba SO'})
        self.test_franchise_so = self.Franchise.create({
            'name': 'Franquicia para Pruebas de Pedidos Stock',
            'franchise_code': 'FSO001',
            'franchisee_id': self.franchisee_partner_so.id,
            'currency_id': self.Currency.id,
            'franchise_type': 'restaurant',
        })

        # Crear productos de prueba SIN IMPUESTOS
        self.product_a = self.Product.create({
            'name': 'Producto A para SO',
            'detailed_type': 'product', # Producto almacenable
            'list_price': 10.0,
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'min_franchise_qty': 1,
            'taxes_id': [(5, 0, 0)], 
        })
        self.product_b = self.Product.create({
            'name': 'Producto B para SO',
            'detailed_type': 'product',
            'list_price': 25.0,
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'min_franchise_qty': 1,
            'taxes_id': [(5, 0, 0)], 
        })

        # Inicializar stock para pruebas de deducción
        self.env['stock.quant']._update_available_quantity(self.product_a, self.env.ref('stock.stock_location_stock'), 100)
        self.env['stock.quant']._update_available_quantity(self.product_b, self.env.ref('stock.stock_location_stock'), 50)

        # Datos válidos con fechas futuras
        self.order_data_valid = {
            'franchise_id': self.test_franchise_so.id,
            'order_date': date(2025, 6, 10),
            'requested_delivery_date': date(2025, 6, 20),
            'order_line_ids': [
                (0, 0, {'product_id': self.product_a.id, 'quantity': 5}), # 5 * 10 = 50
                (0, 0, {'product_id': self.product_b.id, 'quantity': 2}), # 2 * 25 = 50
            ] # Total: 100 (sin impuestos)
        }

    def test_01_create_stock_order_and_computes(self):
        """Prueba la creación básica, generación de nombre y cálculo de totales."""
        order = self.StockOrder.create(self.order_data_valid)
        self.assertTrue(order.id, "El pedido de stock debe crearse correctamente.")
        self.assertTrue(order.name.startswith(f"Order-{self.test_franchise_so.franchise_code}-"), "El formato del nombre del pedido es incorrecto.")
        self.assertEqual(order.state, 'draft', "El estado inicial debe ser borrador.")
        
        self.assertEqual(order.total_items, 2, "El total de artículos (líneas) debe ser 2.")
        self.assertTrue(order.total_amount > 0, "El monto total debe ser mayor a 0.")
        self.assertTrue(order.amount_untaxed > 0, "El monto sin impuestos debe ser mayor a 0.")
        self.assertAlmostEqual(order.outstanding_amount, order.total_amount, places=2)
        self.assertIsNotNone(order.delivery_address)

    def test_02_workflow_submit_approve_transit_deliver_pay(self):
        """Prueba el flujo completo de un pedido de stock."""
        order = self.StockOrder.create(self.order_data_valid)

        # Enviar pedido
        order.action_submit()
        self.assertEqual(order.state, 'submitted')

        # Aprobar pedido
        order.action_approve()
        self.assertEqual(order.state, 'approved')
        self.assertEqual(order.approved_by, self.env.user)
        self.assertEqual(order.approved_date, fields.Date.today())

        #verificar que transición funciona
        order.action_start_transit()
        self.assertEqual(order.state, 'in_transit')
        self.assertEqual(order.shipped_date, fields.Date.today())

        # Entregar pedido
        order.action_deliver()
        self.assertEqual(order.state, 'delivered')
        self.assertEqual(order.delivered_date, fields.Date.today())

        # Marcar como pagado
        order.action_mark_paid()
        self.assertEqual(order.state, 'paid')
        self.assertEqual(order.payment_date, fields.Date.today())
        self.assertAlmostEqual(order.outstanding_amount, 0.00, places=2)


    def test_03_validation_constraints_stock_order(self):
        """Prueba las restricciones de validación en StockOrder."""
        with self.assertRaises(ValidationError, msg="La fecha de entrega solicitada no puede ser anterior a la fecha del pedido."):
            self.StockOrder.create({
                'franchise_id': self.test_franchise_so.id,
                'order_date': date(2025, 7, 10),
                'requested_delivery_date': date(2025, 7, 1), # Inválida
            })

    def test_04_submit_order_validations(self):
        """Prueba las validaciones en action_submit."""
        # Sin líneas de pedido
        order_no_lines = self.StockOrder.create({
            'franchise_id': self.test_franchise_so.id,
            'order_date': date(2025, 8, 1)
        })
        with self.assertRaises(UserError, msg="No se puede enviar un pedido sin líneas de producto."):
            order_no_lines.action_submit()

        # Sin fecha de entrega solicitada
        order_no_req_date = self.StockOrder.create({
            'franchise_id': self.test_franchise_so.id,
            'order_date': date(2025, 8, 1),
            'order_line_ids': [(0, 0, {'product_id': self.product_a.id, 'quantity': 1})]
        })
        with self.assertRaises(UserError, msg="Debe especificar una fecha de entrega solicitada."):
            order_no_req_date.action_submit()

    def test_05_approve_order_insufficient_stock(self):
        """Prueba action_approve con stock insuficiente."""
        order_insufficient_stock = self.StockOrder.create({
            'franchise_id': self.test_franchise_so.id,
            'order_date': date(2025, 9, 1),
            'requested_delivery_date': date(2025, 9, 10),
            'state': 'submitted',
            'order_line_ids': [(0, 0, {'product_id': self.product_a.id, 'quantity': 200})]
        })
        with self.assertRaisesRegex(UserError, "Insufficient stock"):
            order_insufficient_stock.action_approve()

    def test_06_basic_workflow_states(self):
        """Test simplificado que solo verifica transiciones básicas."""
        order = self.StockOrder.create(self.order_data_valid)
        
        # Verificar que se puede enviar
        order.action_submit()
        self.assertEqual(order.state, 'submitted')
        
        # Verificar que se puede aprobar
        order.action_approve()
        self.assertEqual(order.state, 'approved')

    def test_07_state_transitions_only(self):
        """Test que solo verifica transiciones de estado sin campos computed."""
        order = self.StockOrder.create(self.order_data_valid)
        
        # Solo verificar transiciones básicas
        self.assertEqual(order.state, 'draft')
        
        order.action_submit()
        self.assertEqual(order.state, 'submitted')
        
        order.action_approve()
        self.assertEqual(order.state, 'approved')
        
        order.action_start_transit()
        self.assertEqual(order.state, 'in_transit')
        
        order.action_deliver()
        self.assertEqual(order.state, 'delivered')
        
        order.action_mark_paid()
        self.assertEqual(order.state, 'paid')

    def test_08_unlink_basic(self):
        """Test básico de eliminación sin facturas complejas."""
        order = self.StockOrder.create(self.order_data_valid)
        order_id = order.id
        
        # Debería poder eliminar en estado draft
        order.unlink()
        self.assertFalse(self.StockOrder.search([('id', '=', order_id)]))