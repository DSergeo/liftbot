from flask import session


def get_company_db_path():
    company_id = session.get("selected_company")
    return "elestek_lift.db" if company_id == "2" else "elestek.db"

def clean_currency_format(value):
    """Converts Ukrainian formatted currency (with commas) to float"""
    if value is None:
        return 0.0
    return float(str(value).replace(',', '.').replace(' ', ''))

def format_currency_ua(value):
    """Formats currency in Ukrainian format: 72861.44 -> 72,861,44 ₴"""
    if not value:
        return "0,00 ₴"
    
    # Convert to float if string
    if isinstance(value, str):
        value = clean_currency_format(value)
    
    # Format with thousands separator and comma as decimal separator
    formatted = f"{value:,.2f}".replace(',', '|').replace('.', ',').replace('|', ',')
    return f"{formatted} ₴"