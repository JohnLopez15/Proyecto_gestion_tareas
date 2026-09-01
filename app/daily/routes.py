from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.daily import daily_bp
from app.models import (
    DailyLog, DailyLogState, DailyLogTask, Task, TaskState,
    CommercialLog, UserRole, MacroTask, AuditLog
)
from app.projects.routes import registrar_auditoria


@daily_bp.route('/daily')
@login_required
def index():
    hoy = datetime.now(timezone.utc).date()
    jornada = DailyLog.query.filter_by(usuario_id=current_user.id, fecha=hoy).first()

    tareas_disponibles = Task.query.filter(
        Task.responsable_id == current_user.id,
        Task.estado != TaskState.COMPLETADA.value
    ).all()

    macrotareas = MacroTask.query.all()

    return render_template(
        'daily/index.html',
        jornada=jornada,
        tareas_disponibles=tareas_disponibles,
        macrotareas=macrotareas,
        hoy=hoy
    )


@daily_bp.route('/daily/start', methods=['POST'])
@login_required
def start_day():
    hoy = datetime.now(timezone.utc).date()
    jornada_existente = DailyLog.query.filter_by(usuario_id=current_user.id, fecha=hoy).first()

    if jornada_existente:
        flash('Ya tienes una jornada iniciada para el día de hoy.', 'info')
        return redirect(url_for('daily.index'))

    nueva_jornada = DailyLog(
        usuario_id=current_user.id,
        fecha=hoy,
        estado=DailyLogState.ABIERTA.value
    )
    db.session.add(nueva_jornada)
    db.session.flush()

    task_ids = request.form.getlist('task_ids', type=int)

    titulo_imprevista = request.form.get('titulo_imprevista', '').strip()
    macrotarea_imprevista_id = request.form.get('macrotarea_imprevista_id', type=int)

    if titulo_imprevista and macrotarea_imprevista_id:
        tarea_imp = Task(
            macrotarea_id=macrotarea_imprevista_id,
            creador_id=current_user.id,
            responsable_id=current_user.id,
            titulo=f"[Imprevista] {titulo_imprevista}",
            estado=TaskState.EN_PROGRESO.value,
            porcentaje_avance=0
        )
        db.session.add(tarea_imp)
        db.session.flush()
        task_ids.append(tarea_imp.id)

    for tid in task_ids:
        dt = DailyLogTask(jornada_id=nueva_jornada.id, tarea_id=tid)
        db.session.add(dt)

        t = db.session.get(Task, tid)
        if t and t.estado == TaskState.PENDIENTE.value:
            t.estado = TaskState.EN_PROGRESO.value

    db.session.commit()
    flash('¡Jornada iniciada con éxito! Ánimo con tus tareas del día.', 'success')
    return redirect(url_for('daily.index'))


@daily_bp.route('/daily/add-task', methods=['POST'])
@login_required
def add_task_to_day():
    hoy = datetime.now(timezone.utc).date()
    jornada = DailyLog.query.filter_by(usuario_id=current_user.id, fecha=hoy, estado=DailyLogState.ABIERTA.value).first()

    if not jornada:
        flash('No tienes una jornada abierta para hoy.', 'danger')
        return redirect(url_for('daily.index'))

    tarea_id = request.form.get('tarea_id', type=int)
    if tarea_id:
        ya_existe = DailyLogTask.query.filter_by(jornada_id=jornada.id, tarea_id=tarea_id).first()
        if not ya_existe:
            dt = DailyLogTask(jornada_id=jornada.id, tarea_id=tarea_id)
            db.session.add(dt)
            db.session.commit()
            flash('Tarea añadida a la jornada activa.', 'success')

    return redirect(url_for('daily.index'))


@daily_bp.route('/daily/close', methods=['POST'])
@login_required
def close_day():
    hoy = datetime.now(timezone.utc).date()
    jornada = DailyLog.query.filter_by(usuario_id=current_user.id, fecha=hoy, estado=DailyLogState.ABIERTA.value).first()

    if not jornada:
        flash('No se encontró una jornada abierta para cerrar hoy.', 'warning')
        return redirect(url_for('daily.index'))

    comentario_cierre = request.form.get('comentario_cierre', '').strip()
    if not comentario_cierre:
        flash('Es obligatorio dejar un comentario general de cierre del día.', 'danger')
        return redirect(url_for('daily.index'))

    for dt in jornada.tareas_dia:
        tarea = dt.tarea
        accion = request.form.get(f'resolucion_tarea_{tarea.id}')
        dt.porcentaje_al_cierre = tarea.porcentaje_avance

        if tarea.porcentaje_avance < 100:
            if not accion:
                flash(f'Debe seleccionar una acción de resolución para la tarea incompleta: "{tarea.titulo}".', 'danger')
                return redirect(url_for('daily.index'))

            dt.accion_resolucion = accion
            est_ant = tarea.estado

            if accion == 'reprogramar':
                if tarea.fecha_limite:
                    tarea.fecha_limite = tarea.fecha_limite + timedelta(days=1)
                registrar_auditoria(tarea.id, current_user.id, 'resolucion_diaria', 'En Progreso', 'Reprogramada para mañana')
            elif accion == 'backlog':
                tarea.estado = TaskState.PENDIENTE.value
                registrar_auditoria(tarea.id, current_user.id, 'estado', est_ant, 'Pendiente (Movidada a Backlog)')
            elif accion == 'cancelar':
                tarea.estado = TaskState.BLOQUEADA.value
                registrar_auditoria(tarea.id, current_user.id, 'estado', est_ant, 'Bloqueada/Cancelada')

    if current_user.rol == UserRole.COMERCIAL.value:
        llamadas = request.form.get('llamadas', type=int, default=0)
        whatsapp = request.form.get('whatsapp', type=int, default=0)
        linkedin = request.form.get('linkedin', type=int, default=0)
        correos = request.form.get('correos', type=int, default=0)
        ofertas = request.form.get('ofertas_enviadas', type=int, default=0)

        comm_log = CommercialLog.query.filter_by(jornada_id=jornada.id).first()
        if not comm_log:
            comm_log = CommercialLog(jornada_id=jornada.id)
            db.session.add(comm_log)

        comm_log.llamadas = llamadas
        comm_log.whatsapp = whatsapp
        comm_log.linkedin = linkedin
        comm_log.correos = correos
        comm_log.ofertas_enviadas = ofertas

    jornada.comentario_cierre = comentario_cierre
    jornada.estado = DailyLogState.CERRADA.value

    db.session.commit()
    flash('Jornada diaria cerrada exitosamente. ¡Excelente trabajo hoy!', 'success')
    return redirect(url_for('daily.index'))


@daily_bp.route('/daily/commercial/edit/<int:log_id>', methods=['POST'])
@login_required
def edit_commercial_log(log_id):
    comm_log = db.session.get(CommercialLog, log_id)
    if not comm_log:
        flash('Registro comercial no encontrado.', 'danger')
        return redirect(url_for('daily.index'))

    jornada = comm_log.jornada

    if current_user.rol != UserRole.ADMIN.value and jornada.usuario_id != current_user.id:
        flash('No tienes permiso para editar este registro comercial.', 'danger')
        return redirect(url_for('daily.index'))

    es_post_cierre = (jornada.estado == DailyLogState.CERRADA.value)

    v_ant = f"Llamadas:{comm_log.llamadas}, WA:{comm_log.whatsapp}, LinkedIn:{comm_log.linkedin}, Correos:{comm_log.correos}, Ofertas:{comm_log.ofertas_enviadas}"

    comm_log.llamadas = request.form.get('llamadas', type=int, default=comm_log.llamadas)
    comm_log.whatsapp = request.form.get('whatsapp', type=int, default=comm_log.whatsapp)
    comm_log.linkedin = request.form.get('linkedin', type=int, default=comm_log.linkedin)
    comm_log.correos = request.form.get('correos', type=int, default=comm_log.correos)
    comm_log.ofertas_enviadas = request.form.get('ofertas_enviadas', type=int, default=comm_log.ofertas_enviadas)

    v_nuev = f"Llamadas:{comm_log.llamadas}, WA:{comm_log.whatsapp}, LinkedIn:{comm_log.linkedin}, Correos:{comm_log.correos}, Ofertas:{comm_log.ofertas_enviadas}"

    if es_post_cierre and v_ant != v_nuev:
        audit = AuditLog(
            tarea_id=None,
            usuario_id=current_user.id,
            campo_modificado=f'CommercialLog (Jornada #{jornada.id})',
            valor_anterior=v_ant,
            valor_nuevo=v_nuev
        )
        db.session.add(audit)

    db.session.commit()
    flash('Registro comercial actualizado correctamente.', 'success')
    return redirect(url_for('daily.index'))

