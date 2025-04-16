from datetime import datetime
from app import db

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, index=True, unique=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.String(50), nullable=False)
    supplier = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Product {self.code}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'description': self.description,
            'price': self.price,
            'supplier': self.supplier
        }