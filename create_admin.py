from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User


app = create_app()


with app.app_context():

    existing_user = User.query.filter_by(phone="0000000000").first()

    if existing_user:
        print("Test user already exists.")
        print("Phone: 0000000000")
        print("Password: TDM12345")

    else:
        user = User(
            name="TDM Admin",
            phone="0000000000",
            password_hash=generate_password_hash("TDM12345"),
            role="admin"
        )

        db.session.add(user)
        db.session.commit()

        print("Test user created successfully.")
        print("Phone: 0000000000")
        print("Password: TDM12345")