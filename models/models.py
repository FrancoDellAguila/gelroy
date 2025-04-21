# -*- coding: utf-8 -*-

from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class Franchise(models.Model): 
    _name = "gelroy.franchise"
    _description = "Franchise Information" 
    _order = "name" # Order by name by default
    _rec_name = 'name' # Use name as the default display name

    name = fields.Char(string="Franchise Name", required=True)
    franchise_code = fields.Char(string="Code", required=True, copy=False) 
    street = fields.Char('Street')
    street2 = fields.Char('Street2')
    zip = fields.Char('Zip', change_default=True)
    city = fields.Char('City')
    state_id = fields.Many2one("res.country.state", string='State')
    country_id = fields.Many2one('res.country', string='Country')
    phone = fields.Char('Phone')
    mobile = fields.Char('Mobile') 
    email = fields.Char('Email')

    image = fields.Binary('Logo/Image') 
    active = fields.Boolean("Active", default=True, help="Activate/Deactivate franchise record")

    franchise_type = fields.Selection([
        ("restaurant", "Restaurant"),
        ("retail", "Retail"),
        ("service", "Service"),
        ("other", "Other")
    ], string="Type", help="Type of Franchise", required=True, default="other")

    notes = fields.Text("Notes", help="Additional internal notes")
    description = fields.Html('Description') 


    opening_date = fields.Date(string="Opening Date")
    franchisee_id = fields.Many2one('res.partner', string="Franchisee", help="Contact person or company operating the franchise")
    contract_start_date = fields.Date(string="Contract Start Date")
    contract_end_date = fields.Date(string="Contract End Date")
    royalty_fee_percentage = fields.Float(string="Royalty Fee (%)", digits=(5, 2)) 

    contract_duration_months = fields.Integer(string="Contract Duration (Months)", compute='_compute_contract_duration', store=True)

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

