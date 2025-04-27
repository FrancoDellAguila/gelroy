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
             raise UserError(_("No se puede calcular la regalía para la franquicia '%s' sin una moneda definida.") % self.name)

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
        # Asegura que la acción se ejecute sobre un único registro.
        self.ensure_one()
        # Devuelve una acción de ventana para mostrar los pagos de regalía de esta franquicia.
        return {
            'name': _('Pagos de Regalía'), # Título de la vista
            'type': 'ir.actions.act_window', # Tipo de acción
            'res_model': 'gelroy.royalty.payment', # Modelo a mostrar
            'view_mode': 'tree,form', # Vistas disponibles (lista y formulario)
            'domain': [('franchise_id', '=', self.id)], # Filtro para mostrar solo pagos de esta franquicia
            'context': {'default_franchise_id': self.id} # Contexto para pre-rellenar la franquicia al crear nuevo pago
        }

