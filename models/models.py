# -*- coding: utf-8 -*-

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
    street2 = fields.Char('Street2')
    zip = fields.Char('Zip', change_default=True)
    city = fields.Char('City')
    state_id = fields.Many2one("res.country.state", string='State', domain="[('country_id', '=?', country_id)]") 
    country_id = fields.Many2one('res.country', string='Country')
    phone = fields.Char('Phone')
    mobile = fields.Char('Mobile')
    email = fields.Char('Email')

    image = fields.Binary('Logo/Image')
    active = fields.Boolean("Active", default=True, help="Activate/Deactivate franchise record", tracking=True)

    franchise_type = fields.Selection([
        ("restaurant", "Restaurant"),
        ("retail", "Retail"),
        ("service", "Service"),
        ("other", "Other")
    ], string="Type", help="Type of Franchise", required=True, default="other", tracking=True) 

    notes = fields.Text("Notes", help="Additional internal notes")
    description = fields.Html('Description')

    opening_date = fields.Date(string="Opening Date", tracking=True) 
    franchisee_id = fields.Many2one('res.partner', string="Franchisee", help="Contact person or company operating the franchise", tracking=True)
    contract_start_date = fields.Date(string="Contract Start Date", tracking=True) 
    contract_end_date = fields.Date(string="Contract End Date", tracking=True) 
    royalty_fee_percentage = fields.Float(string="Royalty Fee (%)", digits=(5, 2), tracking=True)
    currency_id = fields.Many2one('res.currency', related='franchisee_id.currency_id', store=True, readonly=False, 
                                  string="Currency", help="The currency for financial fields related to this franchise.") 

    contract_duration_months = fields.Integer(string="Contract Duration (Months)", compute='_compute_contract_duration', store=True)

    royalty_payment_ids = fields.One2many('gelroy.royalty.payment', 'franchise_id', string="Royalty Payments") 
    royalty_payment_count = fields.Integer(compute='_compute_royalty_payment_count', string="Royalty Payments Count")

    _sql_constraints = [
        ('franchise_code_unique', 'unique(franchise_code)', 'Franchise Code must be unique!')
    ]

    @api.depends('contract_start_date', 'contract_end_date')
    def _compute_contract_duration(self):
        for rec in self:
            if rec.contract_start_date and rec.contract_end_date and rec.contract_end_date > rec.contract_start_date:
                delta = relativedelta(rec.contract_end_date, rec.contract_start_date)
                rec.contract_duration_months = delta.years * 12 + delta.months
            else:
                rec.contract_duration_months = 0

    @api.depends('royalty_payment_ids')
    def _compute_royalty_payment_count(self):
        for franchise in self:
            franchise.royalty_payment_count = len(franchise.royalty_payment_ids)

    def _calculate_and_create_royalty_payment(self, period_start, period_end, sales_basis):
        """
        Calculates royalty for a given period and basis, then creates a Royalty Payment record.
        Called by a scheduled action.

        :param date period_start: Start date of the calculation period.
        :param date period_end: End date of the calculation period.
        :param float sales_basis: The amount (e.g., sales) on which the royalty is calculated.
        :return: The created gelroy.royalty.payment record or None.
        """
        self.ensure_one()

        if not self.active:
            return None

        if self.royalty_fee_percentage <= 0:
            return None

        if not self.currency_id:
             raise UserError(_("Cannot calculate royalty for franchise '%s' without a defined currency.") % self.name)

        calculated_amount = (sales_basis * self.royalty_fee_percentage) / 100.0

        due_date = period_end + relativedelta(days=15)

        payment_vals = {
            'franchise_id': self.id,
            'calculation_date': fields.Date.context_today(self),
            'period_start_date': period_start,
            'period_end_date': period_end,
            'royalty_rate': self.royalty_fee_percentage,
            'calculated_amount': calculated_amount,
            'payment_due_date': due_date,
            'state': 'calculated',
            'currency_id': self.currency_id.id,
        }

        royalty_payment = self.env['gelroy.royalty.payment'].create(payment_vals)
        self.message_post(body=_("Royalty payment calculated for period %s to %s.") % (period_start, period_end))

        return royalty_payment

    def action_view_royalty_payments(self):
        self.ensure_one()
        return {
            'name': _('Royalty Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'gelroy.royalty.payment',
            'view_mode': 'tree,form',
            'domain': [('franchise_id', '=', self.id)],
            'context': {'default_franchise_id': self.id}
        }

