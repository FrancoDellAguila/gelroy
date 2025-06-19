from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    franchise_id = fields.Many2one(
        'gelroy.franchise',
        string='Related Franchise',
        help="Franchise related to this invoice"
    )
    
    stock_order_id = fields.Many2one(
        'gelroy.stock.order',
        string='Related Stock Order',
        help="Stock order that generated this invoice"
    )
    
    royalty_payment_id = fields.Many2one(
        'gelroy.royalty.payment',
        string='Related Royalty Payment',
        help="Royalty payment that generated this invoice"
    )

    def write(self, vals):
        """Override write para detectar cambios de estado en facturas (UNIFICADO)"""
        result = super().write(vals)
        
        # Si se cambió el estado de pago (payment_state)
        if 'payment_state' in vals:
            for move in self:
                if move.move_type == 'out_invoice' and move.invoice_origin:
                    self._sync_related_records(move)
        
        return result
    
    def _sync_related_records(self, invoice):
        """Sincronizar registros relacionados cuando cambia el estado de pago"""
        
        # 1. ROYALTY PAYMENTS - Buscar por invoice_origin
        royalty_payment = self.env['gelroy.royalty.payment'].search([
            ('name', '=', invoice.invoice_origin)
        ], limit=1)
        
        if royalty_payment:
            if invoice.payment_state == 'paid' and royalty_payment.state != 'paid':
                royalty_payment.write({
                    'state': 'paid',
                    'paid_amount': royalty_payment.calculated_amount,
                    'payment_date': fields.Date.today(),
                })
                royalty_payment.message_post(
                    body=_("Automatically marked as paid by invoice: %s") % invoice.name
                )
            
            elif invoice.payment_state in ['not_paid', 'partial'] and royalty_payment.state == 'paid':
                # Revertir estado
                today = fields.Date.today()
                new_state = 'overdue' if (royalty_payment.payment_due_date and 
                                        royalty_payment.payment_due_date < today) else 'confirmed'
                
                royalty_payment.write({
                    'state': new_state,
                    'paid_amount': 0.0,
                    'payment_date': False,
                })

        
        # 2. STOCK ORDERS - Buscar por invoice_origin
        stock_order = self.env['gelroy.stock.order'].search([
            ('name', '=', invoice.invoice_origin)
        ], limit=1)
        
        if stock_order:
            if invoice.payment_state == 'paid' and stock_order.state != 'paid':
                stock_order.write({
                    'state': 'paid',
                    'payment_date': fields.Date.today(),
                })
                stock_order.message_post(
                    body=_("Automatically marked as paid by invoice: %s") % invoice.name
                )
            
            elif invoice.payment_state in ['not_paid', 'partial'] and stock_order.state == 'paid':
                today = fields.Date.today()
                new_state = 'overdue' if (stock_order.payment_due_date and 
                                        stock_order.payment_due_date < today and
                                        stock_order.outstanding_amount > 0) else 'delivered'
                
                stock_order.write({
                    'state': new_state,
                    'payment_date': False,
                })

#BORRAR
class StockOrder(models.Model):
    _inherit = 'gelroy.stock.order'
    
    invoice_id = fields.Many2one(
        'account.move',
        string='Generated Invoice',
        readonly=True
    )
    
    def action_generate_invoice(self):
        """Generar factura automáticamente desde orden de stock"""
        self.ensure_one()
        
        if self.invoice_id:
            raise UserError(_("Invoice already generated for this order."))
        
        # Crear factura con identificación correcta
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.franchise_id.franchisee_id.id,
            'franchise_id': self.franchise_id.id,
            'stock_order_id': self.id,
            'invoice_date': fields.Date.today(),
            'invoice_origin': self.name,
            'ref': f"Stock Order: {self.name}",
            'invoice_line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.unit_price,
                'name': f"{line.product_id.name} - {self.name}",
            }) for line in self.order_line_ids],
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({
            'invoice_id': invoice.id,
        })
        
        self.message_post(
            body=_("📄 Factura generada: %s") % invoice.name
        )
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }