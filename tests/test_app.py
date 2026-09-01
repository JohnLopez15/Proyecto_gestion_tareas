import pytest
from app import create_app, db
from app.models import User, UserRole, Project, MacroTask, Task, Checklist, DailyLog, DailyLogState, AuditLog, Notification
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


def test_checklist_recalculation_and_audit(app, client):
    with app.app_context():
        # Crear usuario dev
        dev = User(nombre='Dev User', email='dev@empresa.com', rol=UserRole.DESARROLLADOR.value)
        dev.set_password('dev123')
        db.session.add(dev)

        # Crear Proyecto -> Macrotarea -> Tarea
        proyecto = Project(nombre='Proyecto Test')
        db.session.add(proyecto)
        db.session.flush()

        macrotarea = MacroTask(proyecto_id=proyecto.id, nombre='Macrotarea Test')
        db.session.add(macrotarea)
        db.session.flush()

        tarea = Task(
            macrotarea_id=macrotarea.id,
            creador_id=dev.id,
            responsable_id=dev.id,
            titulo='Tarea Test Checklist',
            porcentaje_avance=0
        )
        db.session.add(tarea)
        db.session.flush()

        item1 = Checklist(tarea_id=tarea.id, descripcion='Subtarea 1', completado=False)
        item2 = Checklist(tarea_id=tarea.id, descripcion='Subtarea 2', completado=False)
        db.session.add_all([item1, item2])
        db.session.commit()

        # Marcar item1 como completado
        item1.completado = True
        nuevo_pct = tarea.recalcular_porcentaje()
        assert nuevo_pct == 50
        assert tarea.estado == 'En Progreso'

        # Marcar item2 como completado
        item2.completado = True
        nuevo_pct = tarea.recalcular_porcentaje()
        assert nuevo_pct == 100
        assert tarea.estado == 'Completada'


def test_daily_log_flow(app, client):
    with app.app_context():
        comercial = User(nombre='Comercial User', email='comercial@empresa.com', rol=UserRole.COMERCIAL.value)
        comercial.set_password('comercial123')
        db.session.add(comercial)
        db.session.commit()

    # Login como usuario comercial
    client.post('/login', data={'email': 'comercial@empresa.com', 'password': 'comercial123'})

    # Iniciar jornada
    res_start = client.post('/daily/start', data={}, follow_redirects=True)
    assert res_start.status_code == 200

    # Verificar que la jornada está abierta
    with app.app_context():
        user = User.query.filter_by(email='comercial@empresa.com').first()
        jornada = DailyLog.query.filter_by(usuario_id=user.id).first()
        assert jornada is not None
        assert jornada.estado == DailyLogState.ABIERTA.value

    # Cerrar jornada con comercial log
    res_close = client.post('/daily/close', data={
        'comentario_cierre': 'Día productivo en ventas',
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
        assert jornada.registro_comercial is not None
        assert jornada.registro_comercial.llamadas == 10
        assert jornada.registro_comercial.ofertas_enviadas == 3

