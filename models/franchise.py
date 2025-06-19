from odoo import models, fields, api, _ 
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta

class Franchise(models.Model):
    _name = "gelroy.franchise"
    _description = "Franchise Information"
    _order = "name" 
    _inherit = ['mail.thread', 'mail.activity.mixin'] 
    _rec_name = 'name' 

    name = fields.Char(string="Franchise Name", required=True, tracking=True) 
    franchise_code = fields.Char(string="Code", required=True, copy=False, tracking=True) 
    street = fields.Char('Street')
    zip = fields.Char('Zip', change_default=True)
    city = fields.Char('City')
    state_id = fields.Many2one("res.country.state", string='State', domain="[('country_id', '=?', country_id)]") 
    country_id = fields.Many2one('res.country', string='Country')
    phone = fields.Char('Phone')
    email = fields.Char('Email')

    _sql_constraints = [
        ('unique_franchise_code', 'unique(franchise_code)', 'The franchise code must be unique.')
    ]

    image = fields.Binary('Logo/Image')
    active = fields.Boolean("Active", default=True, help="Activate/Deactivate franchise record", tracking=True)

    franchise_type = fields.Selection([
        ('restaurant', 'Restaurant'),
        ('coffee_shop', 'Coffee Shop'),
        ('ice_cream_parlor', 'Ice Cream Parlor'),
        ('fast_food', 'Fast Food'),
        ('pizzeria', 'Pizzeria'),
        ('bakery_pastry', 'Bakery / Pastry Shop')
    ], string="Type", help="Type of Franchise", required=True, default="restaurant", tracking=True) 

    notes = fields.Text("Notes", help="Additional internal notes")

    opening_date = fields.Date(string="Opening Date", tracking=True) 
    franchisee_id = fields.Many2one('res.partner', string="Franchisee", help="Contact person or company operating the franchise", tracking=True)
    contract_start_date = fields.Date(string="Contract Start Date", tracking=True)
    contract_end_date = fields.Date(string="Contract End Date", tracking=True)
    contract_duration_months = fields.Integer(string="Contract Duration (Months)", compute='_compute_contract_duration', store=True, tracking=True)
    royalty_fee_percentage = fields.Float(string="Royalty Fee %", digits=(5, 2), help="Percentage of revenue to be paid as royalty", tracking=True)
    
    monthly_revenue = fields.Monetary(string='Monthly Revenue', help="Actual revenue for royalty calculation")
    last_revenue_update = fields.Date(string='Last Revenue Update')
    
    royalty_calculation_day = fields.Integer(string='Royalty Calculation Day', default=1, 
                                           help="Day of month when royalties are calculated (1-28)")
    royalty_payment_terms = fields.Integer(string='Payment Terms (Days)', default=30,
                                         help="Days after calculation when payment is due")
    
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id,
                                  help="Currency used for this franchise")
    
    # Relaciones
    royalty_payment_ids = fields.One2many('gelroy.royalty.payment', 'franchise_id', string="Royalty Payments") 
    royalty_payment_count = fields.Integer(compute='_compute_royalty_payment_count', string="Royalty Payments Count")

    # campos para pedidos de stock
    stock_order_ids = fields.One2many('gelroy.stock.order', 'franchise_id', string="Stock Orders")
    stock_order_count = fields.Integer(compute='_compute_stock_order_count', string="Stock Orders Count")

    # Campos financieros calculados
    total_royalties_due = fields.Monetary(string='Total Royalties Due', 
                                         compute='_compute_financial_summary', store=True)
    total_royalties_paid = fields.Monetary(string='Total Royalties Paid', 
                                          compute='_compute_financial_summary', store=True)
    outstanding_royalties = fields.Monetary(string='Outstanding Royalties', 
                                           compute='_compute_financial_summary', store=True)
    
    # Deuda de pedidos de mercadería
    outstanding_stock_orders = fields.Monetary(string='Outstanding Stock Orders', 
                                              compute='_compute_financial_summary', store=True)
    
    # Deuda total combinada
    total_outstanding_debt = fields.Monetary(string='Total Debt', 
                                            compute='_compute_financial_summary', store=True)
    
    # Contadores
    pending_royalty_payments = fields.Integer(string='Pending Royalty Payments', 
                                             compute='_compute_financial_summary', store=True)
    pending_stock_orders_count = fields.Integer(string='Pending Stock Orders', 
                                               compute='_compute_financial_summary', store=True)

    _sql_constraints = [
        ('franchise_code_unique', 'unique(franchise_code)', 'Franchise Code must be unique!')
    ]

    # Calcula la duración del contrato en meses.
    @api.depends('contract_start_date', 'contract_end_date')
    def _compute_contract_duration(self):
        for rec in self:
            # Verifica que ambas fechas existan y la fecha de fin sea posterior a la de inicio.
            if rec.contract_start_date and rec.contract_end_date and rec.contract_end_date > rec.contract_start_date:
                delta = relativedelta(rec.contract_end_date, rec.contract_start_date)
                # Convierte la diferencia a meses (años * 12 + meses).
                rec.contract_duration_months = delta.years * 12 + delta.months
            else:
                rec.contract_duration_months = 0

    # Calcula el número de registros de pago de regalías asociados a esta franquicia.
    @api.depends('royalty_payment_ids')
    def _compute_royalty_payment_count(self):
        for franchise in self:
            # Asigna la cantidad de elementos en la relación One2many.
            franchise.royalty_payment_count = len(franchise.royalty_payment_ids)

    # método para contar pedidos de stock
    @api.depends('stock_order_ids')
    def _compute_stock_order_count(self):
        for franchise in self:
            franchise.stock_order_count = len(franchise.stock_order_ids)

    def _calculate_and_create_royalty_payment(self, period_start, period_end, sales_basis):
        """
        Calcula la regalía para un período y base dados, luego crea un registro de Pago de Regalía.
        Llamado por una acción planificada.

        :param date period_start: Fecha de inicio del período de cálculo.
        :param date period_end: Fecha de fin del período de cálculo.
        :param float sales_basis: El monto (ej., ventas) sobre el cual se calcula la regalía.
        :return: El registro gelroy.royalty.payment creado o None.
        """
        # Asegura que el método se ejecute sobre un único registro.
        self.ensure_one()

        # Si la franquicia no está activa, no calcula nada.
        if not self.active:
            return None

        # Si el porcentaje de regalía es cero o negativo, no calcula nada.
        if self.royalty_fee_percentage <= 0:
            return None

        # Si la franquicia no tiene una moneda definida, lanza un error.
        if not self.currency_id:
            raise UserError(_("Cannot calculate royalty for franchise '%s' without a defined currency.") % self.name)

        # Calcula el monto de la regalía.
        calculated_amount = (sales_basis * self.royalty_fee_percentage) / 100.0

        # Calcula la fecha de vencimiento (ej. 15 días después del fin de período).
        due_date = period_end + relativedelta(days=15)

        # Prepara los valores para crear el nuevo registro de pago.
        payment_vals = {
            'franchise_id': self.id,
            'calculation_date': fields.Date.context_today(self), # Fecha actual
            'period_start_date': period_start,
            'period_end_date': period_end,
            'royalty_rate': self.royalty_fee_percentage, # Tasa de regalía usada
            'calculated_amount': calculated_amount, # Monto calculado
            'payment_due_date': due_date, # Fecha de vencimiento
            'state': 'calculated', # Estado inicial
            'currency_id': self.currency_id.id, # Moneda
        }

        # Crea el registro de pago de regalía.
        royalty_payment = self.env['gelroy.royalty.payment'].create(payment_vals)
        # Registra un mensaje en el chatter de la franquicia.
        self.message_post(body=_("Pago de regalía calculado para el período %s a %s.") % (period_start, period_end))

        # Devuelve el registro creado.
        return royalty_payment

    def action_view_royalty_payments(self):
        """Ver todos los pagos de regalías de esta franquicia"""
        return {
            'name': f'Royalty Payments - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'gelroy.royalty.payment',
            'view_mode': 'tree,form',
            'domain': [('franchise_id', '=', self.id)],
            'context': {
                'default_franchise_id': self.id,
                'search_default_group_by_state': 1, 
            },
        }

    def action_view_pending_stock_orders(self):
        """Ver todos los pedidos de stock pendientes de pago"""
        return {
            'name': f'Pending Stock Orders - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'gelroy.stock.order',
            'view_mode': 'tree,form',
            'domain': [
                ('franchise_id', '=', self.id),
                ('state', '=', 'delivered')  # Entregados pero no pagados
            ],
            'context': {'default_franchise_id': self.id},
        }

    def action_view_stock_orders(self):
        """Ver todos los pedidos de stock de esta franquicia"""
        return {
            'name': f'Stock Orders - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'gelroy.stock.order',
            'view_mode': 'tree,form',
            'domain': [('franchise_id', '=', self.id)],
            'context': {
                'default_franchise_id': self.id,
                'search_default_group_by_state': 1,
            },
        }

    def action_view_all_debts(self):
        """Ver un resumen consolidado de todas las deudas"""
        # Aquí podrías crear una vista especial o dashboard
        pass

    def action_franchisee_dashboard(self):
        """Panel específico para franquiciados de sus pedidos de stock."""
        self.ensure_one()
        return {
            'name': _('My Franchise Panel'),
            'type': 'ir.actions.act_window',
            'res_model': 'gelroy.stock.order',
            'view_mode': 'kanban,tree,form',
            'domain': [('franchise_id', '=', self.id)],
            'context': {
                'default_franchise_id': self.id,
                'search_default_my_orders': 1,
            }
        }

    @api.depends('royalty_payment_ids.state', 'royalty_payment_ids.calculated_amount', 
                 'royalty_payment_ids.paid_amount', 'stock_order_ids.state', 'stock_order_ids.total_amount')
    def _compute_financial_summary(self):
        for franchise in self:
            # PEDIDOS DE STOCK
            stock_orders = franchise.stock_order_ids
            
            # Deuda de pedidos entregados pero no pagados
            delivered_unpaid_orders = stock_orders.filtered(
                lambda o: o.state == 'delivered'
            )
            outstanding_stock_orders = sum(delivered_unpaid_orders.mapped('total_amount'))
            
            # Contador de pedidos pendientes de pago
            pending_stock_count = len(delivered_unpaid_orders)
            
            # REGALÍAS
            royalty_payments = franchise.royalty_payment_ids
            
            # Totales de regalías
            total_royalties_due = sum(payment.calculated_amount for payment in royalty_payments 
                                     if payment.state in ['calculated', 'confirmed', 'overdue'])
            total_royalties_paid = sum(payment.paid_amount for payment in royalty_payments)
            outstanding_royalties = sum(payment.outstanding_amount for payment in royalty_payments 
                                       if payment.state != 'paid')
            
            # Contadores de regalías
            pending_royalty_count = len(royalty_payments.filtered(
                lambda p: p.state in ['calculated', 'confirmed', 'overdue']
            ))
            
            # TOTALES COMBINADOS
            total_debt = outstanding_royalties + outstanding_stock_orders
            
            franchise.update({
                'total_royalties_due': total_royalties_due,
                'total_royalties_paid': total_royalties_paid,
                'outstanding_royalties': outstanding_royalties,
                'outstanding_stock_orders': outstanding_stock_orders,
                'total_outstanding_debt': total_debt,
                'pending_royalty_payments': pending_royalty_count,
                'pending_stock_orders_count': pending_stock_count,
            })

