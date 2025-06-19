# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from odoo import fields
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class TestRoyaltyPayment(TransactionCase):

    def setUp(self):
        super(TestRoyaltyPayment, self).setUp()
        # Modelos
        self.Partner = self.env['res.partner']
        self.Franchise = self.env['gelroy.franchise']
        self.RoyaltyPayment = self.env['gelroy.royalty.payment']
        self.AccountMove = self.env['account.move']
        
        self.Currency = self.env.ref('base.EUR')
        self.Currency.active = True

        # Datos Comunes
        self.franchisee_partner = self.Partner.create({'name': 'Franquiciado de Prueba RP'})
        self.test_franchise = self.Franchise.create({
            'name': 'Franquicia para Pruebas de Regalías',
            'franchise_code': 'FRT001',
            'franchisee_id': self.franchisee_partner.id,
            'royalty_fee_percentage': 10.0,
            'currency_id': self.Currency.id,
            'royalty_payment_terms': 15, # Días para pagar
            'franchise_type': 'restaurant',
        })

        # Datos para un pago típico con fechas futuras para evitar overdue automático
        self.payment_data_valid = {
            'franchise_id': self.test_franchise.id,
            'period_start_date': date(2025, 6, 1),  # Mes futuro
            'period_end_date': date(2025, 6, 30),   # Mes futuro
            'calculation_date': date(2025, 7, 1),
            'period_revenue': 1000.00,
        }

    def test_01_create_royalty_payment_and_computes(self):
        """Prueba la creación, cálculo de nombre, monto y fecha de vencimiento."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)

        self.assertTrue(payment.id, "El pago de regalías debe crearse correctamente.")
        self.assertEqual(payment.name, f"ROY-{self.test_franchise.franchise_code}-2025-06", "El nombre de referencia del pago es incorrecto.")
        self.assertEqual(payment.royalty_rate, 10.0, "La tasa de regalías debe heredarse de la franquicia.")
        self.assertAlmostEqual(payment.calculated_amount, 100.00, places=2, msg="El monto calculado es incorrecto.")
        self.assertAlmostEqual(payment.outstanding_amount, 100.00, places=2, msg="El monto pendiente inicial debe igualar al monto calculado.")
        
        expected_due_date = payment.period_end_date + timedelta(days=self.test_franchise.royalty_payment_terms)
        self.assertEqual(payment.payment_due_date, expected_due_date, "El cálculo de la fecha de vencimiento es incorrecto.")
        self.assertEqual(payment.state, 'draft', "El estado inicial debe ser borrador.")
        self.assertEqual(payment.days_overdue, 0, "Los días vencidos deben ser 0 para pago no vencido.")

    def test_02_workflow_calculate_confirm_register_payment(self):
        """Prueba el flujo de estados: borrador -> calculado -> confirmado -> pagado."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)

        # Calcular
        payment.action_calculate()
        self.assertEqual(payment.state, 'calculated', "El estado debe ser 'calculado'.")

        # Confirmar
        payment.action_confirm()
        self.assertEqual(payment.state, 'confirmed', "El estado debe ser 'confirmado'.")

        # Registrar Pago
        payment.action_register_payment()
        self.assertEqual(payment.state, 'paid', "El estado debe ser 'pagado'.")
        self.assertAlmostEqual(payment.paid_amount, payment.calculated_amount, places=2)
        self.assertAlmostEqual(payment.outstanding_amount, 0.00, places=2)
        self.assertEqual(payment.payment_date, fields.Date.today())

    def test_03_workflow_overdue_and_pay_overdue(self):
        """Prueba la transición de estado a vencido y luego pagar un pago vencido."""
        # Crear fechas que garanticen que el pago esté vencido
        past_due_date = fields.Date.today() - timedelta(days=10)
        past_period_end = past_due_date - timedelta(days=self.test_franchise.royalty_payment_terms)
        past_period_start = past_period_end.replace(day=1)

        payment = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': past_period_start,
            'period_end_date': past_period_end,
            'calculation_date': past_period_end + timedelta(days=1),
            'period_revenue': 500.00,
        })
        
        # Calcular y confirmar el pago
        payment.action_calculate()
        payment.action_confirm()
        
        # Ejecutar el cron para marcar como vencido
        self.RoyaltyPayment.check_overdue_payments()
        
        # Refrescar el registro
        payment.invalidate_recordset()
        
        self.assertEqual(payment.state, 'overdue', "El pago debe marcarse como 'vencido'.")
        self.assertTrue(payment.days_overdue > 0, "Los días vencidos deben ser mayores a 0.")
        expected_days_overdue = (fields.Date.today() - past_due_date).days
        self.assertEqual(payment.days_overdue, expected_days_overdue)

        # Registrar pago para vencido
        payment.action_register_payment()
        self.assertEqual(payment.state, 'paid', "El pago vencido debe transicionar a 'pagado'.")
        self.assertAlmostEqual(payment.outstanding_amount, 0.00, places=2)


    def test_04_validation_constraints(self):
        """Prueba varias restricciones de validación."""
        # Fecha de fin de período antes de la fecha de inicio
        with self.assertRaises(ValidationError, msg="La fecha de fin de período debe ser posterior a la fecha de inicio."):
            self.RoyaltyPayment.create({
                'franchise_id': self.test_franchise.id,
                'period_start_date': date(2025, 7, 1),
                'period_end_date': date(2025, 6, 30), # Inválido
                'calculation_date': date(2025, 8, 1),
                'period_revenue': 100.00,
            })

        # Ingresos de período negativos
        with self.assertRaises(ValidationError, msg="Los ingresos del período no pueden ser negativos."):
            self.RoyaltyPayment.create({
                'franchise_id': self.test_franchise.id,
                'period_start_date': date(2025, 8, 1),
                'period_end_date': date(2025, 8, 31),
                'calculation_date': date(2025, 9, 1),
                'period_revenue': -100.00, # Inválido
            })

        # Pago duplicado para la misma franquicia y mes
        self.RoyaltyPayment.create(self.payment_data_valid) # Crea para 2025-06
        with self.assertRaises(ValidationError, msg="No debe permitir pago duplicado para el mismo mes/franquicia."):
            self.RoyaltyPayment.create({
                'franchise_id': self.test_franchise.id,
                'period_start_date': date(2025, 6, 10), # Inicio diferente
                'period_end_date': date(2025, 6, 25),   # Mismo mes de fin
                'calculation_date': date(2025, 7, 1),
                'period_revenue': 200.00,
            })

    def test_05_action_calculate_no_revenue(self):
        """Prueba action_calculate cuando period_revenue no está establecido."""
        payment_no_revenue_data = self.payment_data_valid.copy()
        payment_no_revenue_data['period_revenue'] = 0.0  # Usar 0 en lugar de eliminar el campo
        payment = self.RoyaltyPayment.create(payment_no_revenue_data)
        with self.assertRaises(UserError, msg="Debe lanzar UserError si period_revenue falta o es 0."):
            payment.action_calculate()

    def test_06_action_confirm_wrong_state(self):
        """Prueba action_confirm desde un estado diferente a 'calculated'."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid) # el estado es 'draft'
        with self.assertRaises(UserError, msg="Debe lanzar UserError si se confirma desde un estado no calculado."):
            payment.action_confirm()

    def test_07_action_register_payment_wrong_state(self):
        """Prueba action_register_payment desde un estado diferente a 'confirmed' o 'overdue'."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid) # el estado es 'draft'
        with self.assertRaises(UserError, msg="Debe lanzar UserError si se registra pago desde estado borrador."):
            payment.action_register_payment()

        payment.action_calculate() # estado es 'calculated'
        payment.action_confirm() # estado es 'confirmed'
        payment.action_register_payment() # estado es 'paid'
        with self.assertRaises(UserError, msg="Debe lanzar UserError si se re-registra un pago pagado."):
            payment.action_register_payment()

    def test_08_action_cancel_and_reset(self):
        """Prueba cancelar un pago y reiniciarlo a borrador."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        payment.action_calculate()
        payment.action_confirm()

        payment.action_cancel()
        self.assertEqual(payment.state, 'cancelled', "El pago debe estar 'cancelado'.")

        # No se puede cancelar un pago pagado
        payment_paid = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': date(2025, 9, 1), 'period_end_date': date(2025, 9, 30),
            'calculation_date': date(2025, 10, 1), 'period_revenue': 100, 'state': 'paid', 'paid_amount': 10
        })
        with self.assertRaises(UserError):
            payment_paid.action_cancel()

        # Reiniciar a borrador
        payment.action_reset_to_draft()
        self.assertEqual(payment.state, 'draft', "El pago debe reiniciarse a 'borrador'.")
        self.assertEqual(payment.paid_amount, 0.0)
        self.assertFalse(payment.payment_date)

    def test_09_create_invoice_from_royalty_payment(self):
        """Prueba la creación de factura desde un pago de regalías."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        payment.action_calculate()
        payment.action_confirm()

        action_dict = payment.action_create_invoice()
        self.assertTrue(action_dict, "Debe devolverse la acción para crear factura")
        self.assertEqual(action_dict.get('res_model'), 'account.move', "La acción debe apuntar a account.move")

        invoice = self.env['account.move'].browse(action_dict.get('res_id'))
        self.assertTrue(invoice.exists(), "La factura debe haberse creado")
        self.assertEqual(invoice.partner_id, self.test_franchise.franchisee_id)
        self.assertAlmostEqual(invoice.amount_untaxed, payment.calculated_amount, places=2)
        self.assertEqual(invoice.invoice_origin, payment.name)
        self.assertEqual(payment.invoice_count, 1)

        # Probar intentar crear una segunda factura
        with self.assertRaises(UserError, msg="No debe permitir crear una segunda factura."):
            payment.action_create_invoice()

    def test_10_view_invoices(self):
        """Prueba action_view_invoices."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        payment.action_calculate()
        payment.action_confirm()
        
        # Sin facturas aún
        action_no_invoice = payment.action_view_invoices()
        self.assertEqual(action_no_invoice['domain'], [('id', 'in', [])]) # Dominio para recordset vacío

        # Crear una factura
        invoice_action = payment.action_create_invoice()
        invoice_id = invoice_action['res_id']

        action_one_invoice = payment.action_view_invoices()
        self.assertEqual(action_one_invoice.get('res_model'), 'account.move')
        self.assertEqual(action_one_invoice.get('res_id'), invoice_id)
        self.assertEqual(action_one_invoice.get('view_mode'), 'form')

    def test_11_unlink_royalty_payment(self):
        """Prueba eliminar pagos de regalías con y sin facturas."""
        self.Currency.active = True
        
        # Pago sin factura
        payment_no_invoice = self.RoyaltyPayment.create(self.payment_data_valid)
        payment_id = payment_no_invoice.id
        payment_no_invoice.unlink()
        self.assertFalse(self.RoyaltyPayment.search([('id', '=', payment_id)]), "El pago debe eliminarse.")

        # Pago con factura borrador
        payment_with_draft_invoice = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': date(2025, 7, 1), 'period_end_date': date(2025, 7, 31),
            'calculation_date': date(2025, 8, 1), 'period_revenue': 300
        })
        payment_with_draft_invoice.action_calculate()
        payment_with_draft_invoice.action_confirm()
        invoice_action = payment_with_draft_invoice.action_create_invoice()
        invoice = self.env['account.move'].browse(invoice_action['res_id'])
        self.assertEqual(invoice.state, 'draft')
        
        payment_id_draft_inv = payment_with_draft_invoice.id
        invoice_id_draft = invoice.id
        payment_with_draft_invoice.unlink() # Debe eliminar pago y factura borrador
        self.assertFalse(self.RoyaltyPayment.search([('id', '=', payment_id_draft_inv)]), "El pago con factura borrador debe eliminarse.")
        self.assertFalse(self.AccountMove.search([('id', '=', invoice_id_draft)]), "La factura borrador debe eliminarse.")

        # Pago con factura publicada
        payment_with_posted_invoice = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': date(2025, 8, 1), 'period_end_date': date(2025, 8, 31),
            'calculation_date': date(2025, 9, 1), 'period_revenue': 400
        })
        payment_with_posted_invoice.action_calculate()
        payment_with_posted_invoice.action_confirm()
        invoice_action_posted = payment_with_posted_invoice.action_create_invoice()
        invoice_posted = self.env['account.move'].browse(invoice_action_posted['res_id'])
        invoice_posted.action_post() # Publicar la factura
        self.assertEqual(invoice_posted.state, 'posted')

        with self.assertRaises(ValidationError, msg="No debe eliminar pago con factura publicada."):
            payment_with_posted_invoice.unlink()

    def test_12_cron_check_overdue_payments(self):
        """Prueba la tarea cron check_overdue_payments."""
        # Crear un pago que debe vencerse
        due_date_for_cron = fields.Date.today() - timedelta(days=5)
        period_end_for_cron = due_date_for_cron - timedelta(days=self.test_franchise.royalty_payment_terms)
        
        payment_to_be_overdue = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': period_end_for_cron.replace(day=1),
            'period_end_date': period_end_for_cron,
            'calculation_date': period_end_for_cron + timedelta(days=1),
            'period_revenue': 700.00,
        })
        payment_to_be_overdue.action_calculate()
        payment_to_be_overdue.action_confirm()
        self.assertEqual(payment_to_be_overdue.state, 'confirmed')

        # Ejecutar el cron
        overdue_count = self.RoyaltyPayment.check_overdue_payments()
        
        # Refrescar el registro
        payment_to_be_overdue.invalidate_recordset()
        
        # Verificar que el pago ahora esté vencido
        self.assertEqual(payment_to_be_overdue.state, 'overdue', "El pago debe marcarse como vencido después del cron.")
        self.assertTrue(overdue_count >= 1, "El cron debe retornar al menos 1 pago marcado como vencido.")

    def test_13_compute_name(self):
        """Prueba el cálculo del nombre del pago."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        expected_name = f"ROY-{self.test_franchise.franchise_code}-2025-06"
        self.assertEqual(payment.name, expected_name, "El nombre calculado es incorrecto.")

    def test_14_compute_outstanding_amount(self):
        """Prueba el cálculo del monto pendiente."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        payment.action_calculate()
        
        # Inicialmente el monto pendiente debe igualar al calculado
        self.assertAlmostEqual(payment.outstanding_amount, payment.calculated_amount, places=2)
        
        # Después de un pago parcial
        payment.paid_amount = 50.0
        payment._compute_outstanding_amount()
        self.assertAlmostEqual(payment.outstanding_amount, 50.0, places=2, msg="El monto pendiente debe ser 50 después del pago parcial.")

    def test_15_compute_days_overdue(self):
        """Prueba el cálculo de días vencidos."""
        # Pago no vencido con fecha futura
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        self.assertEqual(payment.days_overdue, 0, "Los días vencidos deben ser 0 para pago no vencido.")
        
        # Crear pago vencido manualmente
        past_due_date = fields.Date.today() - timedelta(days=5)
        past_period_end = past_due_date - timedelta(days=self.test_franchise.royalty_payment_terms)
        
        overdue_payment = self.RoyaltyPayment.create({
            'franchise_id': self.test_franchise.id,
            'period_start_date': past_period_end.replace(day=1),
            'period_end_date': past_period_end,
            'calculation_date': past_period_end + timedelta(days=1),
            'period_revenue': 500.00,
            'state': 'overdue'  # Establecer manualmente como overdue
        })
        
        # Forzar recálculo
        overdue_payment._compute_days_overdue()
        self.assertEqual(overdue_payment.days_overdue, 5, "Los días vencidos deben ser 5 para pago vencido hace 5 días.")

    def test_16_state_transitions_edge_cases(self):
        """Prueba casos límite en las transiciones de estado."""
        payment = self.RoyaltyPayment.create(self.payment_data_valid)
        
        # Intentar confirmar desde borrador
        with self.assertRaises(UserError):
            payment.action_confirm()
        
        # Intentar registrar pago desde borrador
        with self.assertRaises(UserError):
            payment.action_register_payment()
        
        # Workflow correcto
        payment.action_calculate()
        payment.action_confirm()
        payment.action_register_payment()
        
        # Intentar acciones en estado pagado
        with self.assertRaises(UserError):
            payment.action_calculate()
        
        with self.assertRaises(UserError):
            payment.action_confirm()
        
        with self.assertRaises(UserError):
            payment.action_register_payment()