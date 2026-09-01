from datetime import datetime
from flask import render_template, request
from flask_login import login_required
from app.reports import reports_bp
from app.models import User, UserRole, DailyLog, CommercialLog, Project, Task
from app.decorators import roles_required


@reports_bp.route('/reports')
@login_required
@roles_required(UserRole.ADMIN.value)
def index():
    usuario_id = request.args.get('usuario_id', type=int)
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')

    query_jornadas = DailyLog.query

    if usuario_id:
        query_jornadas = query_jornadas.filter(DailyLog.usuario_id == usuario_id)

    if fecha_inicio_str:
        try:
            f_ini = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            query_jornadas = query_jornadas.filter(DailyLog.fecha >= f_ini)
        except ValueError:
            pass

    if fecha_fin_str:
        try:
            f_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            query_jornadas = query_jornadas.filter(DailyLog.fecha <= f_fin)
        except ValueError:
            pass

    jornadas = query_jornadas.order_by(DailyLog.fecha.desc()).all()

    # Consolidado de métricas comerciales
    totales_comerciales = {
        'llamadas': 0,
        'whatsapp': 0,
        'linkedin': 0,
        'correos': 0,
        'ofertas_enviadas': 0
    }
    for j in jornadas:
        if j.registro_comercial:
            totales_comerciales['llamadas'] += j.registro_comercial.llamadas
            totales_comerciales['whatsapp'] += j.registro_comercial.whatsapp
            totales_comerciales['linkedin'] += j.registro_comercial.linkedin
            totales_comerciales['correos'] += j.registro_comercial.correos
            totales_comerciales['ofertas_enviadas'] += j.registro_comercial.ofertas_enviadas

    usuarios = User.query.order_by(User.nombre).all()
    proyectos = Project.query.order_by(Project.nombre).all()

    return render_template(
        'reports/index.html',
        jornadas=jornadas,
        totales_comerciales=totales_comerciales,
        usuarios=usuarios,
        proyectos=proyectos,
        usuario_id_sel=usuario_id,
        fecha_inicio_sel=fecha_inicio_str or '',
        fecha_fin_sel=fecha_fin_str or ''
    )

