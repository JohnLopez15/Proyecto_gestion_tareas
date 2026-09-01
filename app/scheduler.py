from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta

scheduler = BackgroundScheduler()


def check_task_deadlines(app):
    """
    Job en segundo plano que verifica tareas con fecha límite cercana (próximas 24 horas)
    y genera notificaciones in-app.
    """
    with app.app_context():
        from app.models import Task, Notification, NotificationType, db
        
        ahora = datetime.now(timezone.utc)
        limite = ahora + timedelta(hours=24)
        
        tareas_proximas = Task.query.filter(
            Task.fecha_limite.isnot(None),
            Task.fecha_limite > ahora,
            Task.fecha_limite <= limite,
            Task.estado.in_(['Pendiente', 'En Progreso'])
        ).all()

        for tarea in tareas_proximas:
            if tarea.responsable_id:
                mensaje = f"Alerta: La tarea '{tarea.titulo}' vence pronto ({tarea.fecha_limite.strftime('%Y-%m-%d %H:%M')})."
                notif_existente = Notification.query.filter_by(
                    usuario_id=tarea.responsable_id,
                    tipo=NotificationType.ALARMA_FECHA.value,
                    mensaje=mensaje
                ).first()

                if not notif_existente:
                    nueva_notif = Notification(
                        usuario_id=tarea.responsable_id,
                        mensaje=mensaje,
                        tipo=NotificationType.ALARMA_FECHA.value
                    )
                    db.session.add(nueva_notif)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def init_scheduler(app):
    if not scheduler.running:
        scheduler.add_job(
            func=check_task_deadlines,
            args=[app],
            trigger="interval",
            minutes=15,
            id="check_deadlines_job",
            replace_existing=True
        )
        scheduler.start()

