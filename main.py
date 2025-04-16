from app import app, db  # noqa: F401

with app.app_context():
    from models import Product  # noqa: F401
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
