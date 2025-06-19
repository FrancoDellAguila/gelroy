from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    # === CANTIDADES Y RESTRICCIONES ===
    
    min_franchise_qty = fields.Float(
        string='Minimum Franchise Quantity',
        default=1.0,
        help="Minimum quantity that can be ordered by franchises"
    )
    
    max_franchise_qty = fields.Float(
        string='Maximum Franchise Quantity',
        help="Maximum quantity that can be ordered by franchises (0 = no limit)"
    )
    
    franchise_qty_multiple = fields.Float(
        string='Quantity Multiple',
        default=1.0,
        help="Franchise orders must be in multiples of this quantity"
    )
    
    # === DISPONIBILIDAD ===
    
    available_franchise_ids = fields.Many2many(
        'gelroy.franchise',
        'product_franchise_availability_rel',
        'product_id',
        'franchise_id',
        string='Available for Franchises',
        help="Specific franchises that can order this product. Leave empty for all franchises."
    )
    
    available_franchise_types = fields.Selection([
        ('restaurant', 'Restaurant'),
        ('coffee_shop', 'Coffee Shop'),
        ('ice_cream_parlor', 'Ice Cream Parlor'),
        ('fast_food', 'Fast Food'),
        ('pizzeria', 'Pizzeria'),
        ('bakery_pastry', 'Bakery / Pastry Shop')
    ], string='Available for Franchise Types', help="Select franchise types that can order this product")
    
    # === INFORMACIÓN ADICIONAL ===
    
    product_lead_time = fields.Integer(
        string='Product Lead Time (days)',
        help="Expected delivery time for this product"
    )
    
    product_availability = fields.Selection([
        ('available', 'Available'),
        ('limited', 'Limited Stock'),
        ('backorder', 'Backorder Only'),
        ('discontinued', 'Discontinued'),
    ], string='Product Availability', default='available')
    
    available_franchise_count = fields.Integer(
        string='Available Franchise Count',
        compute='_compute_available_franchise_count'
    )
    
    product_capacity_text = fields.Char(
        string='Product Capacity',
        help="Product capacity or content (e.g., '500ml', '1kg', '250g')"
    )
    
    # === MÉTODOS COMPUTADOS  ===
    
    @api.depends('available_franchise_ids')
    def _compute_available_franchise_count(self):
        """Calcular el número de franquicias disponibles para cada producto"""
        for product in self:
            product.available_franchise_count = len(product.available_franchise_ids)
    
    # === MÉTODOS DE VALIDACIÓN ===
    
    @api.constrains('min_franchise_qty', 'max_franchise_qty')
    def _check_franchise_quantities(self):
        """Verificar que las cantidades mínimas y máximas de franquicia sean válidas"""
        for product in self:
            if product.min_franchise_qty < 0:
                raise ValidationError(_("Minimum franchise quantity cannot be negative."))
            
            if product.max_franchise_qty and product.max_franchise_qty < product.min_franchise_qty:
                raise ValidationError(_("Maximum franchise quantity cannot be less than minimum quantity."))
    
    @api.constrains('franchise_qty_multiple')
    def _check_franchise_qty_multiple(self):
        """Verificar que el múltiplo de cantidad de franquicia sea válido"""
        for product in self:
            if product.franchise_qty_multiple <= 0:
                raise ValidationError(_("Quantity multiple must be greater than zero."))
    
    # === MÉTODOS DE NEGOCIO  ===
    
    def check_franchise_availability(self, franchise_id):
        """Verificar si un producto está disponible para una franquicia específica"""
        self.ensure_one()
        
        if self.product_availability != 'available':
            return False
        
        franchise = self.env['gelroy.franchise'].browse(franchise_id)
        
        # Verificar tipo de franquicia
        if self.available_franchise_types and franchise.franchise_type != self.available_franchise_types:
            return False
        
        # Si hay restricciones específicas de franquicia
        if self.available_franchise_ids:
            return franchise in self.available_franchise_ids
        
        return True
    
    def get_franchise_price_for_quantity(self, quantity, franchise_id=None):
        """Obtener precio para una cantidad específica y franquicia"""
        self.ensure_one()
        
        # Verificar cantidad mínima
        if quantity < self.min_franchise_qty:
            raise UserError(_("Minimum order quantity for %s is %s") % (self.name, self.min_franchise_qty))
        
        # Verificar cantidad máxima
        if self.max_franchise_qty and quantity > self.max_franchise_qty:
            raise UserError(_("Maximum order quantity for %s is %s") % (self.name, self.max_franchise_qty))
        
        # Verificar múltiplos
        if self.franchise_qty_multiple > 1:
            if quantity % self.franchise_qty_multiple != 0:
                raise UserError(_("Quantity for %s must be in multiples of %s") % 
                              (self.name, self.franchise_qty_multiple))
        
        return self.list_price


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    min_franchise_qty = fields.Float(
        string='Minimum Franchise Quantity',
        default=1.0
    )
    
    max_franchise_qty = fields.Float(
        string='Maximum Franchise Quantity'
    )
    
    franchise_qty_multiple = fields.Float(
        string='Quantity Multiple',
        default=1.0
    )
    
    available_franchise_ids = fields.Many2many(
        'gelroy.franchise',
        'product_template_franchise_availability_rel',
        'product_tmpl_id',
        'franchise_id',
        string='Available for Franchises',
        help="Specific franchises that can order this product. Leave empty for all franchises."
    )
    
    available_franchise_types = fields.Selection([
        ('restaurant', 'Restaurant'),
        ('coffee_shop', 'Coffee Shop'),
        ('ice_cream_parlor', 'Ice Cream Parlor'),
        ('fast_food', 'Fast Food'),
        ('pizzeria', 'Pizzeria'),
        ('bakery_pastry', 'Bakery / Pastry Shop')
    ], string='Available for Franchise Types')
    
    product_lead_time = fields.Integer(
        string='Product Lead Time (days)'
    )
    
    product_availability = fields.Selection([
        ('available', 'Available'),
        ('limited', 'Limited Stock'),
        ('backorder', 'Backorder Only'),
        ('discontinued', 'Discontinued'),
    ], string='Product Availability', default='available')
    
    available_franchise_count = fields.Integer(
        string='Available Franchise Count',
        compute='_compute_available_franchise_count'
    )
    
    product_capacity_text = fields.Char(
        string='Product Capacity',
        help="Product capacity or content (e.g., '500ml', '1kg', '250g')"
    )
    
    @api.depends('available_franchise_ids')
    def _compute_available_franchise_count(self):
        """Calcular el número de franquicias disponibles para cada plantilla de producto"""
        for template in self:
            template.available_franchise_count = len(template.available_franchise_ids)
    
    @api.onchange('uom_id')
    def _onchange_uom_id_custom(self):
        # DESHABILITAR el comportamiento automático
        # No hacer nada, permitir que uom_po_id sea independiente
        pass
    
    # Establecer valores por defecto
    @api.model
    def default_get(self, fields_list):
        """Establecer valores por defecto para nuevos productos"""
        defaults = super().default_get(fields_list)
        defaults.update({
            'detailed_type': 'product',
            'sale_ok': True,
            'product_availability': 'available',
        })
        return defaults