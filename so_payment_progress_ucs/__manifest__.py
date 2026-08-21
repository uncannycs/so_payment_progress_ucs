{
    'name': 'Sale Order Payment Progress  Sale Order Payment Tracking | Sale Order Payment Followup |  Sales Order Payment Monitoring | Sale Order Payment Manager',
    'summary': 'Show Payment Status on Sale Order Tree and Sale Order Form. Do a payment on Sale Order Form',
    'description': 'Show Payment Status on Sale Order Tree and Sale Order Form. Do a payment on Sale Order Form',
    'category': 'Sales',
    'version': '19.0.1.0.0',
    'depends': ['sale', 'account'],

    'data': [
        'views/form_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'so_payment_progress_ucs/static/src/xml/account_payment.xml',
            'so_payment_progress_ucs/static/src/js/payment.js',
        ],
    },
    'website': 'https://uncannycs.com',
    'author': 'Uncanny Consulting Services LLP',
    'maintainer': 'Uncanny Consulting Services LLP',
    'license': 'Other proprietary',
    "images": ['static/description/banner.gif'],
    "price": 50,
    "currency": "USD",
}