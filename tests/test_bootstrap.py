"""Safe new-checkout setup using an isolated database; no model/network imports."""
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from pydantic import ValidationError

from src.scripts import init_db
from src.api.models.db_models import User,FloodPrediction,AlertNotification,Zone
from src.api.utils.security import verify_password
from tests.test_staff_workflows import native_reports,password_hash


def test_bootstrap_uses_explicit_admin_is_idempotent_and_never_generates_predictions():
    engine=create_engine('sqlite://')
    kwargs=dict(name='Fixture admin',email='ADMIN@example.test',password='fixture-password-123')
    try:
        assert init_db.bootstrap(engine,**kwargs)==dict(zones_created=8,administrators_created=1,inference_performed=False)
        assert init_db.bootstrap(engine,**{**kwargs,'password':'another-fixture-password'})['administrators_created']==0
        with Session(engine) as db:
            assert db.query(User).count()==1 and db.query(Zone).count()==8
            admin=db.query(User).one()
            assert admin.email=='admin@example.test' and verify_password(kwargs['password'],admin.password_hash)
            assert db.query(FloodPrediction).count()==db.query(AlertNotification).count()==0
        with pytest.raises(ValueError,match='already exists'):
            init_db.bootstrap(engine,**{**kwargs,'email':'second@example.test'})
        with Session(engine) as db:assert db.query(User).count()==1
    finally:engine.dispose()


def test_invalid_password_rejected_before_schema_or_user_creation():
    engine=create_engine('sqlite://')
    try:
        with pytest.raises(ValidationError):
            init_db.bootstrap(engine,name='Fixture',email='fixture@example.test',password='short')
        assert inspect(engine).get_table_names()==[]
    finally:engine.dispose()


def test_cli_validation_never_echoes_private_password(monkeypatch,capsys):
    secret='s'*73
    monkeypatch.setenv('FLOODWATCH_BOOTSTRAP_PASSWORD',secret)
    with pytest.raises(SystemExit) as failure:init_db.main(['--admin-email','fixture@example.test'])
    assert failure.value.code==1
    assert secret not in capsys.readouterr().err


def test_cli_has_no_implicit_bootstrap_or_default_account(monkeypatch):
    monkeypatch.setattr(init_db,'bootstrap',lambda *a,**kw:pytest.fail('No implicit setup'))
    with pytest.raises(SystemExit) as failure:init_db.main([])
    assert failure.value.code==2


def test_native_bootstrap_preserves_existing_admin_and_original_zone(native_reports):
    engine,_=native_reports
    with Session(engine) as db:
        original=db.query(User).filter_by(role='admin').one().password_hash
    result=init_db.bootstrap(engine,name='Ignored existing name',email='admin@example.test',password='new-fixture-password')
    assert result['administrators_created']==0 and result['zones_created']==7
    with Session(engine) as db:
        assert db.query(User).filter_by(role='admin').one().password_hash==original
        assert db.get(Zone,'mathare').name=='Fixture Mathare'
