# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import uuid
import os
import hashlib
import vobject
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

UPLOAD_FOLDER = '/home/rezamahdavi/static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== مدل کاربر ==========
class User(UserMixin):
    def __init__(self, id, name, email, password, role='user'):
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if user:
        conn.close()
        return User(user['id'], user['name'], user['email'], user['password'], 'user')
    admin = conn.execute('SELECT * FROM admins WHERE id=?', (user_id,)).fetchone()
    conn.close()
    if admin:
        return User(admin['id'], admin['username'], admin['username'], admin['password'], 'admin')
    return None

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('دسترسی غیرمجاز!', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== مقداردهی اولیه دیتابیس ==========
def init_db():
    conn = sqlite3.connect('database.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        logo TEXT,
        job_title TEXT,
        description TEXT,
        phone TEXT,
        email_show TEXT,
        website TEXT,
        whatsapp TEXT,
        telegram TEXT,
        instagram TEXT,
        address TEXT,
        location TEXT,
        bio TEXT,
        theme TEXT DEFAULT 'modern',
        bg_style TEXT DEFAULT 'bg-1',
        status TEXT DEFAULT 'pending',
        views INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS gallery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        image_path TEXT,
        caption TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS admins (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        rating INTEGER,
        comment TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    admin_exists = conn.execute('SELECT * FROM admins WHERE username=?', ('admin',)).fetchone()
    if not admin_exists:
        conn.execute('INSERT INTO admins (id, username, password) VALUES (?, ?, ?)',
                     (str(uuid.uuid4())[:8], 'admin', hash_password('admin123')))
    conn.close()

init_db()

# ========== مسیرهای اصلی ==========
@app.route('/')
def index():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    stories = conn.execute('''SELECT s.*, u.name, u.logo 
                              FROM stories s 
                              JOIN users u ON s.user_id = u.id 
                              WHERE s.expires_at > datetime('now') 
                              ORDER BY s.created_at DESC''').fetchall()
    conn.close()
    return render_template('index.html', stories=stories)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/users')
def users_list():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    all_users = conn.execute('SELECT id, name, job_title, logo FROM users WHERE status="approved"').fetchall()
    conn.close()
    return render_template('users_list.html', users=all_users)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_id = str(uuid.uuid4())[:8]
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = hash_password(request.form.get('password', ''))
        if not name or not email or not password:
            return "همه فیلدها الزامی هستند"
        conn = sqlite3.connect('database.db')
        try:
            conn.execute('INSERT INTO users (id, name, email, password) VALUES (?, ?, ?, ?)',
                         (user_id, name, email, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return "ایمیل قبلاً ثبت شده است"
        finally:
            conn.close()
        flash('ثبت‌نام با موفقیت انجام شد. منتظر تایید ادمین باشید.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = hash_password(request.form.get('password', ''))
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        user = conn.execute('SELECT * FROM users WHERE email=? AND password=?', (email, password)).fetchone()
        conn.close()
        if user:
            login_user(User(user['id'], user['name'], user['email'], user['password'], 'user'))
            return redirect(url_for('dashboard'))
        flash('ایمیل یا رمز عبور اشتباه است', 'danger')
        return render_template('login.html')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE id=?', (current_user.id,)).fetchone()
    conn.close()
    return render_template('dashboard.html', user=user)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        job_title = request.form.get('job_title', '').strip()
        bio = request.form.get('bio', '').strip()
        description = request.form.get('description', '').strip()
        phone = request.form.get('phone', '').strip()
        email_show = request.form.get('email_show', '').strip()
        website = request.form.get('website', '').strip()
        whatsapp = request.form.get('whatsapp', '').strip()
        telegram = request.form.get('telegram', '').strip()
        instagram = request.form.get('instagram', '').strip()
        address = request.form.get('address', '').strip()
        location = request.form.get('location', '').strip()
        theme = request.form.get('theme', 'modern')
        bg_style = request.form.get('bg_style', 'bg-1')
        
        logo = request.files.get('logo')
        logo_filename = None
        if logo and logo.filename:
            logo_filename = f"{uuid.uuid4()}_{secure_filename(logo.filename)}"
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'], logo_filename))
            conn = sqlite3.connect('database.db')
            old_logo = conn.execute('SELECT logo FROM users WHERE id=?', (current_user.id,)).fetchone()
            if old_logo and old_logo[0]:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_logo[0]))
                except:
                    pass
            conn.close()
        
        conn = sqlite3.connect('database.db')
        if logo_filename:
            conn.execute('''UPDATE users SET 
                name=?, job_title=?, bio=?, description=?, phone=?, email_show=?,
                website=?, whatsapp=?, telegram=?, instagram=?,
                address=?, location=?, theme=?, bg_style=?, logo=?
                WHERE id=?''',
                (name, job_title, bio, description, phone, email_show,
                 website, whatsapp, telegram, instagram,
                 address, location, theme, bg_style, logo_filename, current_user.id))
        else:
            conn.execute('''UPDATE users SET 
                name=?, job_title=?, bio=?, description=?, phone=?, email_show=?,
                website=?, whatsapp=?, telegram=?, instagram=?,
                address=?, location=?, theme=?, bg_style=?
                WHERE id=?''',
                (name, job_title, bio, description, phone, email_show,
                 website, whatsapp, telegram, instagram,
                 address, location, theme, bg_style, current_user.id))
        conn.commit()
        conn.close()
        flash('اطلاعات با موفقیت ذخیره شد', 'success')
        return redirect(url_for('dashboard'))
    
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE id=?', (current_user.id,)).fetchone()
    conn.close()
    return render_template('edit_profile.html', user=user)

@app.route('/gallery_manage', methods=['GET', 'POST'])
@login_required
def gallery_manage():
    if request.method == 'POST':
        files = request.files.getlist('images')
        for file in files:
            if file and file.filename:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                conn = sqlite3.connect('database.db')
                conn.execute('INSERT INTO gallery (user_id, image_path) VALUES (?, ?)',
                             (current_user.id, filename))
                conn.commit()
                conn.close()
        flash('تصاویر با موفقیت آپلود شدند', 'success')
        return redirect(url_for('gallery_manage'))
    
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    images = conn.execute('SELECT * FROM gallery WHERE user_id=?', (current_user.id,)).fetchall()
    conn.close()
    return render_template('gallery_manage.html', images=images)

@app.route('/delete_gallery/<int:image_id>')
@login_required
def delete_gallery(image_id):
    conn = sqlite3.connect('database.db')
    image = conn.execute('SELECT image_path FROM gallery WHERE id=? AND user_id=?', 
                         (image_id, current_user.id)).fetchone()
    if image:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image[0]))
        except:
            pass
        conn.execute('DELETE FROM gallery WHERE id=?', (image_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('gallery_manage'))

@app.route('/gallery/<user_id>')
def user_gallery(user_id):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT name FROM users WHERE id=?', (user_id,)).fetchone()
    images = conn.execute('SELECT * FROM gallery WHERE user_id=?', (user_id,)).fetchall()
    conn.close()
    if not user:
        return "کاربر پیدا نشد", 404
    return render_template('user_gallery.html', user=user, images=images)

@app.route('/qr/<user_id>')
def generate_qr(user_id):
    base_url = request.host_url.rstrip('/')
    card_url = f"{base_url}/profile/{user_id}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(card_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

@app.route('/profile/<user_id>')
def profile(user_id):
    conn = sqlite3.connect('database.db')
    conn.execute('UPDATE users SET views = views + 1 WHERE id=?', (user_id,))
    conn.commit()
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE id=? AND status="approved"', (user_id,)).fetchone()
    images = conn.execute('SELECT * FROM gallery WHERE user_id=?', (user_id,)).fetchall()
    conn.close()
    if user:
        theme = user['theme'] or 'modern'
        try:
            return render_template(f'themes/{theme}.html', user=user, images=images)
        except:
            return render_template('themes/modern.html', user=user, images=images)
    return "کارت ویزیت پیدا نشد. ممکن است در حال بررسی باشد.", 404

@app.route('/download_vcard/<user_id>')
def download_vcard(user_id):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    conn.close()
    if not user:
        return "کاربر پیدا نشد", 404
    vcard = vobject.vCard()
    vcard.add('fn').value = user['name']
    if user['phone']:
        tel = vcard.add('tel')
        tel.value = user['phone']
        tel.type_param = 'CELL'
    if user['email_show']:
        email = vcard.add('email')
        email.value = user['email_show']
        email.type_param = 'WORK'
    if user['website']:
        url = vcard.add('url')
        url.value = user['website']
    vcard_file = f"static/{user_id}.vcf"
    with open(vcard_file, 'w', encoding='utf-8') as f:
        f.write(vcard.serialize())
    return send_file(vcard_file, as_attachment=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/submit_review', methods=['POST'])
def submit_review():
    user_id = request.form.get('user_id')
    rating = request.form.get('rating')
    comment = request.form.get('comment', '').strip()
    if not user_id or not rating:
        return "اطلاعات ناقص است", 400
    conn = sqlite3.connect('database.db')
    conn.execute('INSERT INTO reviews (user_id, rating, comment) VALUES (?, ?, ?)',
                 (user_id, rating, comment))
    conn.commit()
    conn.close()
    flash('نظر شما با موفقیت ثبت شد و پس از تایید نمایش داده خواهد شد', 'success')
    return redirect(url_for('profile', user_id=user_id))

# ========== پنل ادمین ==========
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = hash_password(request.form.get('password', ''))
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        admin = conn.execute('SELECT * FROM admins WHERE username=? AND password=?', (username, password)).fetchone()
        conn.close()
        if admin:
            login_user(User(admin['id'], admin['username'], admin['username'], admin['password'], 'admin'))
            return redirect(url_for('admin_dashboard'))
        flash('نام کاربری یا رمز عبور اشتباه است', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    pending_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE status="pending"').fetchone()['count']
    approved_users = conn.execute('SELECT COUNT(*) as count FROM users WHERE status="approved"').fetchone()['count']
    total_views = conn.execute('SELECT SUM(views) as total FROM users').fetchone()['total'] or 0
    total_reviews = conn.execute('SELECT COUNT(*) as count FROM reviews').fetchone()['count']
    conn.close()
    return render_template('admin_dashboard.html', 
                         total_users=total_users,
                         pending_users=pending_users,
                         approved_users=approved_users,
                         total_views=total_views,
                         total_reviews=total_reviews)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/approve/<user_id>')
@login_required
@admin_required
def admin_approve(user_id):
    conn = sqlite3.connect('database.db')
    conn.execute('UPDATE users SET status="approved" WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('کارت ویزیت با موفقیت تایید شد', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/reject/<user_id>')
@login_required
@admin_required
def admin_reject(user_id):
    conn = sqlite3.connect('database.db')
    conn.execute('UPDATE users SET status="rejected" WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('کارت ویزیت رد شد', 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/delete/<user_id>')
@login_required
@admin_required
def admin_delete(user_id):
    conn = sqlite3.connect('database.db')
    images = conn.execute('SELECT image_path FROM gallery WHERE user_id=?', (user_id,)).fetchall()
    for img in images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img[0]))
        except:
            pass
    conn.execute('DELETE FROM gallery WHERE user_id=?', (user_id,))
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('کاربر با موفقیت حذف شد', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/reviews')
@login_required
@admin_required
def admin_reviews():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    reviews = conn.execute('''SELECT r.*, u.name as user_name 
                              FROM reviews r 
                              LEFT JOIN users u ON r.user_id = u.id 
                              ORDER BY r.created_at DESC''').fetchall()
    conn.close()
    return render_template('admin_reviews.html', reviews=reviews)

@app.route('/admin/review/approve/<int:review_id>')
@login_required
@admin_required
def admin_review_approve(review_id):
    conn = sqlite3.connect('database.db')
    conn.execute('UPDATE reviews SET status="approved" WHERE id=?', (review_id,))
    conn.commit()
    conn.close()
    flash('نظر با موفقیت تایید شد', 'success')
    return redirect(url_for('admin_reviews'))

@app.route('/admin/review/delete/<int:review_id>')
@login_required
@admin_required
def admin_review_delete(review_id):
    conn = sqlite3.connect('database.db')
    conn.execute('DELETE FROM reviews WHERE id=?', (review_id,))
    conn.commit()
    conn.close()
    flash('نظر با موفقیت حذف شد', 'success')
    return redirect(url_for('admin_reviews'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)