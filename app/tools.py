"""Support tools.

Owner: B
"""

def lookup_account(account_id): raise NotImplementedError
def get_usage(account_id): raise NotImplementedError
def get_plan_limits(plan): raise NotImplementedError
def get_invoices(account_id): raise NotImplementedError
def check_refund_eligibility(account_id, invoice_id): raise NotImplementedError
def check_platform_status(): raise NotImplementedError
def send_password_reset(account_id): raise NotImplementedError  # mock
def create_handoff(payload): raise NotImplementedError
