from odoo import models, fields, api
from datetime import date,datetime, timedelta
from dateutil.relativedelta import relativedelta

# MODELO 1: DASHBOARD FILTRABLE (SOLO CAMPOS FILTRABLES)
class FranchiseDashboard(models.TransientModel):
    _name = 'gelroy.franchise.dashboard'
    _description = 'Franchise Dashboard with KPIs'

    # FILTROS DEL DASHBOARD 
    franchise_id = fields.Many2one('gelroy.franchise', string='Franchise', help='Filter by specific franchise')
    date_from = fields.Date(string='From Date', default=lambda self: fields.Date.today().replace(day=1), help='Start date for filtering')
    date_to = fields.Date(string='To Date', default=fields.Date.today, help='End date for filtering')
    
    # CAMPOS KPI FILTRABLES     
    # Regalías KPIs 
    total_royalties_calculated = fields.Monetary(string='Calculated Royalties', compute='_compute_royalty_kpis', help='Total royalties calculated in the period')
    total_royalties_paid = fields.Monetary(string='Paid Royalties', compute='_compute_royalty_kpis', help='Total royalties paid in the period')
    total_royalties_outstanding = fields.Monetary(string='Outstanding Royalties', compute='_compute_royalty_kpis', help='Pending royalties to be paid')
    royalty_collection_rate = fields.Float(string='Royalty Collection Rate', compute='_compute_royalty_kpis', help='Percentage of collected royalties')
    overdue_royalty_payments_count = fields.Integer(string='Overdue Royalties Count', compute='_compute_royalty_kpis', help='Number of overdue payments')
    overdue_royalty_payments_amount = fields.Monetary(string='Overdue Royalties Amount', compute='_compute_royalty_kpis', help='Amount of overdue royalties')
    average_royalty_per_franchise = fields.Monetary(string='Average Royalty per Active Franchise', compute='_compute_royalty_kpis', help='Average royalty per active franchise')
    
    # Stock KPIs 
    total_stock_orders_value = fields.Monetary(string='Total S.O. Amount', compute='_compute_stock_kpis', help='Total value of stock orders')
    total_stock_orders_count = fields.Integer(string='Total S.O. Count', compute='_compute_stock_kpis', help='Total number of stock orders')
    average_order_value = fields.Monetary(string='Average S.O. Value', compute='_compute_stock_kpis', help='Average value per stock order')
    stock_debt_total = fields.Monetary(string='Outstanding S.O. Amount', compute='_compute_stock_kpis', help='Total debt from delivered but unpaid orders')
    stock_debt_orders_count = fields.Integer(string='Outstanding Stock Orders', compute='_compute_stock_kpis', help='Number of delivered but unpaid orders')
    
    stock_overdue_orders_count = fields.Integer(string='Overdue Stock Orders Count', compute='_compute_stock_kpis', help='Number of overdue stock orders')
    stock_overdue_orders_amount = fields.Monetary(string='Overdue Stock Orders Amount', compute='_compute_stock_kpis', help='Total amount of overdue stock orders')
    
    # Stock Operations KPIs
    pending_approval_orders = fields.Integer(string='Orders Pending Approval', compute='_compute_stock_operations_kpis', help='Orders waiting for approval')
    pending_delivery_orders = fields.Integer(string='Orders Pending Shipment', compute='_compute_stock_operations_kpis', help='Orders approved and ready for delivery')
    in_transit_orders = fields.Integer(string='Orders In Transit', compute='_compute_stock_operations_kpis', help='Orders currently in transit')
    delivered_orders = fields.Integer(string='Delivered Orders', compute='_compute_stock_operations_kpis', help='Orders delivered and paid')  # ✅ NUEVO
    average_delivery_time = fields.Float(string='Average Delivery Time from Shipped (Days)', compute='_compute_stock_operations_kpis', help='Average delivery time in days')
    on_time_delivery_rate = fields.Float(string='On-Time Delivery Rate', compute='_compute_stock_operations_kpis', help='Percentage of on-time deliveries')
    average_delivery_from_approval = fields.Float(string='Average Delivery Time from Approval (Days)', compute='_compute_stock_operations_kpis', help='Average time from approval to delivery')
    
    # Performance Status 
    performance_status = fields.Char(string='Collection Rate Status', compute='_compute_performance_status', help='Performance status based on collection rate')
    
    # Currency field 
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    
    # KPIs TOTALES
    total_overdue_count = fields.Integer(string='Total Overdue Count', compute='_compute_total_overdue')
    total_overdue_amount = fields.Monetary(string='Total Overdue Amount', compute='_compute_total_overdue')

    # MÉTODOS COMPUTE FILTRABLES 
    @api.depends('franchise_id', 'date_from', 'date_to')
    def _compute_royalty_kpis(self):
        """
        Calcular KPIs de Regalías basados en los filtros seleccionados.
        - Respeta filtro de franquicia específica
        - Respeta rango de fechas seleccionado
        - Calcula métricas de cobranza y vencimientos
        """
        for dashboard in self:
            # Construir domain base para búsqueda
            royalty_domain = [('state', '!=', 'draft')]
            
            # Aplicar filtros si están definidos
            if dashboard.franchise_id:
                royalty_domain.append(('franchise_id', '=', dashboard.franchise_id.id))
            if dashboard.date_from:
                royalty_domain.append(('period_start_date', '>=', dashboard.date_from))
            if dashboard.date_to:
                royalty_domain.append(('period_end_date', '<=', dashboard.date_to))
            
            # Buscar pagos de regalías
            royalty_payments = self.env['gelroy.royalty.payment'].search(royalty_domain)
            
            # Calcular métricas básicas
            dashboard.total_royalties_calculated = sum(royalty_payments.mapped('calculated_amount'))
            dashboard.total_royalties_paid = sum(royalty_payments.mapped('paid_amount'))
            dashboard.total_royalties_outstanding = sum(royalty_payments.mapped('outstanding_amount'))
            
            # Calcular tasa de cobranza
            if dashboard.total_royalties_calculated > 0:
                dashboard.royalty_collection_rate = dashboard.total_royalties_paid / dashboard.total_royalties_calculated
            else:
                dashboard.royalty_collection_rate = 1.0
            
            # Calcular vencidos
            overdue_payments = royalty_payments.filtered(lambda p: p.state == 'overdue')
            dashboard.overdue_royalty_payments_count = len(overdue_payments)
            dashboard.overdue_royalty_payments_amount = sum(overdue_payments.mapped('outstanding_amount'))
            
            # Promedio por franquicia activa
            active_franchises_count = len(self.env['gelroy.franchise'].search([('active', '=', True)])) or 1
            dashboard.average_royalty_per_franchise = dashboard.total_royalties_calculated / active_franchises_count

    @api.depends('franchise_id', 'date_from', 'date_to')
    def _compute_stock_kpis(self):
        """
        Calcular KPIs de Stock basados en los filtros seleccionados.
        """
        for dashboard in self:
            # Construir domain para pedidos de stock
            stock_domain = [('state', '!=', 'draft')]
            if dashboard.franchise_id:
                stock_domain.append(('franchise_id', '=', dashboard.franchise_id.id))
            if dashboard.date_from:
                stock_domain.append(('order_date', '>=', dashboard.date_from))
            if dashboard.date_to:
                stock_domain.append(('order_date', '<=', dashboard.date_to))

            # Buscar pedidos de stock
            stock_orders = self.env['gelroy.stock.order'].search(stock_domain)
            
            # Métricas básicas
            dashboard.total_stock_orders_value = sum(stock_orders.mapped('total_amount'))
            dashboard.total_stock_orders_count = len(stock_orders)
            dashboard.average_order_value = (dashboard.total_stock_orders_value / dashboard.total_stock_orders_count 
                                           if dashboard.total_stock_orders_count > 0 else 0.0)
            
            # Deuda de stock (entregados sin pagar)
            delivered_unpaid = stock_orders.filtered(lambda o: o.state == 'delivered')
            dashboard.stock_debt_total = sum(delivered_unpaid.mapped('total_amount'))
            dashboard.stock_debt_orders_count = len(delivered_unpaid)

            # Stock Orders Overdue
            overdue_orders = stock_orders.filtered(lambda o: o.state == 'overdue')
            dashboard.stock_overdue_orders_count = len(overdue_orders)
            dashboard.stock_overdue_orders_amount = sum(overdue_orders.mapped('outstanding_amount'))
    
    @api.depends('franchise_id', 'date_from', 'date_to')
    def _compute_stock_operations_kpis(self):
        """Calcular KPIs Operacionales de Stock."""
        for dashboard in self:
            # Construir domain para pedidos de stock
            stock_domain = [('state', '!=', 'draft')]
            if dashboard.franchise_id:
                stock_domain.append(('franchise_id', '=', dashboard.franchise_id.id))
            if dashboard.date_from:
                stock_domain.append(('order_date', '>=', dashboard.date_from))
            if dashboard.date_to:
                stock_domain.append(('order_date', '<=', dashboard.date_to))

            # Buscar pedidos de stock
            stock_orders = self.env['gelroy.stock.order'].search(stock_domain)
            
            # Métricas operacionales básicas
            dashboard.pending_approval_orders = len(stock_orders.filtered(lambda o: o.state == 'submitted'))
            dashboard.pending_delivery_orders = len(stock_orders.filtered(lambda o: o.state == 'approved'))  
            dashboard.in_transit_orders = len(stock_orders.filtered(lambda o: o.state == 'in_transit'))
            dashboard.delivered_orders = len(stock_orders.filtered(lambda o: o.state in ['delivered', 'paid', 'overdue']))
            
            # CALCULAR TIEMPOS DE ENTREGA
            delivered_orders = stock_orders.filtered(lambda o: o.state in ['delivered', 'paid', 'overdue'])
            
            if delivered_orders:
                # Tiempo desde shipped → delivered
                shipping_times = []
                for order in delivered_orders:
                    if order.delivered_date and order.shipped_date:
                        if hasattr(order.delivered_date, 'date'):
                            delivered_date = order.delivered_date.date()
                        else:
                            delivered_date = order.delivered_date
                        
                        if hasattr(order.shipped_date, 'date'):
                            shipped_date = order.shipped_date.date()
                        else:
                            shipped_date = order.shipped_date
                        
                        shipping_time_days = (delivered_date - shipped_date).days
                        if shipping_time_days >= 0:
                            shipping_times.append(shipping_time_days)
                
                dashboard.average_delivery_time = sum(shipping_times) / len(shipping_times) if shipping_times else 0.0
                
                # Tiempo desde approval → delivered  
                approval_times = []
                for order in delivered_orders:
                    if order.delivered_date and order.approved_date:
                        if hasattr(order.delivered_date, 'date'):
                            delivered_date = order.delivered_date.date()
                        else:
                            delivered_date = order.delivered_date
                        
                        if hasattr(order.approved_date, 'date'):
                            approved_date = order.approved_date.date()
                        else:
                            approved_date = order.approved_date
                        
                        approval_time_days = (delivered_date - approved_date).days
                        if approval_time_days >= 0:
                            approval_times.append(approval_time_days)
                
                dashboard.average_delivery_from_approval = sum(approval_times) / len(approval_times) if approval_times else 0.0
                
                # On-time delivery rate
                on_time_orders = 0
                total_orders_with_dates = 0
                
                for order in delivered_orders:
                    if order.delivered_date and order.requested_delivery_date:
                        if hasattr(order.delivered_date, 'date'):
                            delivered_date = order.delivered_date.date()
                        else:
                            delivered_date = order.delivered_date
                        
                        requested_date = order.requested_delivery_date
                        
                        total_orders_with_dates += 1
                        if delivered_date <= requested_date:
                            on_time_orders += 1
                
                dashboard.on_time_delivery_rate = (on_time_orders / total_orders_with_dates) if total_orders_with_dates > 0 else 0.0
                
            else:
                # No hay órdenes entregadas
                dashboard.average_delivery_time = 0.0
                dashboard.average_delivery_from_approval = 0.0
                dashboard.on_time_delivery_rate = 0.0
            
    @api.depends('royalty_collection_rate')
    def _compute_performance_status(self):
        """
        Calcular estado de rendimiento basado en la tasa de cobranza.
        Clasifica el rendimiento en 5 niveles con emojis.
        """
        for dashboard in self:
            collection_rate = dashboard.royalty_collection_rate
            if collection_rate >= 0.9:
                dashboard.performance_status = '🟢 Excellent'
            elif collection_rate >= 0.8:
                dashboard.performance_status = '🟡 Good'
            elif collection_rate >= 0.6:
                dashboard.performance_status = '🟠 Average'
            elif collection_rate >= 0.3:
                dashboard.performance_status = '🔴 Poor'
            else:
                dashboard.performance_status = '⚫ Critical'

    @api.depends('overdue_royalty_payments_count', 'stock_overdue_orders_count', 'overdue_royalty_payments_amount', 'stock_overdue_orders_amount')
    def _compute_total_overdue(self):
        for dashboard in self:
            dashboard.total_overdue_count = dashboard.overdue_royalty_payments_count + dashboard.stock_overdue_orders_count
            dashboard.total_overdue_amount = dashboard.overdue_royalty_payments_amount + dashboard.stock_overdue_orders_amount


# MODELO 2: EXECUTIVE DASHBOARD - MISMA LÓGICA QUE EL FILTRABLE
class ExecutiveDashboard(models.TransientModel):
    _name = 'gelroy.executive.dashboard'
    _description = 'Executive Global Dashboard'
    _rec_name = 'display_name'
    
    display_name = fields.Char(string='Dashboard Name', default='Executive Dashboard', readonly=True)
    
    # USAR MISMOS CAMPOS QUE EL FILTRABLE (sin filtros)
    total_royalties_calculated = fields.Monetary(string='Total Royalties Calculated', compute='_compute_global_royalty_kpis')
    total_royalties_paid = fields.Monetary(string='Total Royalties Paid', compute='_compute_global_royalty_kpis')
    outstanding_royalties = fields.Monetary(string='Outstanding Royalties', compute='_compute_global_royalty_kpis')
    collection_rate = fields.Float(string='Collection Rate (Last Month)', compute='_compute_global_royalty_kpis')
    overdue_payments_count = fields.Integer(string='Overdue Count', compute='_compute_global_royalty_kpis')
    overdue_payments_amount = fields.Monetary(string='Overdue Amount', compute='_compute_global_royalty_kpis')
    average_royalty_per_franchise = fields.Monetary(string='Average Royalty Value', compute='_compute_global_royalty_kpis')
    
    # Stock KPIs globales
    stock_debt_total = fields.Monetary(string='Outstanding S.O. Amount', compute='_compute_global_stock_kpis')
    pending_approval_orders = fields.Integer(string='Pending Approval', compute='_compute_global_stock_kpis')
    pending_delivery_orders = fields.Integer(string='Pending Shipment', compute='_compute_global_stock_kpis')
    average_stock_debt = fields.Monetary(string='Average S.O. Value', compute='_compute_global_stock_kpis')
    delivered_unpaid_orders_count = fields.Integer(string='Outstanding Stock Orders count', compute='_compute_global_stock_kpis')
    
    # Franchise KPIs globales
    active_franchises = fields.Integer(string='Active Franchises', compute='_compute_global_franchise_kpis')
    contracts_expiring = fields.Integer(string='Contracts Expiring', compute='_compute_global_franchise_kpis')
    new_franchises_month = fields.Integer(string='New Franchises (Month)', compute='_compute_global_franchise_kpis')
    new_franchises_quarter = fields.Integer(string='New Franchises (Quarter)', compute='_compute_global_franchise_kpis')
    new_franchises_year = fields.Integer(string='New Franchises (Year)', compute='_compute_global_franchise_kpis')
    
    # campos de franquicias cerradas
    closed_franchises_month = fields.Integer(string='Closed Franchises (Month)', compute='_compute_global_franchise_kpis')
    closed_franchises_quarter = fields.Integer(string='Closed Franchises (Quarter)', compute='_compute_global_franchise_kpis')
    closed_franchises_year = fields.Integer(string='Closed Franchises (Year)', compute='_compute_global_franchise_kpis')
    average_contract_duration = fields.Float(string='Avg Contract Duration (Months)', compute='_compute_global_franchise_kpis', digits=(12, 1))  # ✅ CAMBIAR A FLOAT
    
    # Performance
    performance_status = fields.Char(string='Performance Status', compute='_compute_global_performance')
    
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # campos Stock Orders Overdue globales
    stock_overdue_orders_count = fields.Integer(string='Overdue S.O. Count', compute='_compute_global_stock_kpis', help='Global count of overdue stock orders')
    stock_overdue_orders_amount = fields.Monetary(string='Overdue S.O. Amount', compute='_compute_global_stock_kpis', help='Global amount of overdue stock orders')
    total_overdue_count = fields.Integer(string='Total Overdue Count', compute='_compute_total_overdue')
    total_overdue_amount = fields.Monetary(string='Total Overdue Amount', compute='_compute_total_overdue')

    @api.depends('overdue_payments_count', 'stock_overdue_orders_count', 'overdue_payments_amount', 'stock_overdue_orders_amount')
    def _compute_total_overdue(self):
        for dashboard in self:
            dashboard.total_overdue_count = dashboard.overdue_payments_count + dashboard.stock_overdue_orders_count
            dashboard.total_overdue_amount = dashboard.overdue_payments_amount + dashboard.stock_overdue_orders_amount

    def _compute_global_royalty_kpis(self):
        """Calcula los KPIs globales de regalías para el dashboard de franquicias.
            - Considera todos los pagos históricos de regalías (sin filtros específicos).
            - Calcula el total de regalías calculadas, pagadas y pendientes.
            - Calcula el collection rate considerando únicamente los pagos del último mes.
            - Determina la cantidad y monto de pagos vencidos.
            - Calcula el promedio de regalías por franquicia activa."""
        for dashboard in self:
            # buscar TODOS los pagos HISTÓRICOS (para la mayoría de campos)
            royalty_domain = [('state', '!=', 'draft')]
            royalty_payments = self.env['gelroy.royalty.payment'].search(royalty_domain)
            
            # CAMPOS GLOBALES/HISTÓRICOS 
            dashboard.total_royalties_calculated = sum(royalty_payments.mapped('calculated_amount'))
            dashboard.total_royalties_paid = sum(royalty_payments.mapped('paid_amount'))
            dashboard.outstanding_royalties = sum(royalty_payments.mapped('outstanding_amount'))
            
            # COLLECTION RATE - SOLO ÚLTIMO MES
            today = fields.Date.today()
            month_ago = today - timedelta(days=30)
            
            # Buscar pagos SOLO del último mes para collection rate
            monthly_domain = [
                ('state', '!=', 'draft'),
                ('period_end_date', '>=', month_ago),
                ('period_end_date', '<=', today),
            ]
            monthly_payments = self.env['gelroy.royalty.payment'].search(monthly_domain)
            
            # Collection rate SOLO del último mes
            monthly_calculated = sum(monthly_payments.mapped('calculated_amount'))
            monthly_paid = sum(monthly_payments.mapped('paid_amount'))
            
            if monthly_calculated > 0:
                dashboard.collection_rate = monthly_paid / monthly_calculated
            else:
                dashboard.collection_rate = 0.0
            
            # CAMPOS GLOBALES/HISTÓRICOS 
            overdue_payments = royalty_payments.filtered(lambda p: p.state == 'overdue')
            dashboard.overdue_payments_count = len(overdue_payments)
            dashboard.overdue_payments_amount = sum(overdue_payments.mapped('outstanding_amount'))
            
            # Promedio por franquicia activa (global/histórico)
            active_franchises_count = len(self.env['gelroy.franchise'].search([('active', '=', True)])) or 1
            dashboard.average_royalty_per_franchise = dashboard.total_royalties_calculated / active_franchises_count

    def _compute_global_stock_kpis(self):
        """
        Calcula los KPIs globales de stock para el dashboard ejecutivo.
        - Considera todos los pedidos de stock históricos (sin filtros).
        - Calcula el total de deuda de stock (pedidos entregados y no pagados).
        - Cuenta los pedidos pendientes de aprobación y de entrega.
        - Calcula el promedio del valor de los pedidos de stock.
        - Cuenta la cantidad de pedidos entregados y no pagados.
        - OVERDUE: Tiempo promedio global de entrega (order_date → delivered_date)
        """
        for dashboard in self:
            stock_domain = [('state', '!=', 'draft')]
            stock_orders = self.env['gelroy.stock.order'].search(stock_domain)
            
            delivered_unpaid = stock_orders.filtered(lambda o: o.state == 'delivered')
            dashboard.stock_debt_total = sum(delivered_unpaid.mapped('total_amount'))
            dashboard.pending_approval_orders = len(stock_orders.filtered(lambda o: o.state == 'submitted'))
            dashboard.pending_delivery_orders = len(stock_orders.filtered(lambda o: o.state == 'approved'))
            dashboard.average_stock_debt = sum(stock_orders.mapped('total_amount')) / len(stock_orders) if stock_orders else 0.0
            dashboard.delivered_unpaid_orders_count = len(delivered_unpaid)

            # Stock Orders Overdue globales
            overdue_orders = stock_orders.filtered(lambda o: o.state == 'overdue')
            dashboard.stock_overdue_orders_count = len(overdue_orders)
            dashboard.stock_overdue_orders_amount = sum(overdue_orders.mapped('outstanding_amount'))
            
    def _compute_global_franchise_kpis(self):
        """Calcula los KPIs globales para el dashboard de franquicias.
            - Obtiene el número total de franquicias activas.
            - Calcula la cantidad de contratos por vencer en los próximos 90 días.
            - Determina la cantidad de nuevas franquicias creadas en el último mes, trimestre y año.
            - Calcula la cantidad de franquicias cerradas en el último mes, trimestre y año.
            - Calcula la duración promedio de los contratos activos en meses.
        """
        for dashboard in self:
            all_franchises = self.env['gelroy.franchise'].search([])
            active_franchises = all_franchises.filtered(lambda f: f.active)
            dashboard.active_franchises = len(active_franchises)

            # Contratos por vencer
            today = fields.Date.today()
            expiring_contracts = self.env['gelroy.franchise'].search([
                ('contract_end_date', '>=', today),
                ('contract_end_date', '<=', today + timedelta(days=90))
            ])
            dashboard.contracts_expiring = len(expiring_contracts)
            
            # Nuevas franquicias por período
            dashboard.new_franchises_month = self.env['gelroy.franchise'].search_count([('create_date', '>=', today - timedelta(days=30))])
            dashboard.new_franchises_quarter = self.env['gelroy.franchise'].search_count([('create_date', '>=', today - timedelta(days=90))])
            dashboard.new_franchises_year = self.env['gelroy.franchise'].search_count([('create_date', '>=', today - timedelta(days=365))])

            # LÓGICA PARA FRANQUICIAS CERRADAS
            month_ago = today - timedelta(days=30)
            quarter_ago = today - timedelta(days=90)
            year_ago = today - timedelta(days=365)
            
            dashboard.closed_franchises_month = self.env['gelroy.franchise'].search_count([
                ('active', '=', False),
                ('write_date', '>=', fields.Datetime.to_datetime(month_ago))
            ])
            dashboard.closed_franchises_quarter = self.env['gelroy.franchise'].search_count([
                ('active', '=', False),
                ('write_date', '>=', fields.Datetime.to_datetime(quarter_ago))
            ])
            dashboard.closed_franchises_year = self.env['gelroy.franchise'].search_count([
                ('active', '=', False),
                ('write_date', '>=', fields.Datetime.to_datetime(year_ago))
            ])
            
            #DURACIÓN PROMEDIO DE CONTRATOS
            contracts_with_dates = active_franchises.filtered(lambda f: f.contract_start_date and f.contract_end_date)
            if contracts_with_dates:
                total_duration_days = sum([(f.contract_end_date - f.contract_start_date).days for f in contracts_with_dates])
                average_duration_days = total_duration_days / len(contracts_with_dates)
                dashboard.average_contract_duration = average_duration_days / 30.44 
            else:
                dashboard.average_contract_duration = 1.0  

    @api.depends('collection_rate')
    def _compute_global_performance(self):
        """
        Calcular estado de rendimiento basado en la tasa de cobranza.
        Clasifica el rendimiento en 5 niveles con emojis.
        """
        for dashboard in self:
            collection_rate = dashboard.collection_rate
            if collection_rate >= 0.9:
                dashboard.performance_status = '🟢 Excellent'
            elif collection_rate >= 0.8:
                dashboard.performance_status = '🟡 Good'
            elif collection_rate >= 0.6:
                dashboard.performance_status = '🟠 Average'
            elif collection_rate >= 0.3:
                dashboard.performance_status = '🔴 Poor'
            else:
                dashboard.performance_status = '⚫ Critical'

    @api.model
    def default_get(self, fields_list):
        """Forzar cálculo al crear el registro"""
        res = super().default_get(fields_list)
        # Crear instancia temporal para calcular
        temp_record = self.new(res)
        
        # LLAMAR A LOS MÉTODOS 
        temp_record._compute_global_royalty_kpis()
        temp_record._compute_global_stock_kpis()
        temp_record._compute_global_franchise_kpis()
        temp_record._compute_global_performance()
        temp_record._compute_total_overdue()
        
        # Copiar valores calculados - USAR TRY/EXCEPT EN LUGAR DE HASATTR
        for field in fields_list:
            try:
                if field in temp_record._fields:  # Verificar que el campo existe
                    res[field] = temp_record[field]
            except (AttributeError, KeyError, RecursionError):
                # Si hay error, simplemente saltear el campo
                pass
        return res