from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate


db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    app.config.from_object("config.Config")

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    from app import models

    from app.routes import main
    from app.routes.auth import auth
    from app.routes.setup import setup
    from app.routes.money import money
    from app.routes.sales import sales
    from app.routes.inventory import inventory
    from app.routes.expenses import expenses
    from app.routes.partners import partners
    from app.routes.purchases import purchases
    from app.routes.reports import reports

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(setup)
    app.register_blueprint(money)
    app.register_blueprint(sales)
    app.register_blueprint(inventory)
    app.register_blueprint(expenses)
    app.register_blueprint(partners)
    app.register_blueprint(purchases)
    app.register_blueprint(reports)

   

    return app


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return db.session.get(User, int(user_id))