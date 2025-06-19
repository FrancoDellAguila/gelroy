# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from datetime import date
from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

class TestFranchiseModel(TransactionCase):

    def setUp(self):
        super(TestFranchiseModel, self).setUp()
        # Referencias a modelos
        self.Partner = self.env['res.partner']
        self.Franchise = self.env['gelroy.franchise']
        self.RoyaltyPayment = self.env['gelroy.royalty.payment']
        self.StockOrder = self.env['gelroy.stock.order']
        self.Currency = self.env.ref('base.EUR')  # Usar una moneda existente

        # Crear datos base para las pruebas
        self.franchisee_partner = self.Partner.create({'name': 'Socio Franquiciado de Prueba'})

        self.franchise_data_valid = {
            'name': 'Franquicia de Prueba Uno',
            'franchise_code': 'TF001',
            'franchise_type': 'restaurant',
            'currency_id': self.Currency.id,
            'franchisee_id': self.franchisee_partner.id,
            'royalty_fee_percentage': 5.0,
            'contract_start_date': date(2023, 1, 1),
            'contract_end_date': date(2023, 12, 31),
        }

    def test_01_create_franchise_basic(self):
        """Prueba la creación básica de un registro de franquicia."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        self.assertTrue(franchise.id, "La franquicia debe crearse con un ID.")
        self.assertEqual(franchise.name, 'Franquicia de Prueba Uno')
        self.assertEqual(franchise.franchise_code, 'TF001')
        self.assertEqual(franchise.currency_id, self.Currency)
        self.assertTrue(franchise.active, "La franquicia debe estar activa por defecto.")

    def test_02_compute_contract_duration(self):
        """Prueba el método _compute_contract_duration."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        # fecha_fin_contrato (2023, 12, 31) - fecha_inicio_contrato (2023, 1, 1) = 11 meses completos
        # Para 2023-01-01 a 2023-12-31, delta.years = 0, delta.months = 11
        self.assertEqual(franchise.contract_duration_months, 11, "La duración del contrato debe ser 11 meses.")

        # Caso: Sin fecha de fin
        franchise.write({'contract_end_date': False})
        self.assertEqual(franchise.contract_duration_months, 0, "La duración debe ser 0 si falta la fecha de fin.")

        # Caso: Fecha de fin anterior al inicio
        franchise.write({
            'contract_start_date': date(2024, 1, 1),
            'contract_end_date': date(2023, 12, 31)
        })
        self.assertEqual(franchise.contract_duration_months, 0, "La duración debe ser 0 si la fecha de fin es anterior al inicio.")

        # Caso: Duración mayor a un año
        franchise.write({
            'contract_start_date': date(2023, 1, 1),
            'contract_end_date': date(2025, 6, 30) # 2 años y 5 meses = 29 meses
        })
        self.assertEqual(franchise.contract_duration_months, 29, "La duración del contrato debe ser 29 meses para 2.5 años.")

    def test_03_compute_royalty_payment_count(self):
        """Prueba el método _compute_royalty_payment_count."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        self.assertEqual(franchise.royalty_payment_count, 0, "El contador inicial de pagos de regalías debe ser 0.")

        self.RoyaltyPayment.create({
            'franchise_id': franchise.id,
            'period_start_date': date(2023, 1, 1),
            'period_end_date': date(2023, 1, 31),
            'calculation_date': date(2023, 2, 1),
            'period_revenue': 1000,
        })
        franchise.invalidate_recordset(fnames=['royalty_payment_count']) # Forzar recálculo del compute
        self.assertEqual(franchise.royalty_payment_count, 1, "El contador de pagos de regalías debe ser 1.")

        self.RoyaltyPayment.create({
            'franchise_id': franchise.id,
            'period_start_date': date(2023, 2, 1),
            'period_end_date': date(2023, 2, 28),
            'calculation_date': date(2023, 3, 1),
            'period_revenue': 1200,
        })
        franchise.invalidate_recordset(fnames=['royalty_payment_count'])
        self.assertEqual(franchise.royalty_payment_count, 2, "El contador de pagos de regalías debe ser 2.")

    def test_04_compute_stock_order_count(self):
        """Prueba el método _compute_stock_order_count."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        self.assertEqual(franchise.stock_order_count, 0, "El contador inicial de pedidos de stock debe ser 0.")

        # Creamos un producto para las líneas de pedido
        product_a = self.env['product.product'].create({'name': 'Producto de Prueba A', 'detailed_type': 'product'})
        self.StockOrder.create({
            'franchise_id': franchise.id,
            'order_date': date(2023, 1, 15),
            'order_line_ids': [(0, 0, {'product_id': product_a.id, 'quantity': 10})]
        })
        franchise.invalidate_recordset(fnames=['stock_order_count'])
        self.assertEqual(franchise.stock_order_count, 1, "El contador de pedidos de stock debe ser 1.")

    def test_05_franchise_code_unique_constraint(self):
        """Prueba la restricción de unicidad en franchise_code."""
        self.Franchise.create({
            'name': 'Primera Franquicia con TF001',
            'franchise_code': 'TF001',
            'franchisee_id': self.franchisee_partner.id,
            'franchise_type': 'restaurant',
            'currency_id': self.Currency.id,
        })
        with self.assertRaises(IntegrityError, msg="No debe permitir códigos de franquicia duplicados"):
            # Intentar crear otra con el mismo código
            self.Franchise.create({
                'name': 'Segunda Franquicia de Prueba',
                'franchise_code': 'TF001', # Mismo código
                'franchisee_id': self.franchisee_partner.id,
                'franchise_type': 'restaurant',
                'currency_id': self.Currency.id,
            })

    def test_06_compute_financial_summary_no_transactions(self):
        """Prueba los campos de resumen financiero cuando no hay transacciones."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        franchise._compute_financial_summary() # Forzar cálculo si no se disparó por depends

        self.assertAlmostEqual(franchise.total_royalties_due, 0.0, places=2)
        self.assertAlmostEqual(franchise.total_royalties_paid, 0.0, places=2)
        self.assertAlmostEqual(franchise.outstanding_royalties, 0.0, places=2)
        self.assertAlmostEqual(franchise.outstanding_stock_orders, 0.0, places=2)
        self.assertAlmostEqual(franchise.total_outstanding_debt, 0.0, places=2)
        self.assertEqual(franchise.pending_royalty_payments, 0)
        self.assertEqual(franchise.pending_stock_orders_count, 0)

    def test_07_compute_financial_summary_with_transactions(self):
        """Prueba el resumen financiero con algunos pagos de regalías y pedidos de stock."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        product_b = self.env['product.product'].create({'name': 'Producto de Prueba B', 'detailed_type': 'product', 'list_price': 10})

        # Crear pagos de regalías
        self.RoyaltyPayment.create({
            'franchise_id': franchise.id, 'period_revenue': 1000, 'royalty_rate': 5,
            'calculated_amount': 50, 'state': 'confirmed',
            'period_start_date': date(2023, 1, 1), 'period_end_date': date(2023, 1, 31),
            'calculation_date': date(2023, 2, 1)
        })
        self.RoyaltyPayment.create({
            'franchise_id': franchise.id, 'period_revenue': 2000, 'royalty_rate': 5,
            'calculated_amount': 100, 'state': 'paid', 'paid_amount': 100,
            'period_start_date': date(2023, 2, 1), 'period_end_date': date(2023, 2, 28),
            'calculation_date': date(2023, 3, 1)
        })

        # Crear pedido de stock entregado, no pagado
        so1 = self.StockOrder.create({
            'franchise_id': franchise.id,
            'order_date': date(2023, 1, 10),
            'order_line_ids': [(0, 0, {'product_id': product_b.id, 'quantity': 5, 'unit_price': 10})]
        })
        # Cambiar estado usando SQL directo para evitar validaciones
        self.env.cr.execute("UPDATE gelroy_stock_order SET state = 'delivered' WHERE id = %s", (so1.id,))

        # Crear pedido de stock pagado
        so2 = self.StockOrder.create({
            'franchise_id': franchise.id,
            'order_date': date(2023, 2, 10),
            'order_line_ids': [(0, 0, {'product_id': product_b.id, 'quantity': 3, 'unit_price': 10})]
        })
        # Cambiar estado usando SQL directo para evitar validaciones
        self.env.cr.execute("UPDATE gelroy_stock_order SET state = 'paid' WHERE id = %s", (so2.id,))

        # Invalidar caché para refrescar los registros
        so1.invalidate_recordset()
        so2.invalidate_recordset()

        # Forzar recálculo usando invalidate_recordset
        franchise.invalidate_recordset(['total_royalties_due', 'total_royalties_paid', 'outstanding_royalties',
                                       'outstanding_stock_orders', 'total_outstanding_debt'])

        # Verificar los valores calculados
        self.assertAlmostEqual(franchise.total_royalties_paid, 100.00, places=2, msg="Total de regalías pagadas incorrecto") 
        self.assertAlmostEqual(franchise.outstanding_royalties, 50.00, places=2, msg="Regalías pendientes incorrectas")
        self.assertAlmostEqual(franchise.outstanding_stock_orders, 57.50, places=2, msg="Pedidos de stock pendientes incorrectos")
        self.assertAlmostEqual(franchise.total_outstanding_debt, 107.50, places=2, msg="Deuda total pendiente incorrecta")

    def test_08_action_view_royalty_payments(self):
        """Prueba la acción para ver los pagos de regalías."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        action = franchise.action_view_royalty_payments()
        self.assertIsNotNone(action)
        self.assertEqual(action.get('res_model'), 'gelroy.royalty.payment')
        self.assertEqual(action.get('domain'), [('franchise_id', '=', franchise.id)])

    def test_09_action_view_stock_orders(self):
        """Prueba la acción para ver los pedidos de stock."""
        franchise = self.Franchise.create(self.franchise_data_valid)
        action = franchise.action_view_stock_orders()
        self.assertIsNotNone(action)
        self.assertEqual(action.get('res_model'), 'gelroy.stock.order')
        self.assertEqual(action.get('domain'), [('franchise_id', '=', franchise.id)])
