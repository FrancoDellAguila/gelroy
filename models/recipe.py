from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class Recipe(models.Model):
    _name = 'gelroy.recipe'
    _description = 'Recipe'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Recipe Name', required=True)
    code = fields.Char(string='Recipe Code', required=True)
    description = fields.Text(string='Description')
    category = fields.Selection([
        ('food', 'Food'),
        ('beverage', 'Beverage'),
        ('dessert', 'Dessert'),
        ('appetizer', 'Appetizer'),
    ], string='Category', required=True)
    
    # Información de producción
    production_size = fields.Float(string='Production Size', default=1.0, required=True)
    unit_of_measure = fields.Many2one('uom.uom', string='Unit of Measure')
    preparation_time = fields.Float(string='Preparation Time (minutes)')
    cooking_time = fields.Float(string='Cooking Time (minutes)')
    total_time = fields.Float(string='Total Time', compute='_compute_total_time', store=True)
    
    # Costos
    ingredient_cost = fields.Monetary(string='Ingredient Cost', compute='_compute_costs', store=True)
    cost_per_production = fields.Monetary(string='Cost per Production', compute='_compute_costs', store=True)
    
    # Estado
    active = fields.Boolean(string='Active', default=True)
    
    # Relaciones
    ingredient_ids = fields.One2many('gelroy.recipe.ingredient', 'recipe_id', string='Ingredients')
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    
    @api.depends('preparation_time', 'cooking_time')
    def _compute_total_time(self):
        """Calcular el tiempo total de preparación y cocción."""
        for recipe in self:
            recipe.total_time = (recipe.preparation_time or 0) + (recipe.cooking_time or 0)
    
    @api.depends('ingredient_ids.total_cost')
    def _compute_costs(self):
        """Calcular el costo total de los ingredientes y el costo por producción."""
        for recipe in self:
            recipe.ingredient_cost = sum(ingredient.total_cost for ingredient in recipe.ingredient_ids)
            recipe.cost_per_production = recipe.ingredient_cost / recipe.production_size if recipe.production_size else 0

    @api.constrains('production_size')
    def _check_production_size(self):
        """Verificar que el tamaño de producción sea mayor que cero."""
        for recipe in self:
            if recipe.production_size <= 0:
                raise ValidationError(_("production size must be greater than zero."))

class RecipeIngredient(models.Model):
    _name = 'gelroy.recipe.ingredient'
    _description = 'Recipe Ingredient'
    _order = 'sequence, product_id'

    recipe_id = fields.Many2one('gelroy.recipe', string='Recipe', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', 
                                     related='product_id.uom_id', store=True, readonly=True)
    
    unit_price = fields.Monetary(string='Unit Price', 
                                 compute='_compute_unit_price', 
                                 store=True, readonly=True)
    total_cost = fields.Monetary(string='Total Cost', compute='_compute_total_cost', store=True)
    currency_id = fields.Many2one('res.currency', related='recipe_id.currency_id', readonly=True)
    
    # Campos informativos
    product_code = fields.Char(related='product_id.default_code', readonly=True)
    notes = fields.Text(string='Notes')

    @api.depends('product_id')
    def _compute_unit_price(self):
        """Establecer el precio del producto con impuestos incluidos"""
        for line in self:
            if line.product_id:
                base_price = line.product_id.list_price
                taxes = line.product_id.taxes_id
                
                if taxes:
                    tax_result = taxes.compute_all(
                        price_unit=base_price,
                        currency=line.currency_id,
                        quantity=1.0,
                        product=line.product_id,
                        partner=False
                    )
                    line.unit_price = tax_result['total_included']
                else:
                    line.unit_price = base_price
            else:
                line.unit_price = 0.0

    @api.depends('quantity', 'unit_price')
    def _compute_total_cost(self):
        """Calcular el costo total del ingrediente."""
        for ingredient in self:
            ingredient.total_cost = ingredient.quantity * ingredient.unit_price

    @api.constrains('quantity')
    def _check_quantity(self):
        """Verificar que la cantidad del ingrediente sea mayor que cero."""
        for ingredient in self:
            if ingredient.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))