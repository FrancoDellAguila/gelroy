# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError
from odoo import fields
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class TestProductionPlanning(TransactionCase):

    def setUp(self):
        super(TestProductionPlanning, self).setUp()
        # Modelos
        self.Partner = self.env['res.partner']
        self.Franchise = self.env['gelroy.franchise']
        self.Product = self.env['product.product']
        self.Recipe = self.env['gelroy.recipe']
        self.RecipeIngredient = self.env['gelroy.recipe.ingredient']
        self.ProductionPlanning = self.env['gelroy.production.planning']
        self.ProductionPlanningLine = self.env['gelroy.production.planning.line']
        self.StockOrder = self.env['gelroy.stock.order']
        self.UoM = self.env.ref('uom.product_uom_unit')
        self.Currency = self.env.ref('base.EUR')

        # Datos Comunes
        self.franchisee_partner_pp = self.Partner.create({'name': 'Franchisee Test PP'})
        self.test_franchise_pp = self.Franchise.create({
            'name': 'Franchise for ProdPlanning Tests',
            'franchise_code': 'FPP001',
            'franchisee_id': self.franchisee_partner_pp.id,
            'currency_id': self.Currency.id,
            'franchise_type': 'bakery_pastry',
        })

        # Productos Ingredientes SIN IMPUESTOS
        self.ing_flour = self.Product.create({
            'name': 'PP Flour', 'detailed_type': 'product', 'list_price': 1.0, 
            'uom_id': self.UoM.id, 'uom_po_id': self.UoM.id,
            'taxes_id': [(5, 0, 0)]
        })
        self.ing_sugar = self.Product.create({
            'name': 'PP Sugar', 'detailed_type': 'product', 'list_price': 2.0, 
            'uom_id': self.UoM.id, 'uom_po_id': self.UoM.id,
            'taxes_id': [(5, 0, 0)]
        })

        # Recetas
        self.recipe_bread = self.Recipe.create({
            'name': 'PP Bread Recipe', 'code': 'PPB001', 'category': 'food',
            'production_size': 10, 'unit_of_measure': self.UoM.id, 'currency_id': self.Currency.id,
            'ingredient_ids': [
                (0, 0, {'product_id': self.ing_flour.id, 'quantity': 5}), # Costo 5*1=5
                (0, 0, {'product_id': self.ing_sugar.id, 'quantity': 1}), # Costo 1*2=2
            ] # Costo total receta = 7.0
        })
        self.recipe_cake = self.Recipe.create({
            'name': 'PP Cake Recipe', 'code': 'PPC001', 'category': 'dessert',
            'production_size': 1, 'unit_of_measure': self.UoM.id, 'currency_id': self.Currency.id,
            'ingredient_ids': [
                (0, 0, {'product_id': self.ing_flour.id, 'quantity': 0.5}), # Costo 0.5*1=0.5
                (0, 0, {'product_id': self.ing_sugar.id, 'quantity': 0.3}), # Costo 0.3*2=0.6
            ] # Costo total receta = 1.1
        })
        
        # Datos para una planificación válida con fechas futuras
        self.planning_data_valid = {
            'franchise_id': self.test_franchise_pp.id,
            'planning_date': fields.Date.today(),
            'period_start_date': fields.Date.today() + timedelta(days=1),
            'period_end_date': fields.Date.today() + timedelta(days=10),
        }

    def test_01_create_production_planning_and_name(self):
        """Prueba la creación básica y generación automática de nombre."""
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        self.assertTrue(planning.id, "La planificación de producción debe crearse.")
        # El nombre ahora se genera como Plan-FCODE-MES-SEQ
        expected_name_part = f"Plan-{self.test_franchise_pp.franchise_code}-{planning.planning_date.month}-"
        self.assertTrue(planning.name.startswith(expected_name_part), 
                       f"El nombre de la planificación '{planning.name}' tiene formato incorrecto, se esperaba que comience con '{expected_name_part}'.")
        self.assertEqual(planning.state, 'draft', "El estado inicial debe ser borrador.")

    def test_02_planning_line_and_planning_computes(self):
        """Prueba los campos calculados en línea de planificación y cabecera de planificación."""
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        
        line1 = self.ProductionPlanningLine.create({
            'planning_id': planning.id,
            'recipe_id': self.recipe_bread.id, # Costo 7.0, tamaño prod 10
            'estimated_quantity': 2, # Se estiman 2 "batches" de esta receta
        })
        self.assertAlmostEqual(line1.total_productions, 2 * 10, places=2, 
                               msg="El total de producciones debe ser 2 lotes × 10 unidades/lote.")
        expected_line1_cost = 2 * self.recipe_bread.ingredient_cost
        self.assertAlmostEqual(line1.total_cost, expected_line1_cost, places=2,
                               msg="El costo total de la línea 1 debe calcularse correctamente.")

        line2 = self.ProductionPlanningLine.create({
            'planning_id': planning.id,
            'recipe_id': self.recipe_cake.id, # Costo 1.1, tamaño prod 1
            'estimated_quantity': 5, # Se estiman 5 tortas
        })
        self.assertAlmostEqual(line2.total_productions, 5 * 1, places=2,
                               msg="El total de producciones debe ser 5 lotes × 1 unidad/lote.")
        expected_line2_cost = 5 * self.recipe_cake.ingredient_cost
        self.assertAlmostEqual(line2.total_cost, expected_line2_cost, places=2,
                               msg="El costo total de la línea 2 debe calcularse correctamente.")

        # Forzar recálculo de los campos compute de la planificación
        planning.invalidate_recordset(fnames=['total_recipes', 'total_productions', 'estimated_cost'])

        self.assertEqual(planning.total_recipes, 2, "El total de recetas debe ser 2.")
        self.assertAlmostEqual(planning.total_productions, (2 * 10) + (5 * 1), places=2,
                               msg="El total de producciones debe sumar ambas líneas.")
        expected_total_cost = expected_line1_cost + expected_line2_cost
        self.assertAlmostEqual(planning.estimated_cost, expected_total_cost, places=2,
                               msg="El costo estimado total debe sumar ambas líneas.")

    def test_03_workflow_confirm_create_stock_order(self):
        """Prueba las acciones de confirmar y crear pedido de stock."""
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        self.ProductionPlanningLine.create({
            'planning_id': planning.id, 'recipe_id': self.recipe_bread.id, 'estimated_quantity': 1
        })
        self.ProductionPlanningLine.create({
            'planning_id': planning.id, 'recipe_id': self.recipe_cake.id, 'estimated_quantity': 3
        })
        planning.invalidate_recordset() # Recalcular totales

        # Confirmar
        planning.action_confirm()
        self.assertEqual(planning.state, 'confirmed', "El estado debe cambiar a confirmado.")

        # Crear Pedido de Stock
        action_result = planning.action_create_stock_order()
        self.assertEqual(planning.state, 'stock_ordered', "El estado debe cambiar a pedido de stock creado.")
        self.assertTrue(planning.stock_order_ids, "El pedido de stock debe crearse y vincularse.")
        self.assertEqual(planning.stock_order_count, 1, "Debe haber exactamente 1 pedido de stock.")
        
        stock_order = planning.stock_order_ids[0]
        self.assertEqual(stock_order.franchise_id, planning.franchise_id, 
                        "La franquicia del pedido debe coincidir con la planificación.")
        self.assertEqual(stock_order.production_planning_id, planning,
                        "El pedido debe estar vinculado a la planificación.")
        self.assertEqual(len(stock_order.order_line_ids), 2, 
                        "El pedido de stock debe tener 2 líneas (una por cada ingrediente único).")

        # Verificar cantidades de ingredientes en el pedido de stock
        # Receta Pan (1 batch): 5 harina, 1 azúcar
        # Receta Torta (3 batches): 0.5*3=1.5 harina, 0.3*3=0.9 azúcar
        # Total Harina: 5 + 1.5 = 6.5
        # Total Azúcar: 1 + 0.9 = 1.9
        flour_line = stock_order.order_line_ids.filtered(lambda l: l.product_id == self.ing_flour)
        sugar_line = stock_order.order_line_ids.filtered(lambda l: l.product_id == self.ing_sugar)
        
        self.assertTrue(flour_line, "La harina debe estar en el pedido de stock.")
        self.assertAlmostEqual(flour_line.quantity, 6.5, places=2,
                               msg="La cantidad de harina debe ser la suma de ambas recetas.")
        self.assertTrue(sugar_line, "El azúcar debe estar en el pedido de stock.")
        self.assertAlmostEqual(sugar_line.quantity, 1.9, places=2,
                               msg="La cantidad de azúcar debe ser la suma de ambas recetas.")

        # Verificar que no se puede crear otro pedido de stock
        with self.assertRaises(UserError, msg="No debe permitir crear otro pedido de stock."):
            planning.action_create_stock_order()
            
        # Verificar la acción de ver pedidos
        view_action = planning.action_view_stock_orders()
        self.assertEqual(view_action['res_id'], stock_order.id,
                        "La acción debe mostrar el pedido correcto.")

    def test_04_validation_constraints_planning(self):
        """Prueba las restricciones de validación en ProductionPlanning."""
        # Confirmar sin líneas
        planning_no_lines = self.ProductionPlanning.create(self.planning_data_valid)
        with self.assertRaisesRegex(UserError, "Cannot confirm planning without recipes."):
            planning_no_lines.action_confirm()

        # Fechas de periodo inválidas con fechas futuras
        with self.assertRaisesRegex(UserError, "Period End Date .* must be after Period Start Date"):
            planning_invalid_dates = self.ProductionPlanning.create({
                'franchise_id': self.test_franchise_pp.id,
                'planning_date': fields.Date.today(),
                'period_start_date': fields.Date.today() + timedelta(days=10),
                'period_end_date': fields.Date.today() + timedelta(days=5), # Fin antes de inicio
                'planning_line_ids': [(0,0, {'recipe_id': self.recipe_bread.id, 'estimated_quantity': 1})]
            })
            planning_invalid_dates.action_confirm()

    def test_05_validation_constraints_planning_line(self):
        """Prueba las restricciones de validación en ProductionPlanningLine."""
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        with self.assertRaisesRegex(ValidationError, "Estimated quantity must be greater than zero."):
            self.ProductionPlanningLine.create({
                'planning_id': planning.id,
                'recipe_id': self.recipe_bread.id,
                'estimated_quantity': 0, # Inválido
            })

    def test_06_action_confirm_date_validations(self):
        """Prueba las validaciones de fecha dentro de action_confirm."""
        planning = self.ProductionPlanning.create({
            'franchise_id': self.test_franchise_pp.id,
            'planning_date': fields.Date.today() - timedelta(days=5), # Fecha de planificación en el pasado
            'period_start_date': fields.Date.today() - timedelta(days=2), # Inicio en el pasado
            'period_end_date': fields.Date.today() + timedelta(days=5),
            'planning_line_ids': [(0,0, {'recipe_id': self.recipe_bread.id, 'estimated_quantity': 1})]
        })
        with self.assertRaisesRegex(UserError, "Period Start Date .* cannot be earlier than today"):
            planning.action_confirm()

        planning.period_start_date = fields.Date.today()
        planning.period_end_date = fields.Date.today() - timedelta(days=1) # Fin antes de inicio
        with self.assertRaisesRegex(UserError, "Period End Date .* must be after Period Start Date"):
            planning.action_confirm()

    def test_07_action_cancel_and_set_to_draft(self):
        """Prueba las acciones de cancelar y establecer como borrador."""
        # Crear planning con líneas
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        self.ProductionPlanningLine.create({
            'planning_id': planning.id, 'recipe_id': self.recipe_bread.id, 'estimated_quantity': 1
        })
        
        planning.action_confirm() # Estado: confirmed
        
        planning.action_cancel()
        self.assertEqual(planning.state, 'cancelled', "El estado debe cambiar a cancelado.")

        planning.action_set_to_draft()
        self.assertEqual(planning.state, 'draft', "El estado debe volver a borrador.")

        # Test simplificado de completed state
        planning.action_confirm()
        planning.action_create_stock_order() # stock_ordered
        
        # Simular que todos los stock orders están delivered
        for so in planning.stock_order_ids:
            so.write({'state': 'delivered'})  # Forzar estado para el test

        planning._check_completion() # Forzar la verificación
        self.assertEqual(planning.state, 'completed', "El estado debe cambiar a completado.")
        
        with self.assertRaisesRegex(UserError, "Cannot cancel a planning that is already .* completed"):
            planning.action_cancel()

    def test_08_check_completion_method(self):
        """Prueba el método _check_completion."""
        planning = self.ProductionPlanning.create(self.planning_data_valid)
        self.ProductionPlanningLine.create({
            'planning_id': planning.id, 'recipe_id': self.recipe_bread.id, 'estimated_quantity': 1
        })
        planning.action_confirm()
        planning.action_create_stock_order()
        self.assertEqual(planning.state, 'stock_ordered', "El estado debe ser pedido de stock.")

        # Aún no completado porque el pedido no está entregado
        planning._check_completion()
        self.assertEqual(planning.state, 'stock_ordered', 
                        "El estado debe permanecer como pedido de stock hasta que se entregue.")

        # Marcar pedido de stock como entregado de forma simple
        for so in planning.stock_order_ids:
            so.write({'state': 'delivered'}) # Forzar estado para el test

        planning._check_completion()
        self.assertEqual(planning.state, 'completed', 
                        "La planificación debe completarse si todos los pedidos de stock están entregados.")