"""Offline, insert-only transfer into an empty, explicitly migrated application DB."""
import hashlib
import json
from uuid import UUID
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb, set_json_loads

TABLES = ('studio_sources', 'studio_code_snapshots', 'studio_source_publications',
          'studio_projects', 'studio_revisions', 'studio_jobs', 'studio_proposals',
          'studio_messages', 'studio_reviews', 'studio_review_agents', 'studio_source_assignments')
OWNED = ('studio_sources', 'studio_projects')


def rows(c, table):
    # Keep JSON null distinct from SQL NULL, and PostgreSQL arrays as arrays.
    with c.cursor() as cursor:
        set_json_loads(lambda value: bytes(value).decode(), cursor)
        return cursor.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchall()


def digest(records):
    normalized = sorted(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False) for row in records)
    return hashlib.sha256('\n'.join(normalized).encode()).hexdigest()


def transfer(source_url, target_url, transfer_id, *, apply=False):
    transfer_id = UUID(str(transfer_id))
    if source_url == target_url:
        raise ValueError('원본과 대상 DB가 같습니다.')
    with psycopg.connect(source_url, row_factory=dict_row) as source, psycopg.connect(target_url, row_factory=dict_row) as target:
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        origin = source.execute("SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port").fetchone()
        destination = target.execute("SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port").fetchone()
        if origin == destination:
            raise ValueError('원본과 대상 DB가 같습니다.')
        target.execute('SELECT pg_advisory_xact_lock(247317)')
        for table in ('studio_jobs', 'studio_reviews', 'studio_code_snapshots'):
            if source.execute(sql.SQL("SELECT 1 FROM {} WHERE status IN ('queued','running') LIMIT 1").format(sql.Identifier(table))).fetchone():
                raise ValueError('진행 중인 작업을 마친 뒤 쓰기와 Worker를 중지해 주세요.')
        if source.execute('SELECT 1 FROM studio_sources GROUP BY kind,repository,ref HAVING count(*)>1 LIMIT 1').fetchone():
            raise ValueError('admin 소유권 통합 시 중복되는 저장소가 있습니다. 이전 전에 정리해 주세요.')
        data = {table: rows(source, table) for table in TABLES}
        manifest = {'tables': {table: {'count': len(records), 'hash': digest(records)} for table, records in data.items()},
                    'owners': sorted({row['owner_id'] for table in OWNED for row in data[table]}),
                    'ownership_target': 'demo-user', 'removed_assignments': len(data['studio_source_assignments'])}
        old = target.execute('SELECT manifest FROM studio_data_transfers WHERE id=%s', (transfer_id,)).fetchone()
        if old:
            if old['manifest'] != manifest:
                raise ValueError('같은 이전 ID에 다른 원본 데이터가 지정되었습니다.')
            return {**manifest, 'already_applied': True, 'verified': True}
        for table in TABLES:
            if target.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(table))).fetchone():
                raise ValueError('대상 앱 테이블이 비어 있지 않습니다. 기존 데이터를 덮어쓰지 않습니다.')
        if not apply:
            return {**manifest, 'dry_run': True}
        target.execute('SET CONSTRAINTS ALL DEFERRED')
        for table, records in data.items():
            if table == 'studio_source_assignments' or not records:
                continue
            columns = list(records[0])
            json_columns = {row['column_name'] for row in source.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND data_type IN ('json','jsonb')", (table,)).fetchall()}
            statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),
                sql.SQL(',').join(map(sql.Identifier, columns)), sql.SQL(',').join(sql.Placeholder() for _ in columns))
            for row in records:
                row = dict(row)
                if table in OWNED:
                    row['owner_id'] = 'demo-user'
                target.execute(statement, [Jsonb(json.loads(value)) if name in json_columns and value is not None else value for name, value in row.items()])
        # Publications and revisions are copied byte-for-byte as historic evidence;
        # their original owner fields are provenance, not current access grants.
        for table in TABLES:
            expected = [] if table == 'studio_source_assignments' else [dict(row, owner_id='demo-user') if table in OWNED else row for row in data[table]]
            if digest(rows(target, table)) != digest(expected):
                raise ValueError('이전 결과가 원본과 일치하지 않습니다. 전체 이전을 취소합니다.')
        for table in TABLES:
            for column in source.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND (column_default LIKE 'nextval(%%' OR is_identity='YES')", (table,)).fetchall():
                name = column['column_name']
                sequence = target.execute('SELECT pg_get_serial_sequence(%s,%s) AS name', (table, name)).fetchone()['name']
                if sequence:
                    maximum = target.execute(sql.SQL('SELECT max({}) AS n FROM {}').format(sql.Identifier(name), sql.Identifier(table))).fetchone()['n']
                    if maximum is not None:
                        target.execute('SELECT setval(%s,%s,true)', (sequence, maximum))
        target.execute('INSERT INTO studio_data_transfers(id,manifest) VALUES (%s,%s)', (transfer_id, Jsonb(manifest)))
        target.execute('SET CONSTRAINTS ALL IMMEDIATE')
        return {**manifest, 'verified': True}
