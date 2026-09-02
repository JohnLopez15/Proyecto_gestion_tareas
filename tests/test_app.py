import pytest
from app import create_app, db
from app.models import (
    User, UserRole, Project, MacroTask, Task, Checklist,
    DailyLog, DailyLogState, AuditLog, Notification, TaskComment
)
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-key'


@pytest.fixture
def app():
    app = create_app(TestConfig)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_admin_creation_and_auth(app, client):
    with app.app_context():
        admin = User.query.filter_by(email='admin@empresa.com').first()
        assert admin is not None
        assert admin.rol == UserRole.ADMIN.value
        assert admin.check_password('admin123') is True

    # Test Login
    response = client.post('/login', data={
        'email': 'admin@empresa.com',
        'password': 'admin123'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Panel Principal' in response.data or b'TaskFlow' in response.data


def test_standalone_macrotask_and_checklist(app, client):
    with app.app_context():
        # Crear usuario dev
        dev = User(nombre='Dev User', email='dev@empresa.com', rol=UserRole.DESARROLLADOR.value)
        dev.set_password('dev123')
        db.session.add(dev)
        db.session.commit()

    client.post('/login', data={'email': 'dev@empresa.com', 'password': 'dev123'})

    # 1. Crear macrotarea independiente (sin proyecto) y vacía (sin tareas)
    res_mt = client.post('/macrotasks/create', data={
        'nombre': 'Macrotarea Independiente de Soporte',
        'proyecto_id': ''
    }, follow_redirects=True)
    assert res_mt.status_code == 200

    with app.app_context():
        mt = MacroTask.query.filter_by(nombre='Macrotarea Independiente de Soporte').first()
        assert mt is not None
        assert mt.proyecto_id is None
        assert len(mt.tareas) == 0  # No es obligatorio que tenga tareas

        # 2. Agregar tarea a la macrotarea independiente
        tarea = Task(
            macrotarea_id=mt.id,
            creador_id=User.query.filter_by(email='dev@empresa.com').first().id,
            responsable_id=User.query.filter_by(email='dev@empresa.com').first().id,
            titulo='Tarea en MT Independiente',
            porcentaje_avance=0
        )
        db.session.add(tarea)
        db.session.flush()

        item1 = Checklist(tarea_id=tarea.id, descripcion='Subtarea 1', completado=False)
        item2 = Checklist(tarea_id=tarea.id, descripcion='Subtarea 2', completado=False)
        db.session.add_all([item1, item2])
        db.session.commit()

        # Recálculo de checklist
        item1.completado = True
        nuevo_pct = tarea.recalcular_porcentaje()
        assert nuevo_pct == 50
        assert tarea.estado == 'En Progreso'


def test_daily_log_with_task_comments_and_imprevistas(app, client):
    with app.app_context():
        comercial = User(nombre='Comercial User', email='comercial@empresa.com', rol=UserRole.COMERCIAL.value)
        comercial.set_password('comercial123')
        db.session.add(comercial)
        db.session.commit()

        # Crear tarea asignada al comercial
        tarea = Task(
            creador_id=comercial.id,
            responsable_id=comercial.id,
            titulo='Llamadas a clientes VIP',
            porcentaje_avance=0
        )
        db.session.add(tarea)
        db.session.commit()
        tarea_id = tarea.id

    # Login como usuario comercial
    client.post('/login', data={'email': 'comercial@empresa.com', 'password': 'comercial123'})

    # Iniciar jornada con tarea seleccionada
    res_start = client.post('/daily/start', data={
        'task_ids': [tarea_id]
    }, follow_redirects=True)
    assert res_start.status_code == 200

    # Cerrar jornada: finalizar tarea al 100%, con comentario de tarea y agregando tarea imprevista al cierre
    res_close = client.post('/daily/close', data={
        f'completar_tarea_{tarea_id}': '1',
        f'comentario_tarea_{tarea_id}': 'Se contactaron 10 clientes con éxito y se cerró la negociación.',
        'titulo_imprevista_cierre': 'Reunión imprevista con Director',
        'completada_imprevista_cierre': '1',
        'comentario_imprevista_cierre': 'Reunión de 30 minutos acordada a última hora.',
        'llamadas': 10,
        'whatsapp': 15,
        'linkedin': 5,
        'correos': 8,
        'ofertas_enviadas': 3
    }, follow_redirects=True)
    assert res_close.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email='comercial@empresa.com').first()
        jornada = DailyLog.query.filter_by(usuario_id=user.id).first()
        assert jornada.estado == DailyLogState.CERRADA.value
        assert jornada.registro_comercial.llamadas == 10

        # Verificar que la tarea original quedó en 100% y tiene su comentario registrado
        t_orig = db.session.get(Task, tarea_id)
        assert t_orig.porcentaje_avance == 100
        assert t_orig.estado == 'Completada'

        comentarios = TaskComment.query.filter_by(tarea_id=tarea_id).all()
        assert len(comentarios) >= 1
        assert "Se contactaron 10 clientes" in comentarios[0].comentario
        assert comentarios[0].usuario_id == user.id

        # Verificar tarea imprevista creada al cierre
        t_imp = Task.query.filter(Task.titulo.like('%Reunión imprevista%')).first()
        assert t_imp is not None
        assert t_imp.porcentaje_avance == 100
        assert t_imp.estado == 'Completada'

    # Verificar visor de actividades diarias
    res_viewer = client.get('/daily/activity')
    assert res_viewer.status_code == 200
    assert b'Visor de Actividades Diarias' in res_viewer.data
    assert b'Llamadas a clientes VIP' in res_viewer.data
