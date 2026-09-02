from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.daily import daily_bp
from app.models import (
    DailyLog, DailyLogState, DailyLogTask, Task, TaskState,
    CommercialLog, UserRole, MacroTask, AuditLog, Project, User, TaskComment
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

    proyectos = Project.query.order_by(Project.nombre).all()
    macrotareas = MacroTask.query.all()

    return render_template(
        'daily/index.html',
        jornada=jornada,
        tareas_disponibles=tareas_disponibles,
        proyectos=proyectos,
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

    if titulo_imprevista:
        tarea_imp = Task(
            macrotarea_id=macrotarea_imprevista_id if macrotarea_imprevista_id else None,
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

    # 1. Validar que cada tarea tenga su comentario obligatorio
    for dt in jornada.tareas_dia:
        tarea = dt.tarea
        comentario_tarea = request.form.get(f'comentario_tarea_{tarea.id}', '').strip()
        if not comentario_tarea:
            flash(f'Es obligatorio ingresar un comentario de cierre para la tarea "{tarea.titulo}".', 'danger')
            return redirect(url_for('daily.index'))

    # 2. Procesar actualización de tareas existentes
    for dt in jornada.tareas_dia:
        tarea = dt.tarea
        comentario_tarea = request.form.get(f'comentario_tarea_{tarea.id}', '').strip()
        completar_directo = request.form.get(f'completar_tarea_{tarea.id}')

        # Actualizar checklists si se modificaron desde el modal de cierre
        if tarea.checklists:
            for item in tarea.checklists:
                esta_marcado = True if request.form.get(f'checklist_item_{item.id}') else False
                item.completado = esta_marcado
            tarea.recalcular_porcentaje()

        if completar_directo:
            tarea.porcentaje_avance = 100
            tarea.estado = TaskState.COMPLETADA.value
            for item in tarea.checklists:
                item.completado = True

        dt.porcentaje_al_cierre = tarea.porcentaje_avance
        dt.comentario = comentario_tarea

        # Guardar comentario en el historial permanente de la tarea
        task_comment = TaskComment(
            tarea_id=tarea.id,
            usuario_id=current_user.id,
            comentario=f"[Cierre Jornada {hoy.strftime('%Y-%m-%d')}]: {comentario_tarea}"
        )
        db.session.add(task_comment)

        # Si no llegó al 100%, procesar resolución
        if tarea.porcentaje_avance < 100:
            accion = request.form.get(f'resolucion_tarea_{tarea.id}')
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

    # 3. Procesar tarea imprevista al momento de finalizar jornada si fue provista
    titulo_imprevista_cierre = request.form.get('titulo_imprevista_cierre', '').strip()
    if titulo_imprevista_cierre:
        macrotarea_cierre_id = request.form.get('macrotarea_imprevista_cierre_id', type=int)
        completar_imp = True if request.form.get('completada_imprevista_cierre') else False
        pct_imp = 100 if completar_imp else request.form.get('porcentaje_imprevista_cierre', type=int, default=100)
        comentario_imp = request.form.get('comentario_imprevista_cierre', '').strip() or 'Tarea imprevista realizada y finalizada en la jornada.'

        tarea_imp = Task(
            macrotarea_id=macrotarea_cierre_id if macrotarea_cierre_id else None,
            creador_id=current_user.id,
            responsable_id=current_user.id,
            titulo=f"[Imprevista] {titulo_imprevista_cierre}",
            estado=TaskState.COMPLETADA.value if pct_imp == 100 else TaskState.EN_PROGRESO.value,
            porcentaje_avance=pct_imp
        )
        db.session.add(tarea_imp)
        db.session.flush()

        dt_imp = DailyLogTask(
            jornada_id=jornada.id,
            tarea_id=tarea_imp.id,
            porcentaje_al_cierre=pct_imp,
            comentario=comentario_imp,
            accion_resolucion='reprogramar' if pct_imp < 100 else None
        )
        db.session.add(dt_imp)

        task_comment_imp = TaskComment(
            tarea_id=tarea_imp.id,
            usuario_id=current_user.id,
            comentario=f"[Cierre Jornada {hoy.strftime('%Y-%m-%d')}]: {comentario_imp}"
        )
        db.session.add(task_comment_imp)

    # 4. Procesar registro comercial si corresponde
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

    jornada.comentario_cierre = "Jornada cerrada con comentarios por tarea."
    jornada.estado = DailyLogState.CERRADA.value

    db.session.commit()
    flash('Jornada diaria cerrada exitosamente con los comentarios registrados en cada tarea.', 'success')
    return redirect(url_for('daily.index'))


@daily_bp.route('/daily/activity')
@login_required
def activity_viewer():
    fecha_str = request.args.get('fecha')
    usuario_id = request.args.get('usuario_id', type=int)

    if fecha_str:
        try:
            fecha_sel = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_sel = datetime.now(timezone.utc).date()
    else:
        fecha_sel = datetime.now(timezone.utc).date()

    query = DailyLog.query.filter_by(fecha=fecha_sel)
    if usuario_id:
        query = query.filter_by(usuario_id=usuario_id)

    jornadas = query.order_by(DailyLog.usuario_id).all()
    usuarios = User.query.order_by(User.nombre).all()

    return render_template(
        'daily/activity.html',
        jornadas=jornadas,
        usuarios=usuarios,
        fecha_sel=fecha_sel.strftime('%Y-%m-%d'),
        usuario_id_sel=usuario_id
    )


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

