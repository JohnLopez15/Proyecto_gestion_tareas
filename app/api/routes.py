from flask import jsonify, request
from flask_login import login_required, current_user
from app import db
from app.api import api_bp
from app.models import Task, Checklist, Notification, TaskState
from app.projects.routes import registrar_auditoria


@api_bp.route('/task/<int:task_id>/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def toggle_checklist_item(task_id, item_id):
    tarea = Task.query.get_or_404(task_id)
    item = Checklist.query.filter_by(id=item_id, tarea_id=task_id).first_or_404()

    item.completado = not item.completado
    db.session.flush()

    pct_ant = tarea.porcentaje_avance
    est_ant = tarea.estado

    nuevo_porcentaje = tarea.recalcular_porcentaje()

    if pct_ant != nuevo_porcentaje:
        registrar_auditoria(
            tarea.id, current_user.id, 'porcentaje_avance',
            f"{pct_ant}%", f"{nuevo_porcentaje}% (Auto por Checklist)"
        )
    if est_ant != tarea.estado:
        registrar_auditoria(
            tarea.id, current_user.id, 'estado',
            est_ant, tarea.estado
        )

    db.session.commit()

    return jsonify({
        'success': True,
        'item_id': item.id,
        'completado': item.completado,
        'nuevo_porcentaje': nuevo_porcentaje,
        'nuevo_estado': tarea.estado
    })


@api_bp.route('/task/<int:task_id>/checklist/add', methods=['POST'])
@login_required
def add_checklist_item_ajax(task_id):
    tarea = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    descripcion = data.get('descripcion', '').strip()

    if not descripcion:
        return jsonify({'success': False, 'error': 'La descripción es obligatoria.'}), 400

    item = Checklist(tarea_id=tarea.id, descripcion=descripcion, completado=False)
    db.session.add(item)
    db.session.flush()

    pct_ant = tarea.porcentaje_avance
    nuevo_porcentaje = tarea.recalcular_porcentaje()

    if pct_ant != nuevo_porcentaje:
        registrar_auditoria(
            tarea.id, current_user.id, 'porcentaje_avance',
            f"{pct_ant}%", f"{nuevo_porcentaje}% (Auto por Checklist)"
        )

    db.session.commit()

    return jsonify({
        'success': True,
        'item': {
            'id': item.id,
            'descripcion': item.descripcion,
            'completado': item.completado
        },
        'nuevo_porcentaje': nuevo_porcentaje,
        'nuevo_estado': tarea.estado
    })


@api_bp.route('/task/<int:task_id>/checklist/<int:item_id>', methods=['DELETE'])
@login_required
def delete_checklist_item_ajax(task_id, item_id):
    tarea = Task.query.get_or_404(task_id)
    item = Checklist.query.filter_by(id=item_id, tarea_id=task_id).first_or_404()

    db.session.delete(item)
    db.session.flush()

    pct_ant = tarea.porcentaje_avance
    nuevo_porcentaje = tarea.recalcular_porcentaje()

    if pct_ant != nuevo_porcentaje:
        registrar_auditoria(
            tarea.id, current_user.id, 'porcentaje_avance',
            f"{pct_ant}%", f"{nuevo_porcentaje}% (Auto por Checklist)"
        )

    db.session.commit()

    return jsonify({
        'success': True,
        'nuevo_porcentaje': nuevo_porcentaje,
        'nuevo_estado': tarea.estado
    })


@api_bp.route('/notifications/unread', methods=['GET'])
@login_required
def get_unread_notifications():
    notifs = Notification.query.filter_by(
        usuario_id=current_user.id,
        leida=False
    ).order_by(Notification.fecha_creacion.desc()).all()

    data = [{
        'id': n.id,
        'mensaje': n.mensaje,
        'tipo': n.tipo,
        'fecha': n.fecha_creacion.strftime('%Y-%m-%d %H:%M')
    } for n in notifs]

    return jsonify({
        'unread_count': len(data),
        'notifications': data
    })


@api_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, usuario_id=current_user.id).first_or_404()
    notif.leida = True
    db.session.commit()

    return jsonify({'success': True, 'id': notif_id})


@api_bp.route('/tasks/search', methods=['GET'])
@login_required
def search_tasks():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'tasks': []})

    tareas = Task.query.filter(
        Task.responsable_id == current_user.id,
        Task.estado != TaskState.COMPLETADA.value,
        Task.titulo.ilike(f'%{query}%')
    ).limit(10).all()

    results = [{
        'id': t.id,
        'titulo': t.titulo,
        'estado': t.estado,
        'porcentaje': t.porcentaje_avance,
        'macrotarea': t.macrotarea.nombre if t.macrotarea else ''
    } for t in tareas]

    return jsonify({'tasks': results})

