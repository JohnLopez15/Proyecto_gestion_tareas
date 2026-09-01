from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.auth import auth_bp
from app.models import User, UserRole
from app.decorators import roles_required


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Credenciales inválidas. Por favor verifica tu email y contraseña.', 'danger')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        flash(f'¡Bienvenido de nuevo, {user.nombre}!', 'success')
        return redirect(next_page or url_for('main.index'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/admin/users', methods=['GET', 'POST'])
@login_required
@roles_required(UserRole.ADMIN.value)
def manage_users():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        rol = request.form.get('rol', UserRole.DESARROLLADOR.value)

        if not nombre or not email or not password:
            flash('Todos los campos son obligatorios.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Ya existe un usuario registrado con este correo electrónico.', 'warning')
        else:
            nuevo_usuario = User(
                nombre=nombre,
                email=email,
                rol=rol
            )
            nuevo_usuario.set_password(password)
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash(f'Usuario {nombre} registrado exitosamente.', 'success')
            return redirect(url_for('auth.manage_users'))

    usuarios = User.query.order_by(User.nombre).all()
    roles = [role.value for role in UserRole]
    return render_template('auth/users.html', usuarios=usuarios, roles=roles)


@auth_bp.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@login_required
@roles_required(UserRole.ADMIN.value)
def edit_user(user_id):
    usuario = User.query.get_or_404(user_id)
    nombre = request.form.get('nombre', '').strip()
    rol = request.form.get('rol')
    nueva_password = request.form.get('password', '')

    if nombre:
        usuario.nombre = nombre
    if rol and rol in [r.value for r in UserRole]:
        usuario.rol = rol
    if nueva_password:
        usuario.set_password(nueva_password)

    db.session.commit()
    flash(f'Usuario {usuario.nombre} actualizado correctamente.', 'success')
    return redirect(url_for('auth.manage_users'))

