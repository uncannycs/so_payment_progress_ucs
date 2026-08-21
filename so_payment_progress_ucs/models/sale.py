from odoo import models, fields, api, _
from odoo.tools import float_is_zero, float_compare, float_repr, formatLang
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_state = fields.Selection([
        ('no_invoice', 'No Invoice'),
        ('not_paid', 'Not Paid'),
        ('partial_paid', 'Partial Paid'),
        ('fully_paid', 'Fully Paid'),
        ('overdue', 'Overdue')
    ], string='Payment Status', default='no_invoice', copy=False, compute='_compute_payment_state', store=True, readonly=True, help="Payment Status.")

    compute_payment_state = fields.Char(
        string='Payment Status', compute='_compute_display_payment_state', store=False, copy=False,
        default='No Invoice', readonly=True, help="Payment Status."
    )

    ribbon_payment_state = fields.Char(
        string='Payment Status Ribbon', store=False, default='no_invoice',
        compute='_compute_display_payment_state'
    )

    show_payment_button = fields.Boolean(
        string='Show Payment Button', compute='_show_payment_button', store=False, copy=False
    )

    payments_widget = fields.Binary(
        string='Payment Details',
        groups="account.group_account_invoice,account.group_account_readonly",
        compute='_compute_payments_widget_reconciled_info'
    )

    order_amount_residual = fields.Monetary(
        string='Amount Due', compute='_compute_order_amount', help="Order Amount Due."
    )

    @api.depends(
        'state',
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.payment_state',
        'invoice_ids.amount_total',
        'invoice_ids.amount_residual',
        'invoice_ids.invoice_date_due',
        'order_line.qty_delivered',
        'order_line.qty_invoiced',
        'order_line.product_uom_qty'
    )
    def _compute_payment_state(self):
        for order in self:
            is_fully_delivery = order._is_fully_delivery()
            raw_payment_state = 'no_invoice'
            if order.state == 'sale':
                posted_invoices = order.invoice_ids.filtered(
                    lambda i: i.state == "posted" and i.move_type in ['out_invoice', 'out_receipt']
                )

                if not posted_invoices:
                    raw_payment_state = 'no_invoice'
                else:
                    invoices = posted_invoices.filtered(
                        lambda i: i.payment_state not in ['paid', 'reversed', 'in_payment']
                    )
                    paid_invoices = posted_invoices.filtered(
                        lambda i: i.payment_state in ['paid', 'in_payment']
                    )

                    if not is_fully_delivery:
                        pl_order_amount_due = float(float_repr(order.order_amount_residual,
                                                               precision_digits=order.currency_id.decimal_places or 2))

                        amount_total = order.amount_total
                        if pl_order_amount_due >= amount_total:
                            raw_payment_state = 'not_paid'
                        elif (0 < pl_order_amount_due < amount_total and invoices) or (0 < pl_order_amount_due < amount_total and paid_invoices):
                            raw_payment_state = 'partial_paid'
                        elif pl_order_amount_due == 0:
                            raw_payment_state = 'fully_paid'
                    else:
                        total_paid, total_invoice_amount = order._get_total_paid_total_invoice_amount()
                        priced_lines = order._get_priced_lines().filtered(lambda l: not getattr(l, 'is_downpayment', False))
                        if priced_lines:
                            total_invoice_amount += sum(
                                (line.qty_delivered - line.qty_invoiced) * line.price_reduce_taxinc for line in
                                priced_lines)

                        if total_invoice_amount > total_paid and not total_paid:
                            raw_payment_state = 'not_paid'
                        elif 0 < total_paid < total_invoice_amount and invoices:
                            raw_payment_state = 'partial_paid'
                        elif total_paid >= total_invoice_amount > 0:
                            raw_payment_state = 'fully_paid'

            # Check payment overdue
            if raw_payment_state in ['partial_paid', 'not_paid']:
                today = fields.Date.context_today(self)
                invoices = order.invoice_ids.filtered(
                    lambda i: i.state == "posted" and i.move_type in ['out_invoice', 'out_receipt'] and i.payment_state not in ['paid']
                )
                if any(l.invoice_date_due and l.invoice_date_due < today for l in invoices):
                    raw_payment_state = 'overdue'

            order.payment_state = raw_payment_state

    @api.depends('payment_state', 'invoice_ids.invoice_date_due', 'invoice_ids.state')
    def _compute_display_payment_state(self):
        for order in self:
            raw_payment_state = order.payment_state or 'no_invoice'
            order.ribbon_payment_state = raw_payment_state

            if raw_payment_state == 'no_invoice':
                order.compute_payment_state = 'No Invoice'
            elif raw_payment_state == 'not_paid':
                order.compute_payment_state = 'Not Paid'
            elif raw_payment_state == 'partial_paid':
                order.compute_payment_state = 'Partial Paid'
            elif raw_payment_state == 'fully_paid':
                order.compute_payment_state = 'Fully Paid'
            elif raw_payment_state == 'overdue':
                diff = 0
                today = fields.Date.context_today(self)
                for l in order.invoice_ids.filtered(lambda i: i.state == 'posted' and i.invoice_date_due):
                    if (today - l.invoice_date_due).days > diff:
                        diff = (today - l.invoice_date_due).days
                if diff == 1:
                    order.compute_payment_state = 'Overdue (yesterday)'
                elif diff > 1:
                    order.compute_payment_state = 'Overdue (%s days ago)' % str(diff)
                else:
                    order.compute_payment_state = 'Overdue'
            else:
                order.compute_payment_state = 'No Invoice'

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.amount_total_signed')
    def _show_payment_button(self):
        for order in self:
            order.show_payment_button = False
            invoice_not_paid = order.invoice_ids.filtered(
                lambda i: i.state == 'posted' and i.payment_state in ['not_paid', 'partial'] and i.move_type == 'out_invoice'
            )

            amount_total_signed = sum(inv.amount_total_signed for inv in order.invoice_ids.filtered(
                lambda i: i.state == 'posted' and i.move_type in ['out_invoice', 'out_receipt', 'out_refund']
            ))

            if amount_total_signed and invoice_not_paid:
                order.show_payment_button = True

    @api.depends(
        'state',
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.payment_state',
        'invoice_ids.amount_total',
        'invoice_ids.amount_residual',
        'order_line.qty_delivered',
        'order_line.qty_invoiced',
        'order_line.product_uom_qty'
    )
    def _compute_order_amount(self):
        for order in self:
            total_paid, pl_order_amount_due = order._get_total_paid_total_invoice_amount()
            lines = order._get_priced_lines().filtered(lambda l: not getattr(l, 'is_downpayment', False))
            is_fully_delivery = order._is_fully_delivery()

            if not is_fully_delivery and lines:
                pl_order_amount_due += sum((line.product_uom_qty - line.qty_invoiced) * line.price_reduce_taxinc for line in lines)
            elif is_fully_delivery and lines:
                pl_order_amount_due += sum(
                    (line.qty_delivered - line.qty_invoiced) * line.price_reduce_taxinc for line in lines)

            pl_order_amount_due = pl_order_amount_due - total_paid

            txs = self.env['payment.transaction'].sudo().search([('sale_order_ids', '=', order.id)])
            for tx in txs:
                if tx and tx.state == 'done' and tx.payment_id and tx.payment_id.state == 'posted':
                    pl_order_amount_due -= tx.amount

            order.order_amount_residual = pl_order_amount_due if pl_order_amount_due > 0 else 0.0

    def _get_invoiceable_orderline(self, final=False):
        return self._get_invoiceable_lines(final=final)

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.payment_state', 'invoice_ids.line_ids.amount_residual')
    def _compute_payments_widget_reconciled_info(self):
        for order in self:
            reconciled_vals = []
            payments_widget_vals = {'title': _('Less Payment'), 'outstanding': False, 'content': []}
            invoice_paid = order.invoice_ids.filtered(lambda i: i.state == 'posted' and i.payment_state in ['paid', 'partial', 'in_payment']
                                                               and i.move_type == 'out_invoice')

            if invoice_paid:
                for inv in invoice_paid:
                    reconciled_partials = inv.sudo()._get_all_reconciled_invoice_partials()
                    for reconciled_partial in reconciled_partials:
                        counterpart_line = reconciled_partial['aml']
                        if counterpart_line.move_id.ref:
                            reconciliation_ref = '%s (%s)' % (counterpart_line.move_id.name, counterpart_line.move_id.ref)
                        else:
                            reconciliation_ref = counterpart_line.move_id.name
                        if counterpart_line.amount_currency and counterpart_line.currency_id != counterpart_line.company_id.currency_id:
                            foreign_currency = counterpart_line.currency_id
                        else:
                            foreign_currency = False

                        reconciled_vals.append({
                            'name': counterpart_line.name,
                            'journal_name': counterpart_line.journal_id.name,
                            'company_name': counterpart_line.journal_id.company_id.name if counterpart_line.journal_id.company_id != order.company_id else False,
                            'amount': reconciled_partial['amount'],
                            'currency_id': order.company_id.currency_id.id if reconciled_partial['is_exchange'] else reconciled_partial['currency'].id,
                            'date': counterpart_line.date,
                            'partial_id': reconciled_partial['partial_id'],
                            'account_payment_id': counterpart_line.payment_id.id if counterpart_line.payment_id else False,
                            'payment_method_name': counterpart_line.payment_id.payment_method_line_id.name if counterpart_line.payment_id and counterpart_line.payment_id.payment_method_line_id else None,
                            'move_id': counterpart_line.move_id.id,
                            'is_refund': counterpart_line.move_id.move_type in ['in_refund', 'out_refund'],
                            'ref': reconciliation_ref,
                            'no_unreconcile': True,
                            'is_exchange': reconciled_partial['is_exchange'],
                            'amount_company_currency': formatLang(self.env, abs(counterpart_line.balance), currency_obj=counterpart_line.company_id.currency_id),
                            'amount_foreign_currency': foreign_currency and formatLang(self.env, abs(counterpart_line.amount_currency), currency_obj=foreign_currency)
                        })
                payments_widget_vals['content'] = reconciled_vals
            else:
                txs = self.env['payment.transaction'].sudo().search([('sale_order_ids', '=', order.id)])
                for tx in txs:
                    if tx and tx.state == 'done' and tx.payment_id and tx.payment_id.state == 'posted':
                        p = tx.payment_id
                        reconciled_vals.append({
                            'name': p.name,
                            'journal_name': p.journal_id.name,
                            'amount': p.amount,
                            'currency_id': p.currency_id.id,
                            'date': p.date,
                            'account_payment_id': p.id,
                            'payment_method_name': p.payment_method_line_id.name if p.journal_id.type == 'bank' else None,
                            'move_id': p.move_id.id,
                            'ref': p.ref,
                            'no_unreconcile': True,
                            'is_exchange': False,
                            'amount_company_currency': formatLang(self.env, abs(p.amount), currency_obj=order.company_id.currency_id),
                            'amount_foreign_currency': formatLang(self.env, abs(p.amount), currency_obj=order.currency_id) if order.currency_id != order.company_id.currency_id else False
                        })
                        payments_widget_vals['content'] = reconciled_vals

            if payments_widget_vals['content']:
                order.payments_widget = payments_widget_vals
            else:
                order.payments_widget = False

    def action_register_payment(self):
        invoice_not_paid = self.invoice_ids.filtered(
            lambda i: i.state == 'posted' and i.payment_state in ['not_paid', 'partial'] and i.move_type in ['out_invoice', 'out_receipt', 'out_refund']
        )

        if not invoice_not_paid:
            raise UserError(_("You can't register a payment because there is nothing left to pay on the selected journal items."))

        action = invoice_not_paid.action_register_payment()
        action['context']['dont_redirect_to_payments'] = True
        return action

    def _get_total_paid_total_invoice_amount(self):
        self.ensure_one()
        total_paid = 0
        total_invoice_amount = 0
        down_payment = 0
        if self.invoice_ids:
            invoices = self.invoice_ids.filtered(
                lambda i: i.state == "posted" and i.move_type in ['out_invoice', 'out_receipt']
            )

            if invoices:
                for inv_line in invoices.invoice_line_ids:
                    if getattr(inv_line, 'is_downpayment', False) or any(sol.is_downpayment for sol in inv_line.sale_line_ids):
                        down_payment += inv_line.price_total

                for invoice in invoices:
                    total_paid += invoice.amount_total - invoice.amount_residual
                    total_invoice_amount += invoice.amount_total

        txs = self.env['payment.transaction'].sudo().search([('sale_order_ids', '=', self.id)])
        for tx in txs:
            if tx and tx.state == 'done' and tx.payment_id and tx.payment_id.state == 'posted':
                total_paid += tx.amount

        return total_paid, total_invoice_amount - down_payment

    def _is_fully_delivery(self):
        self.ensure_one()
        if not hasattr(self, 'picking_ids') or not self.picking_ids:
            return False
        pickings_done = self.picking_ids.filtered(lambda p: p.state == 'done')
        pickings_not_done = self.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel'] and p.state in ['draft', 'waiting', 'confirmed', 'assigned']
        )
        return bool(pickings_done and not pickings_not_done)