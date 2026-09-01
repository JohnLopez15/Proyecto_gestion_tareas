from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def roles_required(*roles):
    """
    Decorador para restringir el acceso a rutas según el rol del usuario autenticado.
    Uso: @roles_required('admin') o @roles_required('admin', 'comercial')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.rol not in roles:
                flash('No tienes permisos suficientes para acceder a esta sección.', 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

