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
    from .api_workflow import bp as workflow_bp
    from .api_analytics import bp as analytics_bp
    from .api_catalogue import bp as catalogue_bp
    from .api_refdata import bp as refdata_bp
    from .api_warehouse import bp as warehouse_bp

    for bp in (auth_bp, pages_bp, records_bp, wells_bp, lookups_bp, formbuilder_bp,
               dashboard_bp, reports_bp, transfer_bp, admin_bp,
               workflow_bp, analytics_bp, catalogue_bp, refdata_bp, warehouse_bp):
        app.register_blueprint(bp)
