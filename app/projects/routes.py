from datetime import datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.projects import projects_bp
from app.models import (
    Project, MacroTask, Task, Checklist, User, AuditLog,
    Notification, NotificationType, TaskState
)


def registrar_auditoria(tarea_id, usuario_id, campo, valor_ant, valor_nuev):
    """Registra una entrada silenciosa en AuditLog si hubo un cambio real."""
    str_ant = str(valor_ant) if valor_ant is not None else ''
    str_nuev = str(valor_nuev) if valor_nuev is not None else ''
    if str_ant != str_nuev:
        audit = AuditLog(
            tarea_id=tarea_id,
            usuario_id=usuario_id,
            campo_modificado=campo,
            valor_anterior=str_ant,
            valor_nuevo=str_nuev
        )
        db.session.add(audit)


@projects_bp.route('/projects', methods=['GET', 'POST'])
@login_required
def list_projects():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        estado = request.form.get('estado', 'Activo')

        if not nombre:
            flash('El nombre del proyecto es obligatorio.', 'danger')
        else:
            proyecto = Project(nombre=nombre, descripcion=descripcion, estado=estado)
            db.session.add(proyecto)
            db.session.commit()
            flash(f'Proyecto "{nombre}" creado exitosamente.', 'success')
            return redirect(url_for('projects.list_projects'))

    proyectos = Project.query.order_by(Project.fecha_creacion.desc()).all()
    return render_template('projects/list.html', proyectos=proyectos)


@projects_bp.route('/projects/<int:project_id>')
@login_required
def detail_project(project_id):
    proyecto = Project.query.get_or_404(project_id)
    usuarios = User.query.order_by(User.nombre).all()
    estados_tarea = [e.value for e in TaskState]
    return render_template('projects/detail.html', proyecto=proyecto, usuarios=usuarios, estados_tarea=estados_tarea)


@projects_bp.route('/projects/<int:project_id>/macrotask', methods=['POST'])
@login_required
def create_macrotask(project_id):
    proyecto = Project.query.get_or_404(project_id)
    nombre = request.form.get('nombre', '').strip()
    if nombre:
        macrotarea = MacroTask(proyecto_id=proyecto.id, nombre=nombre)
        db.session.add(macrotarea)
        db.session.commit()
        flash(f'Macrotarea "{nombre}" agregada.', 'success')
    else:
        flash('El nombre de la macrotarea no puede estar vacío.', 'danger')
    return redirect(url_for('projects.detail_project', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/task', methods=['POST'])
@login_required
def create_task(project_id):
    proyecto = Project.query.get_or_404(project_id)
    macrotarea_id = request.form.get('macrotarea_id', type=int)
    titulo = request.form.get('titulo', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    responsable_id = request.form.get('responsable_id', type=int)
    fecha_limite_str = request.form.get('fecha_limite')

    if not macrotarea_id or not titulo:
        flash('Debe seleccionar una macrotarea y especificar el título.', 'danger')
        return redirect(url_for('projects.detail_project', project_id=project_id))

    fecha_limite = None
    if fecha_limite_str:
        try:
            fecha_limite = datetime.strptime(fecha_limite_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            try:
                fecha_limite = datetime.strptime(fecha_limite_str, '%Y-%m-%d')
            except ValueError:
                pass

    tarea = Task(
        macrotarea_id=macrotarea_id,
        creador_id=current_user.id,
        responsable_id=responsable_id if responsable_id else None,
        titulo=titulo,
        descripcion=descripcion,
        fecha_limite=fecha_limite
    )
    db.session.add(tarea)
    db.session.flush()  # Obtener tarea.id

    if responsable_id and responsable_id != current_user.id:
        notif = Notification(
            usuario_id=responsable_id,
            mensaje=f'Se te ha asignado la tarea "{tarea.titulo}".',
            tipo=NotificationType.ASIGNACION.value
        )
        db.session.add(notif)

    db.session.commit()
    flash(f'Tarea "{titulo}" creada exitosamente.', 'success')
    return redirect(url_for('projects.detail_project', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/kanban')
@login_required
def kanban_project(project_id):
    proyecto = Project.query.get_or_404(project_id)
    macrotareas = MacroTask.query.filter_by(proyecto_id=project_id).all()
    tareas_por_estado = {
        TaskState.PENDIENTE.value: [],
        TaskState.EN_PROGRESO.value: [],
        TaskState.BLOQUEADA.value: [],
        TaskState.COMPLETADA.value: []
    }
    for mt in macrotareas:
        for t in mt.tareas:
            if t.estado in tareas_por_estado:
                tareas_por_estado[t.estado].append(t)
            else:
                tareas_por_estado[TaskState.PENDIENTE.value].append(t)

    return render_template('projects/kanban.html', proyecto=proyecto, tareas_por_estado=tareas_por_estado)


@projects_bp.route('/task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def detail_task(task_id):
    tarea = Task.query.get_or_404(task_id)
    usuarios = User.query.order_by(User.nombre).all()
    estados = [e.value for e in TaskState]

    if request.method == 'POST':
        nuevo_titulo = request.form.get('titulo', '').strip()
        nueva_descripcion = request.form.get('descripcion', '').strip()
        nuevo_estado = request.form.get('estado')
        nuevo_responsable_id = request.form.get('responsable_id', type=int)
        fecha_limite_str = request.form.get('fecha_limite')
        porcentaje_manual_str = request.form.get('porcentaje_avance')
        comentario_justificacion = request.form.get('comentario_justificacion', '').strip()

        # Auditar cambio de estado
        if nuevo_estado and nuevo_estado != tarea.estado:
            registrar_auditoria(tarea.id, current_user.id, 'estado', tarea.estado, nuevo_estado)
            tarea.estado = nuevo_estado

        # Auditar cambio de responsable
        if nuevo_responsable_id != tarea.responsable_id:
            resp_ant = User.query.get(tarea.responsable_id).nombre if tarea.responsable_id else 'Sin Asignar'
            resp_nuev = User.query.get(nuevo_responsable_id).nombre if nuevo_responsable_id else 'Sin Asignar'
            registrar_auditoria(tarea.id, current_user.id, 'responsable_id', resp_ant, resp_nuev)

            if nuevo_responsable_id and nuevo_responsable_id != current_user.id:
                notif = Notification(
                    usuario_id=nuevo_responsable_id,
                    mensaje=f'Se te ha asignado la tarea "{tarea.titulo}".',
                    tipo=NotificationType.ASIGNACION.value
                )
                db.session.add(notif)
            tarea.responsable_id = nuevo_responsable_id if nuevo_responsable_id else None

        # Auditar cambio de fecha limite
        nueva_fecha = None
        if fecha_limite_str:
            try:
                nueva_fecha = datetime.strptime(fecha_limite_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    nueva_fecha = datetime.strptime(fecha_limite_str, '%Y-%m-%d')
                except ValueError:
                    pass

        if nueva_fecha != tarea.fecha_limite:
            f_ant = tarea.fecha_limite.strftime('%Y-%m-%d %H:%M') if tarea.fecha_limite else 'Sin fecha'
            f_nuev = nueva_fecha.strftime('%Y-%m-%d %H:%M') if nueva_fecha else 'Sin fecha'
            registrar_auditoria(tarea.id, current_user.id, 'fecha_limite', f_ant, f_nuev)
            tarea.fecha_limite = nueva_fecha

        # Avance manual con justificación obligatoria
        if porcentaje_manual_str is not None and porcentaje_manual_str != '':
            nuevo_porcentaje = int(porcentaje_manual_str)
            total_items = len(tarea.checklists)
            porcentaje_calculado = int((sum(1 for c in tarea.checklists if c.completado) / total_items) * 100) if total_items > 0 else tarea.porcentaje_avance

            if total_items > 0 and nuevo_porcentaje != porcentaje_calculado and not comentario_justificacion:
                flash('El porcentaje manual difiere del cálculo del checklist. Debe ingresar un comentario de justificación.', 'danger')
                return render_template('projects/task_detail.html', tarea=tarea, usuarios=usuarios, estados=estados)

            if nuevo_porcentaje != tarea.porcentaje_avance:
                just = f" [Justificación: {comentario_justificacion}]" if comentario_justificacion else ""
                registrar_auditoria(
                    tarea.id, current_user.id, 'porcentaje_avance',
                    f"{tarea.porcentaje_avance}%", f"{nuevo_porcentaje}%{just}"
                )
                tarea.porcentaje_avance = nuevo_porcentaje
                if nuevo_porcentaje == 100:
                    tarea.estado = TaskState.COMPLETADA.value

        tarea.titulo = nuevo_titulo
        tarea.descripcion = nueva_descripcion
        db.session.commit()
        flash('Tarea actualizada correctamente.', 'success')
        return redirect(url_for('projects.detail_task', task_id=task_id))

    auditorias = AuditLog.query.filter_by(tarea_id=task_id).order_by(AuditLog.fecha.desc()).all()
    return render_template('projects/task_detail.html', tarea=tarea, usuarios=usuarios, estados=estados, auditorias=auditorias)


@projects_bp.route('/task/<int:task_id>/checklist', methods=['POST'])
@login_required
def add_checklist_item(task_id):
    tarea = Task.query.get_or_404(task_id)
    descripcion = request.form.get('descripcion', '').strip()
    if descripcion:
        item = Checklist(tarea_id=tarea.id, descripcion=descripcion, completado=False)
        db.session.add(item)
        db.session.flush()
        pct_ant = tarea.porcentaje_avance
        pct_nuev = tarea.recalcular_porcentaje()
        if pct_ant != pct_nuev:
            registrar_auditoria(tarea.id, current_user.id, 'porcentaje_avance', f"{pct_ant}%", f"{pct_nuev}% (Auto por Checklist)")
        db.session.commit()
        flash('Ítem de checklist añadido.', 'success')
    return redirect(url_for('projects.detail_task', task_id=task_id))

