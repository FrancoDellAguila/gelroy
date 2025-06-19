from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

class RoyaltyPayment(models.Model):
    _name = 'gelroy.royalty.payment'
    _description = 'Franchise Royalty Payment'
    _order = 'payment_due_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Payment Reference", compute='_compute_name', store=True)

    franchise_id = fields.Many2one('gelroy.franchise', string='Franchise', required=True, 
                                   ondelete='cascade', tracking=True)
    franchisee_id = fields.Many2one('res.partner', string='Franchisee', 
                                    related='franchise_id.franchisee_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  related='franchise_id.currency_id', store=True, readonly=True)
    
    # Fechas y períodos
    calculation_date = fields.Date(string='Calculation Date', default=fields.Date.today, 
                                   required=True, tracking=True)
    period_start_date = fields.Date(string='Period Start Date', required=True, tracking=True)
    period_end_date = fields.Date(string='Period End Date', required=True, tracking=True)
    payment_due_date = fields.Date(string='Due Date', compute='_compute_payment_due_date', 
                                   store=True, tracking=True)
    payment_date = fields.Date(string='Payment Date', tracking=True)
    
    # Cálculos financieros
    period_revenue = fields.Monetary(string='Period Revenue', required=True, tracking=True)
    royalty_rate = fields.Float(string='Royalty Rate (%)', 
                                related='franchise_id.royalty_fee_percentage', 
                                store=True, readonly=True)
    calculated_amount = fields.Monetary(string='Calculated Royalty Amount', 
                                        compute='_compute_calculated_amount', 
                                        store=True, tracking=True)
    paid_amount = fields.Monetary(string='Paid Amount', tracking=True)
    outstanding_amount = fields.Monetary(string='Outstanding Amount', 
                                         compute='_compute_outstanding_amount', store=True)
    
    # Estados y control
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('confirmed', 'Confirmed'),
        ('overdue', 'Overdue'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    days_overdue = fields.Integer(string='Days Overdue', compute='_compute_days_overdue', store=True)
    
    # Información adicional
    notes = fields.Text(string='Additional Notes')
    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_invoice_count')

    @api.depends('franchise_id', 'period_end_date')
    def _compute_name(self):
        """Genera automáticamente el nombre del pago con formato ROY-CODIGO-YYYY-MM"""
        for payment in self:
            if payment.franchise_id and payment.period_end_date:
                franchise_code = payment.franchise_id.franchise_code or f"M{payment.franchise_id.id}"
                period_str = payment.period_end_date.strftime('%Y-%m')
                payment.name = f"ROY-{franchise_code}-{period_str}"
            else:
                payment.name = "New Royalty Payment"

    @api.depends('period_end_date', 'franchise_id.royalty_payment_terms')
    def _compute_payment_due_date(self):
        """Genera automáticamente la fecha de vencimiento del pago"""
        for payment in self:
            if payment.period_end_date and payment.franchise_id.royalty_payment_terms:
                payment.payment_due_date = payment.period_end_date + timedelta(days=payment.franchise_id.royalty_payment_terms)
            else:
                payment.payment_due_date = False

    @api.depends('period_revenue', 'royalty_rate')
    def _compute_calculated_amount(self):
        """Genera automáticamente el monto calculado del pago de regalías"""
        for payment in self:
            if payment.period_revenue and payment.royalty_rate:
                payment.calculated_amount = payment.period_revenue * (payment.royalty_rate / 100)
            else:
                payment.calculated_amount = 0.0

    @api.depends('calculated_amount', 'paid_amount')
    def _compute_outstanding_amount(self):
        """Genera automáticamente el monto pendiente del pago de regalías"""
        for payment in self:
            payment.outstanding_amount = payment.calculated_amount - payment.paid_amount

    @api.depends('payment_due_date', 'state')
    def _compute_days_overdue(self):
        """Calcula los días de retraso del pago"""
        today = fields.Date.today()
        for payment in self:
            if payment.payment_due_date and payment.payment_due_date < today:
                payment.days_overdue = (today - payment.payment_due_date).days
                if payment.state == 'confirmed':
                    payment.state = 'overdue'
            else:
                payment.days_overdue = 0

    @api.depends('name')
    def _compute_invoice_count(self):
        """Cuenta las facturas asociadas a este pago de regalías"""
        for payment in self:
            if payment.name and payment.name not in ['New Royalty Payment', '/', False]:
                payment.invoice_count = self.env['account.move'].search_count([
                    ('invoice_origin', '=', payment.name),
                    ('move_type', '=', 'out_invoice'),
                    ('partner_id', '=', payment.franchisee_id.id)
                ])
            else:
                payment.invoice_count = 0

    def action_calculate(self):
        """Calcula el monto de regalías basado en los ingresos del período y la tasa de regalías"""
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be calculated.")
            if not payment.period_revenue or payment.period_revenue <= 0:
                raise UserError("Period revenue must be greater than 0 to calculate royalties.")
            payment.state = 'calculated'

    def action_confirm(self):
        """Confirma el pago de regalías, asegurando que esté en estado 'calculated'"""
        for payment in self:
            if payment.state != 'calculated':
                raise UserError("Only calculated payments can be confirmed.")
            payment.state = 'confirmed'

    def action_register_payment(self):
        """Registra el pago de regalías, cambiando el estado a 'paid' y actualizando los montos"""
        for payment in self:
            if payment.state not in ['confirmed', 'overdue']:
                raise UserError("Only confirmed or overdue payments can be registered.")
            if payment.state == 'paid':
                raise UserError("This payment has already been registered.")
            
            payment.write({
                'state': 'paid',
                'paid_amount': payment.calculated_amount,
                'payment_date': fields.Date.today()
            })

    def action_cancel(self):
        """Cancela el pago de regalías, asegurando que no esté en estado 'paid'"""
        for payment in self:
            if payment.state == 'paid':
                raise UserError("A payment that has already been registered cannot be canceled.")
            payment.state = 'cancelled'

    def action_reset_to_draft(self):
        """Reinicia el pago de regalías a estado 'draft', permitiendo su recalculo"""
        for payment in self:
            payment.write({
                'state': 'draft',
                'paid_amount': 0.0,
                'payment_date': False,
            })

    def action_create_invoice(self):
        """Crea una factura de cliente para el pago de regalías"""
        for payment in self:
            if payment.state not in ['confirmed', 'paid', 'overdue']:	
                raise UserError("Only confirmed, overdue or paid royalty payments can be invoiced.")
            
            if payment.calculated_amount <= 0:
                raise UserError("Calculated amount must be greater than zero.")
            
            existing_invoice = self.env['account.move'].search([
                ('invoice_origin', '=', payment.name),
                ('move_type', '=', 'out_invoice'),
                ('partner_id', '=', payment.franchisee_id.id),
                ('state', '!=', 'cancel')
            ], limit=1)
            
            if existing_invoice:
                raise UserError(f"Invoice already exists for this royalty payment: {existing_invoice.name}")
            
            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': payment.franchisee_id.id,
                'invoice_date': fields.Date.today(),
                'invoice_origin': payment.name,
                'currency_id': payment.currency_id.id,
                'invoice_line_ids': [(0, 0, {
                    'name': f'Royalty Payment - {payment.franchise_id.name} ({payment.period_start_date.strftime("%b %Y")})',
                    'price_unit': payment.calculated_amount,
                    'quantity': 1,
                })],
            }
            
            invoice = self.env['account.move'].create(invoice_vals)
            
            return {
                'type': 'ir.actions.act_window',
                'name': 'Royalty Invoice',
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': invoice.id,
                'target': 'current',
            }

    def action_view_invoices(self):
        """Muestra las facturas asociadas a este pago de regalías"""
        self.ensure_one()
        invoices = self.env['account.move'].search([
            ('invoice_origin', '=', self.name),
            ('move_type', '=', 'out_invoice')
        ])
        
        if len(invoices) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Royalty Invoice',
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Royalty Invoices',
                'view_mode': 'tree,form',
                'res_model': 'account.move',
                'domain': [('id', 'in', invoices.ids)],
                'target': 'current',
            }

    @api.constrains('period_start_date', 'period_end_date')
    def _check_period_dates(self):
        """Verifica que las fechas de inicio y fin del período sean válidas"""
        for payment in self:
            if payment.period_start_date and payment.period_end_date:
                if payment.period_start_date >= payment.period_end_date:
                    raise ValidationError("The period end date must be after the start date.")

    @api.constrains('period_revenue')
    def _check_revenue(self):
        """Verifica que los ingresos del período no sean negativos"""
        for payment in self:
            if payment.period_revenue < 0:
                raise ValidationError("The period revenue cannot be negative.")

    @api.constrains('franchise_id', 'period_end_date')
    def _check_unique_monthly_payment(self):
        """Verifica que no haya pagos de regalías duplicados para el mismo mes y franquicia"""
        for payment in self:
            if payment.franchise_id and payment.period_end_date:
                month_start = payment.period_end_date.replace(day=1)
                month_end = month_start + relativedelta(months=1)
                
                existing = self.search([
                    ('id', '!=', payment.id),
                    ('franchise_id', '=', payment.franchise_id.id),
                    ('period_end_date', '>=', month_start),
                    ('period_end_date', '<', month_end)
                ])
                
                if existing:
                    period_str = payment.period_end_date.strftime('%Y-%m')
                    raise ValidationError(
                        f"A royalty calculation already exists for this franchise in {period_str}. "
                        "Only one calculation per month is allowed."
                    )

    def unlink(self):
        """Sobrescribe el método unlink para validar facturas asociadas antes de eliminar pagos de regalías"""
        for payment in self:
            if payment.name and payment.name not in ['New Royalty Payment', '/', False]:
                associated_invoices = self.env['account.move'].search([
                    ('invoice_origin', '=', payment.name),
                    ('move_type', '=', 'out_invoice'),
                    ('partner_id', '=', payment.franchisee_id.id)
                ])
                
                if associated_invoices:
                    # CORRECCIÓN: Separar antes de eliminar
                    draft_invoices = associated_invoices.filtered(lambda inv: inv.state == 'draft')
                    confirmed_invoices = associated_invoices.filtered(lambda inv: inv.state in ['posted', 'payment'])
                    
                    # Validar facturas confirmadas ANTES de eliminar borradores
                    if confirmed_invoices:
                        raise ValidationError(
                            f"Cannot delete the royalty payment '{payment.name}' because it has confirmed invoices: "
                            f"{', '.join(confirmed_invoices.mapped('name'))}. "
                            "You must cancel these invoices manually first."
                        )
                    
                    # Eliminar facturas borrador solo si no hay confirmadas
                    if draft_invoices:
                        draft_invoices.unlink()
    
        return super().unlink()

    @api.model
    def check_overdue_payments(self):
        """Verifica y actualiza el estado de los pagos de regalías que están atrasados."""
        today = fields.Date.today()
        
        overdue_candidates = self.search([
            ('state', '=', 'confirmed'),
            ('payment_due_date', '<', today),
            ('outstanding_amount', '>', 0)
        ])
        
        for payment in overdue_candidates:
            payment.write({'state': 'overdue'})
        
        return len(overdue_candidates)

    def read(self, fields_list=None, load='_classic_read'):
        """Marcar como overdue los pagos al leer registros."""
        result = super().read(fields_list, load)
        
        # Solo verificar overdue si no estamos en proceso de instalación
        if not self.env.context.get('install_mode'):
            from datetime import date
            today = date.today()
            for payment in self:
                if (payment.state == 'confirmed' and 
                    payment.payment_due_date and 
                    payment.payment_due_date < today):
                    payment.with_context(skip_overdue_check=True).write({'state': 'overdue'})
        
        return result




