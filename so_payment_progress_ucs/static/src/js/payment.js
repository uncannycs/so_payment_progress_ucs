/** @odoo-module **/

import { AccountPaymentField } from "@account/components/account_payment_field/account_payment_field";
import { patch } from "@web/core/utils/patch";

patch(AccountPaymentField.prototype, {
    async openMove(moveId) {
        const action = await this.orm.call('account.move', 'action_open_business_doc', [moveId], {});
        this.action.doAction(action);
    }
});

