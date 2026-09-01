from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
login_manager.login_message_category = 'warning'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # Registro de Blueprints
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.projects.routes import projects_bp
    from app.daily.routes import daily_bp
    from app.reports.routes import reports_bp
    from app.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(daily_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)

    # Inicializar APScheduler en modo producción/dev (omitiendo en testing)
    if not app.config.get('TESTING'):
        from app.scheduler import init_scheduler
        init_scheduler(app)

    # Crear tablas e inicializar un administrador base
    with app.app_context():
        db.create_all()
        from app.models import User, UserRole
        if not User.query.filter_by(rol=UserRole.ADMIN.value).first():
            admin = User(
                nombre='Administrador Sistema',
                email='admin@empresa.com',
                rol=UserRole.ADMIN.value
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

    # Manejo de errores HTTP
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app

