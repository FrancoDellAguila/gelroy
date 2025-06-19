# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError

class TestRecipeModel(TransactionCase):

    def setUp(self):
        super(TestRecipeModel, self).setUp()
        # Modelos
        self.Recipe = self.env['gelroy.recipe']
        self.RecipeIngredient = self.env['gelroy.recipe.ingredient']
        self.Product = self.env['product.product']
        self.UoM = self.env.ref('uom.product_uom_unit') # Unidad de Medida (Unidades)
        self.Currency = self.env.ref('base.EUR') # O la moneda que uses por defecto

        self.product_flour = self.Product.create({
            'name': 'Flour',
            'detailed_type': 'product',
            'list_price': 1.50, # Precio por unidad (ej. por kg)
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'taxes_id': [(5, 0, 0)], 
        })
        self.product_sugar = self.Product.create({
            'name': 'Sugar',
            'detailed_type': 'product',
            'list_price': 2.00,
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'taxes_id': [(5, 0, 0)],  
        })
        self.product_eggs = self.Product.create({
            'name': 'Eggs (unit)',
            'detailed_type': 'product',
            'list_price': 0.25, # Precio por huevo
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'taxes_id': [(5, 0, 0)],  
        })
        
        # Datos para una receta válida
        self.recipe_data_valid = {
            'name': 'Basic Cake Recipe',
            'code': 'CAKE001',
            'category': 'dessert',
            'production_size': 1.0, # Produce 1 torta
            'unit_of_measure': self.UoM.id, # La receta produce 'Unidades' de torta
            'preparation_time': 20, # minutos
            'cooking_time': 40, # minutos
            'currency_id': self.Currency.id,
        }

    def test_01_create_recipe_and_ingredients(self):
        """Prueba la creación básica de una receta y sus ingredientes."""
        recipe = self.Recipe.create(self.recipe_data_valid)
        self.assertTrue(recipe.id, "La receta debe crearse con un ID.")
        self.assertEqual(recipe.name, 'Basic Cake Recipe')
        self.assertEqual(recipe.active, True, "La receta debe estar activa por defecto.")

        ingredient1 = self.RecipeIngredient.create({
            'recipe_id': recipe.id,
            'product_id': self.product_flour.id,
            'quantity': 0.5, # 0.5 unidades de harina (ej. 0.5 kg si la UdM del producto es kg)
        })
        self.assertTrue(ingredient1.id, "El ingrediente 1 de la receta debe crearse.")
        self.assertAlmostEqual(ingredient1.unit_price, 1.50, places=2, 
                               msg="El precio unitario debe heredarse del producto harina.")
        self.assertAlmostEqual(ingredient1.total_cost, 0.5 * 1.50, places=2,
                               msg="El costo total del ingrediente debe calcularse correctamente.")

        ingredient2 = self.RecipeIngredient.create({
            'recipe_id': recipe.id,
            'product_id': self.product_eggs.id,
            'quantity': 4, # 4 huevos
        })
        self.assertTrue(ingredient2.id, "El ingrediente 2 de la receta debe crearse.")
        self.assertAlmostEqual(ingredient2.unit_price, 0.25, places=2,
                               msg="El precio unitario debe heredarse del producto huevos.")
        self.assertAlmostEqual(ingredient2.total_cost, 4 * 0.25, places=2,
                               msg="El costo total del ingrediente debe calcularse correctamente.")

        # Forzar recálculo de los campos compute de la receta
        recipe.invalidate_recordset(fnames=['ingredient_cost', 'cost_per_production', 'total_time'])

        self.assertEqual(recipe.total_time, 20 + 40, "El cálculo del tiempo total es incorrecto.")
        expected_ingredient_cost = (0.5 * 1.50) + (4 * 0.25)
        self.assertAlmostEqual(recipe.ingredient_cost, expected_ingredient_cost, places=2, 
                               msg="El costo de ingredientes de la receta es incorrecto.")
        self.assertAlmostEqual(recipe.cost_per_production, expected_ingredient_cost / recipe.production_size, places=2, 
                               msg="El costo por producción de la receta es incorrecto.")

    def test_02_recipe_computes_no_ingredients(self):
        """Prueba los campos calculados de la receta cuando no se añaden ingredientes."""
        recipe = self.Recipe.create(self.recipe_data_valid)
        recipe.invalidate_recordset(fnames=['ingredient_cost', 'cost_per_production'])
        self.assertAlmostEqual(recipe.ingredient_cost, 0.0, places=2,
                               msg="El costo de ingredientes debe ser 0 cuando no hay ingredientes.")
        self.assertAlmostEqual(recipe.cost_per_production, 0.0, places=2,
                               msg="El costo por producción debe ser 0 cuando no hay ingredientes.")

    def test_03_recipe_compute_cost_per_production_zero_size(self):
        """Prueba cost_per_production cuando production_size es cero (debe ser detectado por constraint)."""
        recipe_data_zero_size = self.recipe_data_valid.copy()
        recipe_data_zero_size['production_size'] = 0
        
        with self.assertRaises(ValidationError, msg="El tamaño de producción debe ser mayor que cero."):
            self.Recipe.create(recipe_data_zero_size)

        # Si se permitiera crear con 0 y luego se añaden ingredientes:
        recipe = self.Recipe.create(self.recipe_data_valid) # production_size = 1.0
        self.RecipeIngredient.create({
            'recipe_id': recipe.id,
            'product_id': self.product_flour.id,
            'quantity': 1,
        })
        recipe.invalidate_recordset(fnames=['ingredient_cost']) # Recalcular coste de ingredientes
        
        # Intentar poner production_size a 0 después de tener ingredientes
        # La constraint debería saltar antes del cálculo de cost_per_production
        with self.assertRaises(ValidationError, msg="El tamaño de producción debe ser mayor que cero."):
            recipe.write({'production_size': 0})

    def test_04_recipe_validation_constraints(self):
        """Prueba las restricciones de validación en Recipe."""
        # Production size cero o negativo
        with self.assertRaises(ValidationError, msg="El tamaño de producción debe ser mayor que cero."):
            self.Recipe.create({
                'name': 'Receta con Tamaño Inválido',
                'code': 'INVRS001',
                'category': 'food',
                'production_size': 0,
            })
        with self.assertRaises(ValidationError, msg="El tamaño de producción debe ser mayor que cero."):
            self.Recipe.create({
                'name': 'Receta con Tamaño Negativo',
                'code': 'INVRS002',
                'category': 'food',
                'production_size': -1,
            })

    def test_05_recipe_ingredient_validation_constraints(self):
        """Prueba las restricciones de validación en RecipeIngredient."""
        recipe = self.Recipe.create(self.recipe_data_valid)
        # Cantidad de ingrediente cero o negativa
        with self.assertRaises(ValidationError, msg="La cantidad del ingrediente debe ser mayor que cero."):
            self.RecipeIngredient.create({
                'recipe_id': recipe.id,
                'product_id': self.product_flour.id,
                'quantity': 0,
            })
        with self.assertRaises(ValidationError, msg="La cantidad del ingrediente debe ser mayor que cero."):
            self.RecipeIngredient.create({
                'recipe_id': recipe.id,
                'product_id': self.product_sugar.id,
                'quantity': -2,
            })

    def test_06_recipe_ingredient_unit_price_from_product_with_taxes(self):
        """Prueba si unit_price del ingrediente incluye impuestos del product.product taxes_id."""
        # Crear un impuesto de ejemplo
        Tax = self.env['account.tax']
        tax_10_percent = Tax.create({
            'name': "Impuesto de Prueba 10%",
            'amount_type': 'percent',
            'amount': 10.0,
            'type_tax_use': 'sale', # Para list_price, aunque en coste podría ser 'purchase'
        })

        product_with_tax = self.Product.create({
            'name': 'Producto con Impuesto',
            'detailed_type': 'product',
            'list_price': 100.0, # Precio base
            'uom_id': self.UoM.id,
            'uom_po_id': self.UoM.id,
            'taxes_id': [(6, 0, [tax_10_percent.id])] # Asignar el impuesto
        })

        recipe = self.Recipe.create(self.recipe_data_valid)
        ingredient_taxed = self.RecipeIngredient.create({
            'recipe_id': recipe.id,
            'product_id': product_with_tax.id,
            'quantity': 1,
        })

        # El unit_price en RecipeIngredient DEBE incluir el impuesto
        # compute_all con price_unit=100, quantity=1, tax 10% -> total_included = 110
        self.assertAlmostEqual(ingredient_taxed.unit_price, 110.0, places=2, 
                               msg="El precio unitario del ingrediente debe incluir los impuestos del producto.")
        self.assertAlmostEqual(ingredient_taxed.total_cost, 110.0, places=2,
                               msg="El costo total del ingrediente debe reflejar el precio unitario con impuestos incluidos.")

        # Verificar el coste de la receta
        recipe.invalidate_recordset(fnames=['ingredient_cost'])
        self.assertAlmostEqual(recipe.ingredient_cost, 110.0, places=2,
                               msg="El costo de ingredientes de la receta debe incluir los impuestos.")