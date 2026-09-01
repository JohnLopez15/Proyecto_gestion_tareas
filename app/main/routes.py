from datetime import datetime, timezone
from flask import render_template
from flask_login import login_required, current_user
from app.main import main_bp
from app.models import Task, TaskState, DailyLog, Project


@main_bp.route('/')
@login_required
def index():
    hoy = datetime.now(timezone.utc).date()
    jornada_hoy = DailyLog.query.filter_by(usuario_id=current_user.id, fecha=hoy).first()

    now_utc = datetime.now(timezone.utc)

    if current_user.rol == 'admin':
        tareas_pendientes = Task.query.filter_by(estado=TaskState.PENDIENTE.value).count()
        tareas_en_progreso = Task.query.filter_by(estado=TaskState.EN_PROGRESO.value).count()
        tareas_bloqueadas = Task.query.filter_by(estado=TaskState.BLOQUEADA.value).count()
        tareas_completadas = Task.query.filter_by(estado=TaskState.COMPLETADA.value).count()
        
        proximas_vencer = Task.query.filter(
            Task.fecha_limite.isnot(None),
            Task.fecha_limite < now_utc,
            Task.estado != TaskState.COMPLETADA.value
        ).all()
    else:
        tareas_pendientes = Task.query.filter_by(responsable_id=current_user.id, estado=TaskState.PENDIENTE.value).count()
        tareas_en_progreso = Task.query.filter_by(responsable_id=current_user.id, estado=TaskState.EN_PROGRESO.value).count()
        tareas_bloqueadas = Task.query.filter_by(responsable_id=current_user.id, estado=TaskState.BLOQUEADA.value).count()
        tareas_completadas = Task.query.filter_by(responsable_id=current_user.id, estado=TaskState.COMPLETADA.value).count()

        proximas_vencer = Task.query.filter(
            Task.responsable_id == current_user.id,
            Task.fecha_limite.isnot(None),
            Task.fecha_limite < now_utc,
            Task.estado != TaskState.COMPLETADA.value
        ).all()

    proyectos_activos = Project.query.filter_by(estado='Activo').limit(5).all()

    return render_template(
        'main/dashboard.html',
        jornada_hoy=jornada_hoy,
        tareas_pendientes=tareas_pendientes,
        tareas_en_progreso=tareas_en_progreso,
        tareas_bloqueadas=tareas_bloqueadas,
        tareas_completadas=tareas_completadas,
        proximas_vencer=proximas_vencer,
        proyectos_activos=proyectos_activos
    )

