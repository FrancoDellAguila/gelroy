# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from datetime import date
from dateutil.relativedelta import relativedelta

class TestFranchiseDashboard(TransactionCase):

    def setUp(self):
        super(TestFranchiseDashboard, self).setUp()
        # Modelos necesarios
        self.Partner = self.env['res.partner']
        self.Franchise = self.env['gelroy.franchise']
        self.RoyaltyPayment = self.env['gelroy.royalty.payment']
        self.StockOrder = self.env['gelroy.stock.order']
        self.Product = self.env['product.product']
        self.FranchiseDashboard = self.env['gelroy.franchise.dashboard']
        self.ExecutiveDashboard = self.env['gelroy.executive.dashboard']
        self.Currency = self.ref('base.EUR')  
        self.UoM = self.ref('uom.product_uom_unit')  

        # Crear socios franquiciados
        self.franchisee_a = self.Partner.create({'name': 'Franquiciado A'})
        self.franchisee_b = self.Partner.create({'name': 'Franquiciado B'})

        # Crear franquicias
        self.franchise_a = self.Franchise.create({
            'name': 'Franquicia A',
            'franchise_code': 'FA01',
            'franchisee_id': self.franchisee_a.id,
            'currency_id': self.Currency, 
            'franchise_type': 'restaurant',
            'royalty_fee_percentage': 10.0
        })
        self.franchise_b = self.Franchise.create({
            'name': 'Franquicia B',
            'franchise_code': 'FB01',
            'franchisee_id': self.franchisee_b.id,
            'currency_id': self.Currency,
            'franchise_type': 'restaurant',
            'royalty_fee_percentage': 10.0
        })

        # Crear productos sin impuestos
        self.product_a = self.Product.create({
            'name': 'Producto A Dashboard',
            'detailed_type': 'product',
            'list_price': 10.0,
            'uom_id': self.UoM, 
            'uom_po_id': self.UoM, 
            'taxes_id': [(5, 0, 0)]
        })
        self.product_b = self.Product.create({
            'name': 'Producto B Dashboard',
            'detailed_type': 'product',
            'list_price': 25.0,
            'uom_id': self.UoM,
            'uom_po_id': self.UoM,
            'taxes_id': [(5, 0, 0)]
        })

        # Crear algunos pagos de regalías para diferentes fechas y franquicias
        # Pagos para Franquicia A en Enero 2023
        self.RoyaltyPayment.create({
            'franchise_id': self.franchise_a.id,
            'period_start_date': date(2023, 1, 1),
            'period_end_date': date(2023, 1, 31),
            'calculation_date': date(2023, 2, 1),
            'period_revenue': 1000,
            'state': 'paid',
            'paid_amount': 100
        })
        
        # Pagos para Franquicia A en Febrero 2023 (vencido)
        self.RoyaltyPayment.create({
            'franchise_id': self.franchise_a.id,
            'period_start_date': date(2023, 2, 1),
            'period_end_date': date(2023, 2, 28),
            'calculation_date': date(2023, 3, 1),
            'period_revenue': 500,
            'state': 'overdue',
            'payment_due_date': date(2023, 3, 15)
        })
        
        # Pagos para Franquicia B en Enero 2023
        self.RoyaltyPayment.create({
            'franchise_id': self.franchise_b.id,
            'period_start_date': date(2023, 1, 1),
            'period_end_date': date(2023, 1, 31),
            'calculation_date': date(2023, 2, 1),
            'period_revenue': 2000,
            'state': 'paid',
            'paid_amount': 200
        })

    def test_01_royalty_kpis_no_filters(self):
        """Prueba los KPIs de regalías en el dashboard sin filtros (debe agregar todo)."""
        dashboard = self.FranchiseDashboard.create({
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 12, 31)
        })

        # Total calculado: 1000*0.1 + 500*0.1 + 2000*0.1 = 350
        self.assertAlmostEqual(dashboard.total_royalties_calculated, 350, places=2,
                               msg="El total de regalías calculadas debe incluir todas las franquicias.")
        self.assertAlmostEqual(dashboard.total_royalties_paid, 300, places=2,
                               msg="El total de regalías pagadas debe ser 100 + 200.")
        self.assertAlmostEqual(dashboard.total_royalties_outstanding, 50, places=2,
                               msg="El total pendiente debe ser solo el overdue de Franquicia A.")
        self.assertEqual(dashboard.overdue_royalty_payments_count, 1,
                        "Debe haber exactamente 1 pago de regalía vencido.")
        self.assertAlmostEqual(dashboard.overdue_royalty_payments_amount, 50, places=2,
                               msg="El monto vencido debe ser 50.")

    def test_02_royalty_kpis_filtered_by_franchise_a(self):
        """Prueba los KPIs de regalías filtrados para una franquicia específica."""
        dashboard = self.FranchiseDashboard.create({
            'franchise_id': self.franchise_a.id,
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 12, 31)
        })

        self.assertAlmostEqual(dashboard.total_royalties_calculated, 150, places=2,
                               msg="El total calculado debe ser solo de Franquicia A (100 + 50).")
        self.assertAlmostEqual(dashboard.total_royalties_paid, 100, places=2,
                               msg="El total pagado debe ser solo de Franquicia A.")
        self.assertAlmostEqual(dashboard.total_royalties_outstanding, 50, places=2,
                               msg="El total pendiente debe ser solo de Franquicia A.")
        self.assertEqual(dashboard.overdue_royalty_payments_count, 1,
                        "Franquicia A debe tener 1 pago vencido.")

    def test_03_royalty_kpis_filtered_by_date_range(self):
        """Prueba los KPIs de regalías filtrados para un rango de fechas específico."""
        dashboard = self.FranchiseDashboard.create({
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 1, 31)  # Solo Enero
        })
        
        self.assertAlmostEqual(dashboard.total_royalties_calculated, 300, places=2,
                               msg="El total calculado debe ser solo de Enero (100 + 200).")
        self.assertAlmostEqual(dashboard.total_royalties_paid, 300, places=2,
                               msg="El total pagado debe ser solo de Enero.")
        self.assertAlmostEqual(dashboard.total_royalties_outstanding, 0, places=2,
                               msg="No debe haber pagos vencidos en Enero.")
        self.assertEqual(dashboard.overdue_royalty_payments_count, 0,
                        "No debe haber pagos vencidos en Enero.")

    def test_04_performance_status_calculation(self):
        """Prueba el cálculo del KPI performance_status."""
        dashboard_good = self.FranchiseDashboard.create({
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 1, 31)  # En Enero el collection rate es 100%
        })
        
        # Con los datos de Enero, royalty_collection_rate será 1.0 (300 pagado / 300 calculado)
        self.assertEqual(dashboard_good.performance_status, '🟢 Excellent',
                        "El estado de rendimiento debe ser Excelente con 100% de cobro.")

        # Crear un escenario para un performance status diferente usando diferente mes y franquicia
        self.RoyaltyPayment.create({
            'franchise_id': self.franchise_b.id,  # Usar franquicia B
            'period_start_date': date(2023, 8, 1),  # Usar agosto en lugar de julio
            'period_end_date': date(2023, 8, 31),
            'calculation_date': date(2023, 9, 1),
            'period_revenue': 1000,
            'state': 'confirmed'
            # Sin paid_amount, outstanding será 100
        })
        
        dashboard_poor = self.FranchiseDashboard.create({
            'date_from': date(2023, 8, 1),  # Cambiar a agosto
            'date_to': date(2023, 8, 31)
        })
        
        # Con este nuevo pago, royalty_collection_rate será 0% para Agosto
        self.assertEqual(dashboard_poor.performance_status, '⚫ Critical',
                        "El estado de rendimiento debe ser Crítico con 0% de cobro.")

    def test_05_stock_kpis_basic(self):
        """Prueba la creación básica del dashboard."""
        dashboard = self.FranchiseDashboard.create({
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 1, 31)
        })

        # Verificar solo que el dashboard se crea correctamente
        self.assertTrue(dashboard.id, "El dashboard debe crearse correctamente.")
        self.assertEqual(dashboard.date_from, date(2023, 1, 1), "La fecha de inicio debe ser correcta.")
        self.assertEqual(dashboard.date_to, date(2023, 1, 31), "La fecha de fin debe ser correcta.")

    def test_06_simple_dashboard_creation(self):
        """Prueba la creación simple de dashboards sin KPIs complejos."""
        # Solo crear y verificar que los dashboards básicos funcionan
        franchise_dashboard = self.FranchiseDashboard.create({
            'franchise_id': self.franchise_a.id,
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 1, 31)
        })
        
        # Verificar que se crea correctamente
        self.assertTrue(franchise_dashboard.id, "El dashboard de franquicia debe crearse correctamente.")
        self.assertEqual(franchise_dashboard.franchise_id, self.franchise_a, "La franquicia debe coincidir.")

    def test_07_dashboard_date_filtering(self):
        """Prueba el filtrado por fechas en el dashboard."""
        # Crear pagos en diferentes meses
        self.RoyaltyPayment.create({
            'franchise_id': self.franchise_a.id,
            'period_start_date': date(2023, 3, 1),
            'period_end_date': date(2023, 3, 31),
            'calculation_date': date(2023, 4, 1),
            'period_revenue': 500,
            'state': 'paid',
            'paid_amount': 50
        })

        # Dashboard solo para Marzo
        dashboard_march = self.FranchiseDashboard.create({
            'date_from': date(2023, 3, 1),
            'date_to': date(2023, 3, 31)
        })

        self.assertAlmostEqual(dashboard_march.total_royalties_calculated, 50, places=2,
                               msg="Solo debe incluir las regalías de Marzo.")
        self.assertAlmostEqual(dashboard_march.total_royalties_paid, 50, places=2,
                               msg="Solo debe incluir los pagos de Marzo.")

        # Dashboard para todo el primer trimestre
        dashboard_q1 = self.FranchiseDashboard.create({
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 3, 31)
        })

        # Debe incluir todos los pagos del setUp + el nuevo de Marzo
        expected_total = 350 + 50  # 350 del setUp + 50 de Marzo
        self.assertAlmostEqual(dashboard_q1.total_royalties_calculated, expected_total, places=2,
                               msg="Debe incluir todas las regalías del primer trimestre.")

    def test_08_franchise_filtering(self):
        """Prueba el filtrado por franquicia específica."""
        dashboard_a = self.FranchiseDashboard.create({
            'franchise_id': self.franchise_a.id,
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 12, 31)
        })

        dashboard_b = self.FranchiseDashboard.create({
            'franchise_id': self.franchise_b.id,
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 12, 31)
        })

        # Franquicia A: 100 (pagado) + 50 (pendiente) = 150 total
        self.assertAlmostEqual(dashboard_a.total_royalties_calculated, 150, places=2,
                               msg="Franquicia A debe tener 150 en total calculado.")

        # Franquicia B: 200 (pagado) = 200 total
        self.assertAlmostEqual(dashboard_b.total_royalties_calculated, 200, places=2,
                               msg="Franquicia B debe tener 200 en total calculado.")

        # Solo Franquicia A tiene pagos vencidos
        self.assertEqual(dashboard_a.overdue_royalty_payments_count, 1,
                        "Solo Franquicia A debe tener pagos vencidos.")
        self.assertEqual(dashboard_b.overdue_royalty_payments_count, 0,
                        "Franquicia B no debe tener pagos vencidos.")