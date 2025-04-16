import os
import pandas as pd
import logging
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from functools import wraps
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
import io

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

ADMIN_USERNAMES = ['KARIMDALAM123@GMAIL.COM']  # المشرف المصرح له فقط

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_username = request.headers.get('X-Replit-User-Name')
        if not admin_username or admin_username not in ADMIN_USERNAMES:
            flash('غير مصرح لك بالوصول لهذه الصفحة', 'danger')
            return redirect(url_for('search'))
        return f(*args, **kwargs)
    return decorated_function
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_dev")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file size to 16MB

# Configure database
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

@app.route('/')
def index():
    return redirect(url_for('search'))

@app.route('/upload')
@admin_required
def upload():
    return render_template('upload.html')

@app.route('/upload_file', methods=['POST'])
@admin_required
def upload_file():
    try:
        logger.debug("File upload endpoint called")

        if 'file' not in request.files:
            flash('لم يتم العثور على ملف', 'danger')
            return redirect(url_for('upload'))

        file = request.files['file']

        if file.filename == '':
            flash('لم يتم اختيار ملف للتحميل', 'danger')
            return redirect(url_for('upload'))

        # Get file extension
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ['.csv', '.xlsx', '.xls']:
            flash('يرجى تحميل ملف CSV أو Excel فقط', 'danger')
            return redirect(url_for('upload'))

        # Read file content
        if file_ext == '.csv':
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # Process the dataframe
        process_dataframe(df)

        flash('تم تحميل ومعالجة الملف بنجاح', 'success')
        return redirect(url_for('products'))

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        flash(f'حدث خطأ أثناء معالجة الملف: {str(e)}', 'danger')
        return redirect(url_for('upload'))

    # Get secure filename
    filename = secure_filename(file.filename)
    logger.debug(f"Uploaded file: {filename}")

    # Check file extension
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ['.csv', '.xlsx', '.xls']:
        flash('يرجى تحميل ملف CSV أو Excel', 'danger')
        return redirect(url_for('upload'))

    try:
        # Save file temporarily
        temp_path = f"/tmp/{filename}"
        file.save(temp_path)
        logger.debug(f"File saved temporarily at: {temp_path}")

        # Process based on file type
        if file_ext == '.csv':
            df = pd.read_csv(temp_path)
        else:
            df = pd.read_excel(temp_path)

        # Remove temporary file
        os.remove(temp_path)

        # Process data
        logger.debug(f"File loaded successfully, columns: {df.columns.tolist()}")
        process_dataframe(df)
        flash(f'تم تحميل ومعالجة الملف {filename} بنجاح', 'success')
        return redirect(url_for('products'))

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        flash(f'حدث خطأ أثناء معالجة الملف: {str(e)}', 'danger')
        return redirect(url_for('upload'))

@app.route('/upload_sheet', methods=['POST'])
def upload_sheet():
    logger.debug("Google Sheet upload endpoint called")

    if 'sheet_url' not in request.form or not request.form['sheet_url']:
        flash('لم يتم إدخال رابط Google Sheet', 'danger')
        return redirect(url_for('upload'))

    sheet_url = request.form['sheet_url']
    logger.debug(f"Sheet URL: {sheet_url}")

    try:
        # Get Google Sheets credentials from environment
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        if not creds_json:
            flash('لم يتم العثور على بيانات اعتماد Google Sheets. يرجى تكوين بيانات الاعتماد.', 'danger')
            return redirect(url_for('upload'))

        # Load credentials
        try:
            creds_dict = json.loads(creds_json)
            # Use in-memory credentials instead of temporary file
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

            # Create credentials
            temp_file = os.path.join(os.getcwd(), 'temp_credentials.json')
            with open(temp_file, 'w') as f:
                json.dump(creds_dict, f)

            credentials = ServiceAccountCredentials.from_json_keyfile_name(temp_file, scope)
            # Remove the temp file immediately
            os.remove(temp_file)

            # Authorize with Google
            gc = gspread.authorize(credentials)

            # Extract the spreadsheet ID from the URL
            if 'spreadsheets/d/' in sheet_url:
                spreadsheet_id = sheet_url.split('spreadsheets/d/')[1].split('/')[0]
                spreadsheet = gc.open_by_key(spreadsheet_id)
            else:
                flash('تنسيق رابط Google Sheet غير صالح', 'danger')
                return redirect(url_for('upload'))

            # Get the first worksheet
            worksheet = spreadsheet.get_worksheet(0)

            # Get all values from worksheet
            data = worksheet.get_all_records()

            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Process the dataframe
            process_dataframe(df)

            flash('تم معالجة Google Sheet بنجاح', 'success')
            return redirect(url_for('search'))

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in credentials: {str(e)}")
            flash('تنسيق بيانات اعتماد Google Sheets غير صالح', 'danger')
            return redirect(url_for('upload'))

    except Exception as e:
        logger.error(f"Error processing Google Sheet: {str(e)}")
        flash(f'حدث خطأ أثناء معالجة Google Sheet: {str(e)}', 'danger')
        return redirect(url_for('upload'))

# Import models after the database is initialized
from models import Product

@app.route('/search')
def search():
    # Check if any products exist in the database
    products_count = Product.query.count()
    if products_count == 0:
        flash('Please upload a data file first', 'warning')
        return redirect(url_for('index'))

    return render_template('search.html')

@app.route('/api/search', methods=['POST'])
def api_search():
    try:
        code = request.json.get('code', '').strip()
        if not code:
            return jsonify({'success': False, 'error': 'No product code provided'})

        # Search for the product in database
        product = Product.query.filter(Product.code == code).first()

        if product:
            return jsonify({'success': True, 'product': product.to_dict()})

        return jsonify({'success': False, 'error': 'Product not found'})
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def process_dataframe(df):
    """Process the dataframe and store furniture data in database"""
    # Check if required columns exist (using both English and Arabic column names)
    required_columns = [
        ['code', 'قطعة كود', 'كود القطعة', 'الكود', 'كود'],
        ['description', 'وصف القطعة', 'الوصف', 'وصف المنتج', 'وصف'],
        ['price', 'السعر', 'سعر المنتج', 'سعر القطعة'],
        ['supplier', 'المورد', 'اسم المورد']
    ]

    column_mapping = {}
    for aliases in required_columns:
        found = False
        for alias in aliases:
            if alias in df.columns:
                column_mapping[aliases[0]] = alias
                found = True
                break
        if not found:
            raise ValueError(f"Missing required column: {aliases[0]} (or its Arabic equivalent)")

    # Clear existing products
    Product.query.delete()
    db.session.commit()

    # Process each row and add to database
    count = 0
    for _, row in df.iterrows():
        product = Product(
            code=str(row[column_mapping['code']]).strip(),
            description=str(row[column_mapping['description']]),
            price=str(row[column_mapping['price']]),
            supplier=str(row[column_mapping['supplier']])
        )
        db.session.add(product)
        count += 1

    db.session.commit()
    logger.debug(f"Processed {count} products")

@app.route('/reset', methods=['POST'])
@admin_required
def reset_data():
    """Clear the loaded furniture data and return to the upload page"""
    # Clear all products
    Product.query.delete()
    db.session.commit()

    flash('تم حذف جميع الأصناف بنجاح', 'info')
    return redirect(url_for('products'))

@app.route('/products', methods=['GET', 'POST'])
def products():
    """Display all products in a table with password protection"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == '7120':
            session['authenticated'] = True
            all_products = Product.query.all()
            return render_template('products.html', products=all_products, authenticated=True)
        else:
            flash('كلمة المرور غير صحيحة', 'danger')
            return render_template('products.html', authenticated=False)

    if session.get('authenticated'):
        all_products = Product.query.all()
        return render_template('products.html', products=all_products, authenticated=True)

    return render_template('products.html', authenticated=False, products=None)

@app.route('/edit_price', methods=['POST'])
@admin_required
def edit_price():
    """Update product price"""
    try:
        product_code = request.form.get('code')
        new_price = request.form.get('price')

        if not product_code or not new_price:
            flash('يرجى تعبئة جميع الحقول المطلوبة', 'danger')
            return redirect(url_for('products'))

        product = Product.query.filter_by(code=product_code).first()
        if product:
            product.price = new_price
            db.session.commit()
            flash('تم تحديث السعر بنجاح', 'success')
        else:
            flash('لم يتم العثور على المنتج', 'danger')

        return redirect(url_for('products'))

    except Exception as e:
        flash(f'حدث خطأ أثناء تحديث السعر: {str(e)}', 'danger')
        return redirect(url_for('products'))

@app.route('/export_excel')
def export_excel():
    """Export all products to Excel file"""
    try:
        # Get all products from database
        all_products = Product.query.all()

        if not all_products:
            flash('لا توجد أصناف للتصدير', 'warning')
            return redirect(url_for('products'))

        # Create a DataFrame
        data = {
            'الكود': [],
            'الوصف': [],
            'السعر': [],
            'المورد': []
        }

        for product in all_products:
            data['الكود'].append(product.code)
            data['الوصف'].append(product.description)
            data['السعر'].append(product.price)
            data['المورد'].append(product.supplier)

        df = pd.DataFrame(data)

        # Create a response with Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='الأصناف')
        output.seek(0)

        # Create the response with proper headers
        response = Response(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=furniture_products.xlsx'

        return response

    except Exception as e:
        logger.error(f"Error exporting Excel: {str(e)}")
        flash(f'حدث خطأ أثناء تصدير الملف: {str(e)}', 'danger')
        return redirect(url_for('products'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)