from datetime import datetime, timezone
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db, login_manager


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_date():
    return datetime.now(timezone.utc).date()


class UserRole(str, Enum):
    ADMIN = 'admin'
    DESARROLLADOR = 'desarrollador'
    COMERCIAL = 'comercial'


class TaskState(str, Enum):
    PENDIENTE = 'Pendiente'
    EN_PROGRESO = 'En Progreso'
    BLOQUEADA = 'Bloqueada'
    COMPLETADA = 'Completada'


class DailyLogState(str, Enum):
    ABIERTA = 'Abierta'
    CERRADA = 'Cerrada'


class NotificationType(str, Enum):
    ASIGNACION = 'asignacion'
    ALARMA_FECHA = 'alarma_fecha'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(30), nullable=False, default=UserRole.DESARROLLADOR.value)
    fecha_creacion = db.Column(db.DateTime, default=utc_now)

    # Relaciones
    tareas_creadas = db.relationship('Task', foreign_keys='Task.creador_id', backref='creador', lazy=True)
    tareas_asignadas = db.relationship('Task', foreign_keys='Task.responsable_id', backref='responsable', lazy=True)
    jornadas = db.relationship('DailyLog', backref='usuario', lazy=True, cascade="all, delete-orphan")
    notificaciones = db.relationship('Notification', backref='usuario', lazy=True, cascade="all, delete-orphan")
    auditorias = db.relationship('AuditLog', backref='usuario', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'email': self.email,
            'rol': self.rol
        }


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.String(50), nullable=False, default='Activo')
    fecha_creacion = db.Column(db.DateTime, default=utc_now)

    macrotareas = db.relationship('MacroTask', backref='proyecto', lazy=True, cascade="all, delete-orphan")


class MacroTask(db.Model):
    __tablename__ = 'macrotasks'

    id = db.Column(db.Integer, primary_key=True)
    proyecto_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    nombre = db.Column(db.String(150), nullable=False)
    estado = db.Column(db.String(50), nullable=False, default='Pendiente')

    tareas = db.relationship('Task', backref='macrotarea', lazy=True, cascade="all, delete-orphan")


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    macrotarea_id = db.Column(db.Integer, db.ForeignKey('macrotasks.id'), nullable=True)
    creador_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    responsable_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    porcentaje_avance = db.Column(db.Integer, nullable=False, default=0)
    estado = db.Column(db.String(50), nullable=False, default=TaskState.PENDIENTE.value)
    fecha_limite = db.Column(db.DateTime, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=utc_now)

    checklists = db.relationship('Checklist', backref='tarea', lazy=True, cascade="all, delete-orphan")
    auditorias = db.relationship('AuditLog', backref='tarea', lazy=True, cascade="all, delete-orphan")
    jornadas_asociadas = db.relationship('DailyLogTask', backref='tarea', lazy=True, cascade="all, delete-orphan")

    def recalcular_porcentaje(self):
        total = len(self.checklists)
        if total == 0:
            return self.porcentaje_avance
        completados = sum(1 for item in self.checklists if item.completado)
        nuevo_porcentaje = int((completados / total) * 100)
        self.porcentaje_avance = nuevo_porcentaje
        if nuevo_porcentaje == 100:
            self.estado = TaskState.COMPLETADA.value
        elif nuevo_porcentaje > 0 and self.estado == TaskState.PENDIENTE.value:
            self.estado = TaskState.EN_PROGRESO.value
        return nuevo_porcentaje


class TaskComment(db.Model):
    __tablename__ = 'task_comments'

    id = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comentario = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=utc_now)

    usuario = db.relationship('User', backref='comentarios_tareas', lazy=True)
    tarea = db.relationship('Task', backref=db.backref('comentarios', cascade='all, delete-orphan'), lazy=True)


class Checklist(db.Model):
    __tablename__ = 'checklists'

    id = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    descripcion = db.Column(db.String(255), nullable=False)
    completado = db.Column(db.Boolean, nullable=False, default=False)


class DailyLog(db.Model):
    __tablename__ = 'daily_logs'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=utc_now_date)
    estado = db.Column(db.String(30), nullable=False, default=DailyLogState.ABIERTA.value)
    comentario_cierre = db.Column(db.Text, nullable=True)

    registro_comercial = db.relationship('CommercialLog', backref='jornada', uselist=False, cascade="all, delete-orphan")
    tareas_dia = db.relationship('DailyLogTask', backref='jornada', lazy=True, cascade="all, delete-orphan")


class DailyLogTask(db.Model):
    __tablename__ = 'daily_log_tasks'

    id = db.Column(db.Integer, primary_key=True)
    jornada_id = db.Column(db.Integer, db.ForeignKey('daily_logs.id'), nullable=False)
    tarea_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    accion_resolucion = db.Column(db.String(50), nullable=True)  # reprogramar, backlog, cancelar
    porcentaje_al_cierre = db.Column(db.Integer, nullable=True)
    comentario = db.Column(db.Text, nullable=True)


class CommercialLog(db.Model):
    __tablename__ = 'commercial_logs'

    id = db.Column(db.Integer, primary_key=True)
    jornada_id = db.Column(db.Integer, db.ForeignKey('daily_logs.id'), unique=True, nullable=False)
    llamadas = db.Column(db.Integer, nullable=False, default=0)
    whatsapp = db.Column(db.Integer, nullable=False, default=0)
    linkedin = db.Column(db.Integer, nullable=False, default=0)
    correos = db.Column(db.Integer, nullable=False, default=0)
    ofertas_enviadas = db.Column(db.Integer, nullable=False, default=0)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mensaje = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(50), nullable=False, default=NotificationType.ASIGNACION.value)
    leida = db.Column(db.Boolean, nullable=False, default=False)
    fecha_creacion = db.Column(db.DateTime, default=utc_now)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    campo_modificado = db.Column(db.String(100), nullable=False)
    valor_anterior = db.Column(db.Text, nullable=True)
    valor_nuevo = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=utc_now)

