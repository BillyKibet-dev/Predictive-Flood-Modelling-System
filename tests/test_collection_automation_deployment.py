"""Static checks for the deliberately inert, collection-only Linux deployment path."""
from pathlib import Path

from src.api.config import settings
from src.scripts import run_point_collection as runner


ROOT=Path(__file__).resolve().parents[1]


def test_collection_timer_and_service_are_explicitly_collection_only():
    timer=(ROOT/'deploy/examples/monitoring-point-weather.timer').read_text(encoding='utf-8')
    service=(ROOT/'deploy/examples/monitoring-point-weather.service').read_text(encoding='utf-8')
    environment=(ROOT/'deploy/examples/application.env.example').read_text(encoding='utf-8')
    assert 'OnCalendar=*-*-* *:05:00 UTC' in timer
    assert 'Persistent=false' in timer and 'RandomizedDelaySec=0' in timer
    assert 'run_point_collection --execute --automated --require-synced-clock' in service
    assert 'Restart=no' in service and 'ReadWritePaths=/var/lib/nairobifloodwatch/point_weather' in service
    assert 'MONITORING_POINT_COLLECTION_AUTOMATED=true' in environment
    assert 'MONITORING_POINT_COLLECTION_INTERVAL_HOURS=1' in environment


def test_automated_runner_requires_private_gate_and_exact_timer_interval(monkeypatch,capsys):
    monkeypatch.setattr(settings,'MONITORING_POINT_COLLECTION_AUTOMATED',False)
    assert runner.main(['--execute','--automated','--require-synced-clock'])==2
    assert 'AUTOMATED_COLLECTION_NOT_ENABLED' in capsys.readouterr().out
    monkeypatch.setattr(settings,'MONITORING_POINT_COLLECTION_AUTOMATED',True)
    monkeypatch.setattr(settings,'MONITORING_POINT_COLLECTION_INTERVAL_HOURS',5)
    assert runner.main(['--execute','--automated','--require-synced-clock'])==2
    assert 'AUTOMATED_TIMER_INTERVAL_MISMATCH' in capsys.readouterr().out


def test_cors_accepts_several_frontend_origins_and_drops_localhost_in_production():
    from src.api.config import allowed_origins
    origins = allowed_origins('https://floodwatch.example, https://www.floodwatch.example/ ,https://x.netlify.app', 'production')
    assert origins == ['https://floodwatch.example', 'https://www.floodwatch.example', 'https://x.netlify.app']
    assert 'http://localhost:5173' in allowed_origins('https://floodwatch.example', 'development')


def test_api_unit_can_write_every_runtime_store():
    service = (ROOT/'deploy/examples/nairobifloodwatch-api.service').read_text(encoding='utf-8')
    environment = (ROOT/'deploy/examples/application.env.example').read_text(encoding='utf-8')
    for store in ('operational_sources', 'point_weather', 'imerg_early', 'report_photos'):
        assert f'/var/lib/nairobifloodwatch/{store}' in service.split('ReadWritePaths=')[1].splitlines()[0]
        assert f'/var/lib/nairobifloodwatch/{store}' in environment
