# -*- coding: utf-8 -*-

from odoo import models, fields, api

class RoyaltyPayment(models.Model):
    _name = 'gelroy.royalty.payment'
    _description = 'Franchise Royalty Payment'
    _order = 'payment_due_date desc'

    name = fields.Char(string="Payment Reference", compute='_compute_name', store=True)

    franchise_id = fields.Many2one('gelroy.franchise', string='Franchise', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', string='Currency', related='franchise_id.currency_id', store=True) 
    calculation_date = fields.Date(string='Calculation Date', default=fields.Date.context_today, required=True)
    period_start_date = fields.Date(string='Period Start Date', required=True)
    period_end_date = fields.Date(string='Period End Date', required=True)
    
    
    royalty_rate = fields.Float(string='Royalty Rate (%)', related='franchise_id.royalty_fee_percentage', store=True, readonly=True)
    calculated_amount = fields.Monetary(string='Calculated Royalty Amount')
    
    payment_due_date = fields.Date(string='Due Date')
    payment_date = fields.Date(string='Payment Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('invoiced', 'Invoiced'), 
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ], string='Status', default='draft', required=True)
    
    #invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True) # dependencia 'account'
    notes = fields.Text(string='Notes')

    # Crea el nombre del pago basado en el franquiciado y la fecha de fin del periodo.
    @api.depends('franchise_id', 'period_end_date')
    def _compute_name(self):
        for payment in self:
            name = ("Payment") 
            if payment.franchise_id and payment.period_end_date:
                name = f"{payment.franchise_id.name} - {payment.period_end_date.strftime('%m/%Y')}"
            payment.name = name