from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

class ProductionPlanning(models.Model):
    _name = 'gelroy.production.planning'
    _description = 'Production Planning'
    _order = 'planning_date desc, name desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string="Planning Reference", readonly=True, copy=False, default="New Production Planning")
    
    franchise_id = fields.Many2one('gelroy.franchise', string='Franchise', required=True, 
                                   ondelete='cascade', tracking=True)
    franchisee_id = fields.Many2one('res.partner', string='Franchisee', 
                                    related='franchise_id.franchisee_id', store=False, readonly=True)
    
    # Fechas
    planning_date = fields.Date(string='Planning Date', default=fields.Date.context_today, 
                               required=True, tracking=True)
    period_start_date = fields.Date(string='Period Start Date', required=True, tracking=True)
    period_end_date = fields.Date(string='Period End Date', required=True, tracking=True)
    
    # Estado
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('stock_ordered', 'Stock Ordered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Líneas de planificación
    planning_line_ids = fields.One2many('gelroy.production.planning.line', 'planning_id', 
                                       string="Planning Lines", copy=True)
    
    # Campos calculados
    total_recipes = fields.Integer(string='Total Recipes', compute='_compute_totals', store=True)
    total_productions = fields.Float(string='Total productions', compute='_compute_totals', store=True)
    estimated_cost = fields.Monetary(string='Estimated Cost', compute='_compute_totals', store=True)
    
    # Relación con Stock Orders
    stock_order_ids = fields.One2many('gelroy.stock.order', 'production_planning_id', 
                                     string='Stock Orders')
    stock_order_count = fields.Integer(string='Stock Orders', compute='_compute_stock_order_count')
    
    currency_id = fields.Many2one('res.currency', related='franchise_id.currency_id', readonly=True)
    notes = fields.Text(string='Notes')

    def _get_default_name(self):
        """Generar nombre por defecto: plan-mes-secuencia"""
        today = fields.Date.context_today(self)
        month_number = today.month
        year = today.year
        
        # Contar planes existentes en el mes actual
        existing_plans = self.env['gelroy.production.planning'].search_count([
            ('planning_date', '>=', today.replace(day=1)),
            ('planning_date', '<=', today.replace(day=1) + relativedelta(months=1, days=-1))
        ])
        
        sequence = existing_plans + 1
        return f"plan-{month_number}-{sequence}"

    @api.model
    def create(self, vals):
        # Generar nombre basado en mes y secuencia
        if not vals.get('name') or vals.get('name', '').strip() == '':
            planning_date = vals.get('planning_date', fields.Date.context_today(self))
            if isinstance(planning_date, str):
                planning_date = fields.Date.from_string(planning_date)
            
            month_number = planning_date.month
            
            # Contar planes existentes en el mes
            existing_plans = self.search_count([
                ('planning_date', '>=', planning_date.replace(day=1)),
                ('planning_date', '<=', planning_date.replace(day=1) + relativedelta(months=1, days=-1))
            ])
            
            sequence = existing_plans + 1
            vals['name'] = f"plan-{month_number}-{sequence}"
        
        return super().create(vals)

    @api.depends('planning_line_ids.estimated_quantity', 'planning_line_ids.recipe_cost')
    def _compute_totals(self):
        """Calcular totales de recetas, producciones y costos."""
        for planning in self:
            planning.total_recipes = len(planning.planning_line_ids)
            planning.total_productions = sum(line.total_productions for line in planning.planning_line_ids)
            planning.estimated_cost = sum(line.total_cost for line in planning.planning_line_ids)

    @api.depends('stock_order_ids')
    def _compute_stock_order_count(self):
        """Calcular el número de órdenes de stock relacionadas con la planificación"""
        for planning in self:
            planning.stock_order_count = len(planning.stock_order_ids)

    def action_confirm(self):
        """Confirmar la planificación"""
        for planning in self:
            # VALIDAR que no hay líneas de planificación
            if not planning.planning_line_ids:
                raise UserError(_("Cannot confirm planning without recipes."))
            
            # VALIDAR que period_start_date no sea anterior a hoy
            today = fields.Date.context_today(self)
            if planning.period_start_date < today:
                raise UserError(_(
                    "Cannot confirm planning: Period Start Date (%s) cannot be earlier than today (%s). "
                    "Please update the period start date to today or a future date."
                ) % (planning.period_start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')))
            
            # VALIDAR que period_end_date sea posterior a period_start_date
            if planning.period_end_date <= planning.period_start_date:
                raise UserError(_(
                    "Cannot confirm planning: Period End Date (%s) must be after Period Start Date (%s)."
                ) % (planning.period_end_date.strftime('%Y-%m-%d'), planning.period_start_date.strftime('%Y-%m-%d')))
            
            # Confirmar la planificación
            planning.state = 'confirmed'
            planning.message_post(body=_("Production planning confirmed."))

    def action_create_stock_order(self):
        """Crear orden de stock basada en las recetas planificadas"""
        for planning in self:
            if planning.state not in ['confirmed']:
                raise UserError(_("Only confirmed plannings can generate stock orders."))
            
            if planning.stock_order_ids:
                raise UserError(_("Stock order already exists for this planning."))
            
            # Agrupar ingredientes por producto
            ingredient_requirements = {}
            
            for line in planning.planning_line_ids:
                for ingredient in line.recipe_id.ingredient_ids:
                    required_qty = ingredient.quantity * line.estimated_quantity
                    
                    if ingredient.product_id.id in ingredient_requirements:
                        ingredient_requirements[ingredient.product_id.id]['quantity'] += required_qty
                    else:
                        ingredient_requirements[ingredient.product_id.id] = {
                            'product_id': ingredient.product_id.id,
                            'quantity': required_qty,
                            'product': ingredient.product_id
                        }
            
            # Crear Stock Order
            stock_order_vals = {
                'franchise_id': planning.franchise_id.id,
                'production_planning_id': planning.id,
                'order_date': fields.Date.context_today(self),
                'requested_delivery_date': planning.period_start_date,
                'state': 'draft',
                'notes': f'Generated from production planning: {planning.name}',
                'order_line_ids': []
            }
            
            # Crear líneas de stock order
            for req in ingredient_requirements.values():
                line_vals = {
                    'product_id': req['product_id'],
                    'quantity': req['quantity'],
                }
                stock_order_vals['order_line_ids'].append((0, 0, line_vals))
            
            # Crear la orden
            stock_order = self.env['gelroy.stock.order'].create(stock_order_vals)
            
            # Actualizar estado
            planning.state = 'stock_ordered'
            planning.message_post(body=_("Stock order created: %s") % stock_order.name)
            
            # Retornar acción para abrir la orden creada
            return {
                'type': 'ir.actions.act_window',
                'name': _('Stock Order'),
                'view_mode': 'form',
                'res_model': 'gelroy.stock.order',
                'res_id': stock_order.id,
                'target': 'current',
            }

    def action_view_stock_orders(self):
        """Ver órdenes de stock relacionadas"""
        action = self.env.ref('gelroy.stock_order_action').read()[0]
        if len(self.stock_order_ids) > 1:
            action['domain'] = [('id', 'in', self.stock_order_ids.ids)]
        elif self.stock_order_ids:
            action['views'] = [(self.env.ref('gelroy.stock_order_form_view').id, 'form')]
            action['res_id'] = self.stock_order_ids.id
        return action

    @api.model_create_multi
    def create(self, vals_list):
        """Sobrescribir create para generar nombres automáticamente"""
        for vals in vals_list:
            if vals.get('name', 'New Production Planning') == 'New Production Planning':
                vals['name'] = self._generate_planning_name(
                    vals.get('franchise_id'), 
                    vals.get('planning_date')
                )
        return super().create(vals_list)

    def write(self, vals):
        # Regenerar nombre si cambia la franquicia o fecha
        if 'franchise_id' in vals or 'planning_date' in vals:
            for planning in self:
                franchise_id = vals.get('franchise_id', planning.franchise_id.id)
                planning_date = vals.get('planning_date', planning.planning_date)
                new_name = self._generate_planning_name(franchise_id, planning_date, exclude_id=planning.id)
                vals['name'] = new_name
        return super().write(vals)

    def _generate_planning_name(self, franchise_id, planning_date, exclude_id=None):
        """Generar nombre de planificación basado en franquicia y fecha"""
        if not franchise_id or not planning_date:
            return "New Production Planning"
        
        franchise = self.env['gelroy.franchise'].browse(franchise_id)
        franchise_code = franchise.franchise_code or 'F'
        
        # Obtener mes y año de la fecha de planificación
        if isinstance(planning_date, str):
            from datetime import datetime
            planning_date = datetime.strptime(planning_date, '%Y-%m-%d').date()
        
        month_number = planning_date.month
        
        # Buscar planificaciones existentes para esa franquicia en el mismo mes
        domain = [
            ('franchise_id', '=', franchise_id),
            ('planning_date', '>=', planning_date.replace(day=1)),
            ('planning_date', '<=', planning_date.replace(day=1) + relativedelta(months=1, days=-1))
        ]
        if exclude_id:
            domain.append(('id', '!=', exclude_id))
        
        existing_plannings = self.search(domain)
        sequence = len(existing_plannings) + 1
        
        return f"Plan-{franchise_code}-{month_number}-{sequence:03d}"

    def _check_completion(self):
        """Verificar si todas las órdenes de stock están entregadas para marcar como completed"""
        for planning in self:
            if planning.state == 'stock_ordered' and planning.stock_order_ids:
                # Verificar si todas las órdenes están entregadas
                all_delivered = all(order.state == 'delivered' for order in planning.stock_order_ids)
                
                if all_delivered:
                    planning.state = 'completed'
                    planning.message_post(body=_("Production planning completed - all stock orders delivered."))

    def action_mark_completed(self):
        """Marcar manualmente como completado"""
        for planning in self:
            if planning.state in ['stock_ordered']:
                planning.state = 'completed'
                planning.message_post(body=_("Production planning manually marked as completed."))

    def action_cancel(self):
        """Cancelar el planning de producción"""
        for record in self:
            if record.state in ['cancelled', 'completed']:
                raise UserError(_("Cannot cancel a planning that is already cancelled or completed."))
            record.write({'state': 'cancelled'})
        return True
    
    def action_set_to_draft(self):
        """Volver a draft desde cancelled"""
        for record in self:
            if record.state != 'cancelled':
                raise UserError(_("Only cancelled plannings can be set back to draft."))
            record.write({'state': 'draft'})
        return True
    
class ProductionPlanningLine(models.Model):
    _name = 'gelroy.production.planning.line'
    _description = 'Production Planning Line'
    _order = 'sequence, recipe_id'

    planning_id = fields.Many2one('gelroy.production.planning', string='Planning', 
                                 required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    recipe_id = fields.Many2one('gelroy.recipe', string='Recipe', required=True)
    estimated_quantity = fields.Float(string='Estimated Quantity', required=True, default=1.0)
    
    # Campos calculados
    recipe_production_size = fields.Float(related='recipe_id.production_size', readonly=True)
    total_productions = fields.Float(string='Total productions', compute='_compute_totals', store=True)
    recipe_cost = fields.Monetary(related='recipe_id.ingredient_cost', readonly=True)
    total_cost = fields.Monetary(string='Total Cost', compute='_compute_totals', store=True)
    
    currency_id = fields.Many2one('res.currency', related='planning_id.currency_id', readonly=True)
    notes = fields.Text(string='Notes')

    @api.depends('estimated_quantity', 'recipe_production_size', 'recipe_cost')
    def _compute_totals(self):
        """Calcular totales de producciones y costos."""
        for line in self:
            line.total_productions = line.estimated_quantity * line.recipe_production_size
            line.total_cost = line.estimated_quantity * line.recipe_cost

    @api.constrains('estimated_quantity')
    def _check_estimated_quantity(self):
        """Verificar que la cantidad estimada sea mayor que cero."""
        for line in self:
            if line.estimated_quantity <= 0:
                raise ValidationError(_("Estimated quantity must be greater than zero."))