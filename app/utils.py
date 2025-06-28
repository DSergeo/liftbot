from flask import session

def get_company_db_path():
    company_id = session.get("selected_company")
    return "elestek_lift.db" if company_id == "2" else "elestek.db"
