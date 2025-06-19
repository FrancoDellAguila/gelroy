from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class StockOrderLine(models.Model):
    _name = 'gelroy.stock.order.line'
    _description = 'Stock Order Line'
    _order = 'sequence, id'

    order_id = fields.Many2one('gelroy.stock.order', string='Stock Order', 
                               required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_code = fields.Char(related='product_id.default_code', readonly=True)
    product_name = fields.Char(related='product_id.name', readonly=True)
    
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', 
                                     related='product_id.uom_id', 
                                     store=True, readonly=True)
    
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    
    unit_price = fields.Monetary(string='Unit Price', 
                                 compute='_compute_unit_price', 
                                 store=True, readonly=True)
    
    # Campos de cálculo de impuestos
    price_subtotal = fields.Monetary(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Monetary(string='Tax Amount', compute='_compute_amount', store=True)
    price_total = fields.Monetary(string='Total', compute='_compute_amount', store=True)
    
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id', readonly=True) 
    
    notes = fields.Text(string='Line Notes')

    @api.depends('product_id')
    def _compute_unit_price(self):
        """Establecer el precio del producto automáticamente"""
        for line in self:
            if line.product_id:
                line.unit_price = line.product_id.list_price
            else:
                line.unit_price = 0.0

    @api.depends('quantity', 'unit_price', 'product_id.taxes_id')
    def _compute_amount(self):
        """Calcular subtotal, impuestos y total de la línea"""
        for line in self:
            price = line.unit_price * line.quantity
            
            # Usar los impuestos configurados en el producto
            if line.product_id and line.product_id.taxes_id:
                taxes = line.product_id.taxes_id.compute_all(
                    price_unit=line.unit_price,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.order_id.franchisee_id if line.order_id else None
                )
                line.price_subtotal = taxes['total_excluded']
                line.price_tax = taxes['total_included'] - taxes['total_excluded']
                line.price_total = taxes['total_included']
            else:
                line.price_subtotal = price
                line.price_tax = 0.0
                line.price_total = price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Al cambiar producto: establecer valores por defecto y verificar disponibilidad"""
        if self.product_id:
            # Al cambiar el producto, los campos related se actualizan automáticamente
            # Solo establecer cantidad por defecto si está vacía
            if not self.quantity:
                self.quantity = 1.0
                
            # Verificar disponibilidad para franquicia si existe el método
            franchise_id = self.order_id.franchise_id.id if self.order_id.franchise_id else None
            
            if franchise_id:
                try:
                    # Verificar disponibilidad si el método existe
                    if hasattr(self.product_id, 'check_franchise_availability'):
                        if not self.product_id.check_franchise_availability(franchise_id):
                            return {'warning': {
                                'title': _('Product Not Available'),
                                'message': _('This product is not available for the selected franchise.')
                            }}
                    
                    # Establecer cantidad mínima si existe
                    if hasattr(self.product_id, 'min_franchise_qty') and self.product_id.min_franchise_qty > 1:
                        self.quantity = self.product_id.min_franchise_qty
                    
                except Exception as e:
                    return {'warning': {
                        'title': _('Product Restriction'),
                        'message': str(e)
                    }}

    @api.constrains('quantity', 'product_id')
    def _check_franchise_quantity_constraints(self):
        """Verificar restricciones de cantidad específicas para franquicias"""
        for line in self:
            if line.product_id and line.order_id.franchise_id:
                # Verificar restricciones de cantidad para franquicias si existen
                if hasattr(line.product_id, 'min_franchise_qty') and line.quantity < line.product_id.min_franchise_qty:
                    raise ValidationError(_("Minimum quantity for %s is %s") % 
                                        (line.product_id.name, line.product_id.min_franchise_qty))
                
                if hasattr(line.product_id, 'max_franchise_qty') and line.product_id.max_franchise_qty and line.quantity > line.product_id.max_franchise_qty:
                    raise ValidationError(_("Maximum quantity for %s is %s") % 
                                        (line.product_id.name, line.product_id.max_franchise_qty))
                
                if hasattr(line.product_id, 'franchise_qty_multiple') and line.product_id.franchise_qty_multiple > 1:
                    if line.quantity % line.product_id.franchise_qty_multiple != 0:
                        raise ValidationError(_("Quantity for %s must be in multiples of %s") % 
                                            (line.product_id.name, line.product_id.franchise_qty_multiple))

    @api.constrains('quantity', 'product_id', 'unit_price')
    def _check_order_state_modifications(self):
        """Prevenir modificaciones cuando el pedido está aprobado o en estados posteriores"""
        for line in self:
            if line.order_id.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                raise ValidationError(_(
                    "Cannot modify order lines when order is in state '%s'. "
                    "Order: %s"
                ) % (line.order_id.state, line.order_id.name))

    def write(self, vals):
        """Sobrescribir write para prevenir modificaciones en estados aprobados+"""
         # Verificar si se están modificando campos críticos
        protected_fields = ['quantity', 'product_id', 'unit_price', 'order_id']
        if any(field in vals for field in protected_fields):
            for line in self:
                if line.order_id.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                    raise UserError(_(
                        "Cannot modify order line for product '%s'. "
                        "Order '%s' is in state '%s' and is locked for modifications."
                    ) % (line.product_id.name, line.order_id.name, line.order_id.state))
        
        return super().write(vals)

    def unlink(self):
        """Sobrescribir unlink para prevenir eliminación en estados aprobados+"""
        for line in self:
            if line.order_id.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                raise UserError(_(
                    "Cannot delete order line for product '%s'. "
                    "Order '%s' is in state '%s' and is locked for modifications."
                ) % (line.product_id.name, line.order_id.name, line.order_id.state))
        
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        """Sobrescribir create para prevenir agregar líneas en estados aprobados+"""
        for vals in vals_list:
            if 'order_id' in vals:
                order = self.env['gelroy.stock.order'].browse(vals['order_id'])
                if order.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                    raise UserError(_(
                        "Cannot add order lines. Order '%s' is in state '%s' and is locked for modifications."
                    ) % (order.name, order.state))
        
        return super().create(vals_list)