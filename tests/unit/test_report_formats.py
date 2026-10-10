import base64
import csv
import struct
import zlib
from dataclasses import replace
from html import escape

import pytest
from click.testing import CliRunner
from openpyxl import load_workbook

from asm.cli import main
from asm.conf import load_config
from asm.db import Database
from asm.models import Asset
from asm.pipeline import run_pipeline
from asm.stages.s8_report import HEADERS, report_paths, write_report


def png_bytes():
    def chunk(kind, content):
        return (struct.pack('>I', len(content)) + kind + content
                + struct.pack('>I', zlib.crc32(kind + content)))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x12\x34\x56')) + chunk(b'IEND', b''))


def attach_screenshot(db, asset, source, suffix=''):
    table, asset_id = asset
    assert table == 'assets'
    host = db.rows('SELECT host FROM assets WHERE id=?', (asset_id,))[0]['host']
    db.upsert('urls', {'url': f'https://{host}/{suffix}', 'asset_id': asset_id,
                      'title': '截图', 'screenshot': str(source)}, ('url',))


def test_csv_eight_table_contract_matches_workbook(db, tmp_path):
    title = '中文门户，含逗号, "引号"\n第二行'
    db.asset(Asset(host='portal.example.invalid', title=title, source='fixture'))
    db.asset(Asset(host='excluded.example.invalid', confidence='D', source='fuzzy'))
    counts = write_report(db, tmp_path / 'report.xlsx')
    paths = report_paths(tmp_path / 'report.xlsx')
    book = load_workbook(paths['xlsx'])
    assert len(list(paths['csv_dir'].glob('*.csv'))) == 7
    for name, headers in HEADERS.items():
        path = paths['csv'] if name == '总表' else paths['csv_dir'] / f'{name}.csv'
        assert path.read_bytes().startswith(b'\xef\xbb\xbf')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
        assert rows[0] == headers
        assert len(rows) - 1 == counts[name]
        assert rows == [[str(v) if v is not None else '' for v in row] for row in book[name].values]
    book.close()
    with paths['csv'].open(encoding='utf-8-sig', newline='') as stream:
        assert title in list(csv.reader(stream))[1]
    html = paths['html'].read_text(encoding='utf-8')
    assert 'excluded.example.invalid' not in html
    assert html.count('data-sheet=') == 8


@pytest.mark.parametrize('title', ['=1+1', '\t=1+1', '  @SUM(1,2)', '\r\n+1', '-1+2'])
def test_csv_formula_prefixes_are_neutralized_without_losing_text(db, tmp_path, title):
    db.asset(Asset(host='portal.example.invalid', title=title))
    write_report(db, tmp_path / 'report.csv')
    with (tmp_path / 'report.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert rows[1][3] == "'" + title


def test_html_embeds_screenshot_once_and_escapes_untrusted_fields(db, tmp_path):
    hostile = '</script><script>window.pwned=true</script><img src=x onerror=alert(1)>'
    source = tmp_path / 'captured.png'
    source.write_bytes(png_bytes())
    first = db.asset(Asset(host='a.example.invalid', title=hostile, source='fixture'))
    attach_screenshot(db, first, source)
    attach_screenshot(db, first, source, 'other')
    second = db.asset(Asset(host='b.example.invalid'))
    attach_screenshot(db, second, tmp_path / 'missing.png')
    third = db.asset(Asset(host='c.example.invalid'))
    corrupt = tmp_path / 'corrupt.png'
    corrupt.write_text('NOT A PNG: do not embed this', encoding='utf-8')
    attach_screenshot(db, third, corrupt)
    write_report(db, tmp_path / 'report.html')
    html = (tmp_path / 'report.html').read_text(encoding='utf-8')
    assert hostile not in html and escape(hostile, quote=True) in html
    assert html.count('<script>') == 1
    assert html.count('data:image/png;base64,') == 1
    assert base64.b64encode(source.read_bytes()).decode() in html
    assert 'href="#screenshot-1"' in html
    assert '截图文件缺失或无法复制' in html
    assert '截图文件无法作为 PNG 显示' in html
    assert 'NOT A PNG' not in html
    assert "connect-src &#x27;none&#x27;" in html


def test_unreadable_screenshot_does_not_abort_any_report(db, tmp_path, monkeypatch):
    source = tmp_path / 'captured.png'
    source.write_bytes(png_bytes())
    asset = db.asset(Asset(host='a.example.invalid'))
    attach_screenshot(db, asset, source)

    def fail_copy(*_):
        raise PermissionError('fixture')
    monkeypatch.setattr('asm.stages.s8_report.shutil.copyfile', fail_copy)
    output = tmp_path / 'delivery/report.xlsx'
    assert write_report(db, output)['总表'] == 1
    assert all(path.exists() for path in report_paths(output).values())
    assert '截图文件缺失或无法复制' in output.with_suffix('.html').read_text(encoding='utf-8')


def test_empty_report_has_headers_and_explicit_screenshot_state(db, tmp_path):
    assert set(write_report(db, tmp_path / 'report.xlsx').values()) == {0}
    with (tmp_path / 'report.csv').open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.reader(stream)) == [HEADERS['总表']]
    assert '本报告未采集首页截图' in (tmp_path / 'report.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('suffix', ['xlsx', 'csv', 'html'])
def test_cli_export_suffix_selects_bundle_name(project, tmp_path, monkeypatch, suffix):
    config = replace(load_config('demo', project), root=tmp_path)
    with Database(config.output / 'asm.db') as database:
        database.asset(Asset(host='a.example.invalid'))
    monkeypatch.setattr('asm.cli.load_config', lambda *_: config)
    output = tmp_path / f'custom.{suffix}'
    result = CliRunner().invoke(main, ['report', '--profile', 'demo', '--output', str(output)])
    assert result.exit_code == 0, result.output
    assert 'xlsx:' in result.output and 'csv:' in result.output and 'html:' in result.output
    assert all(path.exists() for path in report_paths(output).values())
    bad = CliRunner().invoke(main, ['report', '--output', str(tmp_path / 'bad.pdf')])
    assert bad.exit_code == 1 and 'must end in' in bad.output
    assert not (tmp_path / 'bad.pdf').exists()


def test_default_pipeline_reports_supply_branch_results(project, tmp_path, monkeypatch):
    config = replace(load_config('demo', project), data={**load_config('demo', project).data,
                                                     'supply_chain': {'vendor_list': ['FIXTURE_VENDOR']}})
    config = replace(config, data={**config.data, 'output': {'dir': str(tmp_path)}})
    monkeypatch.setattr('asm.pipeline.load_config', lambda *_: config)
    result = run_pipeline(dry_run=True, passive_only=True)
    assert list(result)[-1] == '8'
    assert result['8']['status'] == 'completed'
    with (config.output / 'dry-run/report-csv/todos.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert any(row['type'] == 'supply_research' and row['target'] == 'FIXTURE_VENDOR' for row in rows)
