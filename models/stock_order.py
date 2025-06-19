from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta

class StockOrder(models.Model):
    _name = 'gelroy.stock.order'
    _description = 'Franchise Stock Order'
    _order = 'order_date desc, name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string="Order Reference", readonly=True, copy=False, default="New Stock Order")
    
    franchise_id = fields.Many2one('gelroy.franchise', string='Franchise', required=True, 
                                   ondelete='cascade', tracking=True)
    franchisee_id = fields.Many2one('res.partner', string='Franchisee', 
                                    related='franchise_id.franchisee_id', store=False, readonly=True)  # Cambiar store=False
    
    order_date = fields.Date(string='Order Date', default=fields.Date.context_today, 
                             required=True, tracking=True)
    requested_delivery_date = fields.Date(string='Requested Delivery Date', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('overdue', 'Overdue'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    priority = fields.Selection([
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),
        ('emergency', 'Emergency'),
    ], string='Priority', default='normal', tracking=True)
    
    # Líneas de pedido
    order_line_ids = fields.One2many('gelroy.stock.order.line', 'order_id', 
                                     string="Order Lines", copy=True)
    
    # Campos calculados
    total_items = fields.Integer(string='Total Items', compute='_compute_totals', store=True)
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_totals', store=True)
    currency_id = fields.Many2one('res.currency', related='franchise_id.currency_id', 
                                  store=False, readonly=True)
    
    # Información adicional
    notes = fields.Text(string='Notes')
    delivery_address = fields.Text(string='Delivery Address', compute='_compute_delivery_address', 
                                   store=False)
    
    # Campos de seguimiento
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Date(string='Approved Date', readonly=True)
    shipped_date = fields.Date(string='Shipped Date', readonly=True)
    delivered_date = fields.Date(string='Delivered Date', readonly=True)

    # campos de impuestos
    amount_untaxed = fields.Monetary(string='Subtotal', compute='_compute_totals', store=True)
    amount_tax = fields.Monetary(string='Taxes', compute='_compute_totals', store=True)

    production_planning_id = fields.Many2one('gelroy.production.planning', 
                                        string='Production Planning', 
                                        readonly=True)

    payment_date = fields.Date(string='Payment Date', readonly=True, tracking=True)

    # campos de vencimiento:
    payment_due_date = fields.Date(string='Payment Due Date', tracking=True,
                                   help="Date when payment is due")
    days_overdue = fields.Integer(string='Days Overdue', compute='_compute_days_overdue', store=True)
    outstanding_amount = fields.Monetary(string='Outstanding Amount', compute='_compute_outstanding_amount', store=True)

    @api.depends('order_line_ids.price_subtotal', 'order_line_ids.price_tax', 'order_line_ids.price_total')
    def _compute_totals(self):
        for order in self:
            total_items = len(order.order_line_ids)  # Número de líneas de pedido
            amount_untaxed = sum(line.price_subtotal for line in order.order_line_ids)
            amount_tax = sum(line.price_tax for line in order.order_line_ids)
            amount_total = sum(line.price_total for line in order.order_line_ids)
            
            order.total_items = total_items
            order.amount_untaxed = amount_untaxed
            order.amount_tax = amount_tax
            order.total_amount = amount_total

    @api.depends('franchise_id')
    def _compute_delivery_address(self):
        for order in self:
            if order.franchise_id:
                address_parts = []
                if order.franchise_id.street:
                    address_parts.append(order.franchise_id.street)
                if order.franchise_id.city:
                    address_parts.append(order.franchise_id.city)
                if order.franchise_id.state_id:
                    address_parts.append(order.franchise_id.state_id.name)
                if order.franchise_id.zip:
                    address_parts.append(order.franchise_id.zip)
                if order.franchise_id.country_id:
                    address_parts.append(order.franchise_id.country_id.name)
                order.delivery_address = ', '.join(address_parts)
            else:
                order.delivery_address = ""

    def action_submit(self):
        """Submits the order for approval"""
        for order in self:
            if not order.order_line_ids:
                raise UserError(_("Cannot submit an order without product lines."))
            
            # Verificar plazo de entrega por producto
            if order.requested_delivery_date:
                from datetime import date
                
                today = date.today()
                requested_date = order.requested_delivery_date
                
                # Si la fecha solicitada es una cadena, convertirla
                if isinstance(requested_date, str):
                    from datetime import datetime
                    requested_date = datetime.strptime(requested_date, '%Y-%m-%d').date()
                
                days_available = (requested_date - today).days
                insufficient_time_products = []
                
                # Verificar cada producto en las líneas del pedido
                for line in order.order_line_ids:
                    product_delay = line.product_id.sale_delay or 0  # Días de entrega del producto
                    
                    if days_available < product_delay:
                        insufficient_time_products.append({
                            'product_name': line.product_id.name,
                            'required_days': product_delay,
                            'available_days': days_available
                        })
                
                # Si hay productos que no cumplen el plazo, mostrar error
                if insufficient_time_products:
                    error_msg = _("Cannot submit order. The following products do not meet delivery time:\n")
                    for item in insufficient_time_products:
                        error_msg += _("• %s: Requires %s days, only %s days available\n") % (
                            item['product_name'],
                            item['required_days'],
                            item['available_days']
                        )
                    error_msg += _("\nPlease adjust the requested delivery date.")
                    raise UserError(error_msg)
            
            elif not order.requested_delivery_date:
                raise UserError(_("Must specify a requested delivery date."))
            
            order.state = 'submitted'
            order.message_post(body=_("Order submitted for approval."))

    def action_approve(self):
        """Approves the order"""
        for order in self:
            # Verificar stock antes de aprobar
            insufficient_stock = []
            
            for line in order.order_line_ids:
                # Obtener la cantidad disponible del producto
                available_qty = line.product_id.qty_available
                
                if available_qty < line.quantity:
                    insufficient_stock.append({
                        'product_name': line.product_id.name,
                        'requested': line.quantity,
                        'available': available_qty,
                        'missing': line.quantity - available_qty
                    })
            
            # Si hay productos sin stock suficiente, mostrar error
            if insufficient_stock:
                error_msg = _("Cannot approve order. Insufficient stock for the following products:\n")
                for item in insufficient_stock:
                    error_msg += _("• %s: Requested %s, Available %s (Missing %s)\n") % (
                        item['product_name'], 
                        item['requested'], 
                        item['available'], 
                        item['missing']
                    )
                raise UserError(error_msg)
            
            # Si todo está bien, aprobar el pedido
            order.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Date.today(),
            })
            order.message_post(body=_("Order approved by %s.") % self.env.user.name)

    def action_start_transit(self):
        """Marks the order as in transit and deducts stock directly"""
        for order in self:
            if order.state != 'approved':
                raise UserError(_("Only approved orders can be put in transit."))
            
            # VERIFICAR STOCK ANTES DE DESCONTAR
            insufficient_stock = []
            
            for line in order.order_line_ids:
                # Solo verificar productos almacenables
                if line.product_id.detailed_type != 'product':
                    continue  # Saltar servicios y consumibles
                
                available_qty = line.product_id.qty_available
                
                if available_qty < line.quantity:
                    insufficient_stock.append({
                        'product_name': line.product_id.name,
                        'product_code': line.product_id.default_code or '',
                        'requested': line.quantity,
                        'available': available_qty,
                        'missing': line.quantity - available_qty
                    })
            
            # Si hay productos sin stock suficiente, mostrar error
            if insufficient_stock:
                error_msg = _("Cannot put in transit. Insufficient stock for the following products:\n")
                for item in insufficient_stock:
                    error_msg += _("• %s (%s): Requested %s, Available %s (Missing %s)\n") % (
                        item['product_name'],
                        item['product_code'], 
                        item['requested'], 
                        item['available'], 
                        item['missing']
                    )
                raise UserError(error_msg)
            
            products_shipped = []
            
            for line in order.order_line_ids:
                # Solo procesar productos almacenables
                if line.product_id.detailed_type != 'product':
                    continue
                
                product = line.product_id
                
                try:
                    # BUSCAR UBICACIÓN DE STOCK INTERNO 
                    stock_location = self.env['stock.location'].search([
                        ('usage', '=', 'internal'),
                        ('company_id', '=', self.env.company.id)
                    ], limit=1)
                    
                    if not stock_location:
                        # Intentar con la ubicación por defecto
                        stock_location = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
                    
                    if not stock_location:
                        raise UserError(_("No internal stock location found for company %s") % self.env.company.name)
                    
                    # BUSCAR QUANT
                    quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', stock_location.id),
                        ('company_id', '=', self.env.company.id)
                    ], limit=1)
                    
                    if quant:
                        # ACTUALIZAR CANTIDAD EXISTENTE
                        old_qty = quant.quantity
                        new_qty = old_qty - line.quantity
                        
                        quant.sudo().write({'quantity': new_qty})
                        
                        products_shipped.append({
                            'name': product.name,
                            'code': product.default_code or '',
                            'shipped': line.quantity,
                            'old_stock': old_qty,
                            'new_stock': new_qty
                        })
                        
                    else:
                        self.env['stock.quant'].sudo().create({
                            'product_id': product.id,
                            'location_id': stock_location.id,
                            'quantity': -line.quantity,
                            'company_id': self.env.company.id,
                        })
                        
                        products_shipped.append({
                            'name': product.name,
                            'code': product.default_code or '',
                            'shipped': line.quantity,
                            'old_stock': 0,
                            'new_stock': -line.quantity
                        })
                
                except Exception as e:
                    raise UserError(_(
                        "Error updating stock for product %s: %s"
                    ) % (product.name, str(e)))
            
            # ACTUALIZAR ESTADO
            order.write({
                'state': 'in_transit',
                'shipped_date': fields.Date.today(),
            })
            
            # CREAR MENSAJE 
            if products_shipped:
                message_lines = [_("Order in transit. Stock deducted from stock.quant:")]
                for item in products_shipped:
                    code_part = f" ({item['code']})" if item['code'] else ""
                    message_lines.append(
                        f"• {item['name']}{code_part}: {item['old_stock']} → {item['new_stock']} "
                        f"(shipped: {item['shipped']})"
                    )
                
                message = '\n'.join(message_lines)
            else:
                message = _("Order in transit. No physical products to deduct from stock.")
            
            order.message_post(body=message)

    def action_deliver(self):
        """Marks the order as delivered"""
        for order in self:
            order.write({
                'state': 'delivered',
                'delivered_date': fields.Date.today(),
            })
            order.message_post(body=_("Order delivered. Set Payment Due Date manually if needed."))
            if order.production_planning_id:
                order.production_planning_id._check_completion()


    def action_mark_paid(self):
        """Marks the order as paid"""
        for order in self:
            if order.state not in ['delivered', 'overdue']:
                raise UserError(_("Only delivered or overdue orders can be marked as paid. Current state: %s") % order.state)
            
            # Mensaje diferente según el estado anterior
            if order.state == 'overdue':
                message = _("Order marked as paid (was overdue by %s days).") % order.days_overdue
            else:
                message = _("Order marked as paid.")
            
            order.write({
                'state': 'paid',
                'payment_date': fields.Date.today(),
            })
            order.message_post(body=message)

    def action_cancel(self):
        """Cancels the order"""
        for order in self:
            if order.state in ['delivered', 'paid']:
                raise UserError(_("Cannot cancel an order that has been delivered or paid."))
            order.state = 'cancelled'
            order.message_post(body=_("Order cancelled."))

    def action_reset_to_draft(self):
        """Resets the order to draft"""
        for order in self:
            order.state = 'draft'
            order.message_post(body=_("Order reset to draft."))

    @api.constrains('requested_delivery_date', 'order_date')
    def _check_delivery_date(self):
        for order in self:
            if order.requested_delivery_date and order.order_date:
                if order.requested_delivery_date < order.order_date:
                    raise ValidationError(_("The requested delivery date cannot be earlier than the order date."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New Stock Order') == 'New Stock Order':
                vals['name'] = self._generate_order_name(
                    vals.get('franchise_id'), 
                    vals.get('order_date')
                )
        return super().create(vals_list)

    def write(self, vals):
        """Override write to prevent modifications in certain states"""
        # DEFINIR CAMPOS QUE SÍ SE PUEDEN MODIFICAR EN ESTADOS AVANZADOS
        allowed_fields_when_locked = [
            'state',                    # Cambio de estado permitido
            'approved_by',              # Campos de seguimiento
            'approved_date',
            'shipped_date',
            'delivered_date',
            'payment_date',
            'payment_due_date',         # Solo para gestión de pagos
            'notes',                    # Notas adicionales permitidas
            'message_follower_ids',     # Seguidores del chatter
            'message_ids',              # Mensajes del chatter
            'activity_ids',             # Actividades
            'invoice_count',            # Contador de facturas
            'days_overdue',             # Campos computados automáticos
            'outstanding_amount',       # Campos computados automáticos
        ]
        
        # VERIFICAR SI ORDEN ESTÁ BLOQUEADA PARA MODIFICACIONES
        for order in self:
            if order.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                # Obtener campos que se están intentando modificar
                modifying_fields = set(vals.keys()) - set(allowed_fields_when_locked)
                
                if modifying_fields:
                    field_names = ', '.join(modifying_fields)
                    raise UserError(_(
                        "Cannot modify fields '%s' when order '%s' is in state '%s'. "
                        "Order is locked for modifications."
                    ) % (field_names, order.name, order.state))
        
        # VERIFICACIÓN ESPECÍFICA PARA ORDER LINES
        if 'order_line_ids' in vals:
            for order in self:
                if order.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid']:
                    raise UserError(_(
                        "Cannot modify order lines. Order '%s' is in state '%s' and is locked for modifications."
                    ) % (order.name, order.state))
        
        # Regenerar nombre si cambia la franquicia o fecha (solo en draft/submitted)
        if ('franchise_id' in vals or 'order_date' in vals) and not any(
            order.state in ['approved', 'in_transit', 'delivered', 'overdue', 'paid'] 
            for order in self
        ):
            for order in self:
                franchise_id = vals.get('franchise_id', order.franchise_id.id)
                order_date = vals.get('order_date', order.order_date)
                new_name = self._generate_order_name(franchise_id, order_date, exclude_id=order.id)
                vals['name'] = new_name
        
        return super().write(vals)

    def _generate_order_name(self, franchise_id, order_date, exclude_id=None):
        if not franchise_id or not order_date:
            return "New Stock Order"
        
        franchise = self.env['gelroy.franchise'].browse(franchise_id)
        franchise_code = franchise.franchise_code or 'F'
        
        # Buscar pedidos existentes para esa franquicia
        domain = [
            ('franchise_id', '=', franchise_id)
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))
        
        existing_orders = self.search(domain)
        sequence = len(existing_orders) + 1
        
        return f"Order-{franchise_code}-{sequence:03d}"

    def action_create_invoice(self):
        """Creates an invoice for the stock order"""
        for order in self:
            if order.state not in ['delivered', 'in_transit', 'overdue']:
                raise UserError(_("Only delivered, in-transit or overdue orders can be invoiced."))

            # Verificar si ya existe una factura
            existing_invoice = self.env['account.move'].search([
                ('invoice_origin', '=', order.name),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel')
            ], limit=1)
            
            if existing_invoice:
                raise UserError(_("Invoice already exists for this order: %s") % existing_invoice.name)
            
            # Crear factura
            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': order.franchise_id.franchisee_id.id,
                'invoice_date': fields.Date.context_today(self),
                'invoice_origin': order.name,
                'currency_id': order.currency_id.id,
                'invoice_line_ids': [],
            }
            
            # Agregar líneas de factura
            for line in order.order_line_ids:
                invoice_line_vals = {
                    'product_id': line.product_id.id,
                    'name': line.product_id.name,
                    'quantity': line.quantity,
                    'price_unit': line.unit_price,  # Usar unit_price (sin impuestos)
                    'product_uom_id': line.product_id.uom_id.id,
                    # Los impuestos del producto se aplicarán automáticamente
                }
                invoice_vals['invoice_line_ids'].append((0, 0, invoice_line_vals))
            
            # Crear la factura
            invoice = self.env['account.move'].create(invoice_vals)
            
            invoice._compute_tax_totals()
            
            # Refrescar el contador de facturas
            order._compute_invoice_count()
            
            # Mensaje en el pedido
            order.message_post(body=_("Invoice created: %s (Total: %s)") % (invoice.name, invoice.amount_total))
            
            # Abrir la factura
            return {
                'type': 'ir.actions.act_window',
                'name': _('Invoice'),
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': invoice.id,
                'target': 'current',
            }

    def action_view_invoices(self):
        """View invoices related to this stock order"""
        self.ensure_one()
        invoices = self.env['account.move'].search([
            ('invoice_origin', '=', self.name),
            ('move_type', '=', 'out_invoice')
        ])
        
        if len(invoices) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Invoice'),
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Invoices'),
                'view_mode': 'tree,form',
                'res_model': 'account.move',
                'domain': [('id', 'in', invoices.ids)],
                'target': 'current',
            }

    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_invoice_count')

    @api.depends('name')
    def _compute_invoice_count(self):
        for order in self:
            order.invoice_count = self.env['account.move'].search_count([
                ('invoice_origin', '=', order.name),
                ('move_type', '=', 'out_invoice')
            ])

    def unlink(self):
        """Override unlink para borrar facturas en cascada de forma segura"""
        for order in self:
            if order.name and order.name not in ['New Stock Order', '/', False]:
                # Buscar facturas asociadas a esta orden de stock
                associated_invoices = self.env['account.move'].search([
                    ('invoice_origin', '=', order.name),
                    ('move_type', '=', 'out_invoice')
                ])
                
                if associated_invoices:
                    # Separar por estado
                    draft_invoices = associated_invoices.filtered(lambda inv: inv.state == 'draft')
                    cancel_invoices = associated_invoices.filtered(lambda inv: inv.state == 'cancel')
                    confirmed_invoices = associated_invoices.filtered(lambda inv: inv.state in ['posted', 'payment'])
                    
                    # Eliminar borradores y canceladas
                    deletable_invoices = draft_invoices + cancel_invoices
                    if deletable_invoices:
                        try:
                            invoice_names = deletable_invoices.mapped('name')
                            deletable_invoices.unlink()
                            order.message_post(body=_("Invoices deleted in cascade: %s") % ', '.join(invoice_names))
                        except Exception as e:
                            raise ValidationError(_(
                                "Error deleting draft invoices: %s"
                            ) % str(e))
                    
                    # Validar facturas confirmadas/pagadas
                    if confirmed_invoices:
                        # Verificar conciliación
                        reconciled_invoices = confirmed_invoices.filtered(lambda inv: any(
                            line.matched_debit_ids or line.matched_credit_ids 
                            for line in inv.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
                        ))
                        
                        if reconciled_invoices:
                            raise ValidationError(_(
                                "Cannot delete stock order '%s' because it has RECONCILED (paid) invoices: %s. "
                                "You must unreconcile the payments and cancel these invoices manually."
                            ) % (order.name, ', '.join(reconciled_invoices.mapped('name'))))
                        # Facturas confirmadas pero no conciliadas - informar
                        if confirmed_invoices:
                            raise ValidationError(_(
                                "Cannot delete stock order '%s' because it has confirmed invoices: %s. "
                                "You must cancel these invoices manually."
                            ) % (order.name, ', '.join(confirmed_invoices.mapped('name'))))
        return super().unlink()

    @api.depends('payment_due_date', 'outstanding_amount', 'state')
    def _compute_days_overdue(self):
        """Calcular días de retraso"""
        today = fields.Date.context_today(self)
        for order in self:
            if (order.payment_due_date and 
                order.payment_due_date < today and 
                order.outstanding_amount > 0 and
                order.state not in ['paid', 'cancelled']):
                
                order.days_overdue = (today - order.payment_due_date).days
            else:
                order.days_overdue = 0

    @api.depends('total_amount', 'state')
    def _compute_outstanding_amount(self):
        """Calcular monto pendiente de pago"""
        for order in self:
            if order.state == 'paid':
                order.outstanding_amount = 0.0
            else:
                # Buscar facturas pagadas para esta orden
                paid_invoices = self.env['account.move'].search([
                    ('invoice_origin', '=', order.name),
                    ('move_type', '=', 'out_invoice'),
                    ('payment_state', '=', 'paid'),
                    ('state', '=', 'posted')
                ])
                
                paid_amount = sum(paid_invoices.mapped('amount_total'))
                order.outstanding_amount = order.total_amount - paid_amount

    def read(self, fields=None, load='_classic_read'):
        """Override read para verificar overdue al acceder a los datos"""
        result = super().read(fields, load)
        
        # Solo ejecutar si se está leyendo fields relacionados con estado
        if not fields or any(field in fields for field in ['state', 'days_overdue', 'payment_due_date']):
            self._auto_mark_overdue()
        
        return result

    def _auto_mark_overdue(self):
        """Cambiar automáticamente delivered a overdue cuando vencen"""
        today = fields.Date.context_today(self)
        
        overdue_candidates = self.filtered(lambda o: 
            o.state == 'delivered' and 
            o.payment_due_date and 
            o.payment_due_date < today and
            o.outstanding_amount > 0
        )
        
        # Cambiar a overdue automáticamente
        for order in overdue_candidates:
            order.write({'state': 'overdue'})