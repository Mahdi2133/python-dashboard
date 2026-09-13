"""Blueprint registration."""


def register_blueprints(app):
    from .auth import bp as auth_bp
    from .pages import bp as pages_bp
    from .api_records import bp as records_bp
    from .api_wells import bp as wells_bp
    from .api_lookups import bp as lookups_bp
    from .api_formbuilder import bp as formbuilder_bp
    from .api_dashboard import bp as dashboard_bp
    from .api_reports import bp as reports_bp
    from .api_transfer import bp as transfer_bp
    from .api_admin import bp as admin_bp

    for bp in (auth_bp, pages_bp, records_bp, wells_bp, lookups_bp, formbuilder_bp,
               dashboard_bp, reports_bp, transfer_bp, admin_bp):
        app.register_blueprint(bp)
