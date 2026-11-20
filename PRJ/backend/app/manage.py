"""Explicit deployment commands. Never accepts credentials as command arguments."""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
import psycopg
from psycopg import sql
from .config import settings
from .db import initialize


def password(path=None):
    value = Path(path).read_text().removesuffix('\n') if path else getpass('초기 비밀번호: ')
    if not 10 <= len(value) <= 128:
        raise ValueError('비밀번호는 10~128자로 지정해 주세요.')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate')
    bootstrap = commands.add_parser('bootstrap-admin')
    bootstrap.add_argument('--password-file')
    runtime = commands.add_parser('runtime-role')
    runtime.add_argument('--name', default='hplanit_app')
    runtime.add_argument('--password-file')
    reset = commands.add_parser('recover-admin')
    reset.add_argument('--password-file')
    transfer = commands.add_parser('transfer')
    transfer.add_argument('--transfer-id', required=True, type=UUID)
    transfer.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = settings()
    migration_url = config.migration_database_url or config.database_url
    if args.command == 'migrate':
        initialize(migration_url)
        print('Schema migrations applied.')
    elif args.command == 'runtime-role':
        if not args.name.isascii() or not args.name.replace('_', '').isalnum() or args.name in {'postgres', 'studio_runtime', 'anon', 'authenticated'}:
            raise ValueError('전용 런타임 역할 이름을 지정해 주세요.')
        secret = password(args.password_file)
        with psycopg.connect(migration_url) as c:
            if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (args.name,)).fetchone():
                raise ValueError('이미 존재하는 역할입니다. 기존 비밀번호를 변경하지 않습니다.')
            c.execute(sql.SQL('CREATE ROLE {} LOGIN INHERIT PASSWORD {}').format(sql.Identifier(args.name), sql.Literal(secret)))
            c.execute(sql.SQL('GRANT studio_runtime TO {}').format(sql.Identifier(args.name)))
        print('Runtime role created. Configure DATABASE_URL with this login; retain MIGRATION_DATABASE_URL separately.')
    elif args.command in {'bootstrap-admin', 'recover-admin'}:
        from .accounts import AccountInput, Reset, provision
        if config.auth_mode != 'supabase':
            raise ValueError('AUTH_MODE=supabase가 필요합니다.')
        secret = password(args.password_file)
        if args.command == 'bootstrap-admin':
            op = uuid5(NAMESPACE_URL, 'hplanit:bootstrap-admin')
            result = provision(AccountInput(operation_id=op, loginId='admin', name='IT 관리자', role='ADMINISTRATOR', password=secret), 'bootstrap', bootstrap=True)
        else:
            # Operator-only recovery for a failed self-reset. Uses migration credentials,
            # never exposes a public API bypass, and leaves an audit trail.
            with psycopg.connect(migration_url) as c:
                row = c.execute("SELECT id FROM studio_accounts WHERE login_id='admin' AND role='ADMINISTRATOR'").fetchone()
                if not row:
                    raise ValueError('초기 관리자 계정이 없습니다.')
                c.execute("UPDATE studio_accounts SET active=true,provisioning_status='ready' WHERE id=%s", (row[0],))
            result = provision(Reset(operation_id=uuid5(NAMESPACE_URL, 'hplanit:recover-admin:' + os.urandom(16).hex()), password=secret), 'operator', account_id=row[0], bootstrap=True)
        print(json.dumps({'id': result['id'], 'loginId': result['loginId'], 'active': result['active']}))
    else:
        from .transfer import transfer
        source = os.environ.get('SOURCE_DATABASE_URL', '')
        if not source:
            raise ValueError('SOURCE_DATABASE_URL을 비밀 환경 파일에 설정해 주세요.')
        result = transfer(source, migration_url, args.transfer_id, apply=args.apply)
        # Full manifest stays in the target DB; console output excludes original owners/data.
        print(json.dumps({'tables': {k: v['count'] for k, v in result['tables'].items()},
                          **{k: result[k] for k in ('dry_run', 'verified', 'already_applied') if k in result}}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Driver/provider exceptions may contain connection strings or sensitive inputs.
        print('작업을 완료하지 못했습니다. 연결·권한·진행 중 작업·대상 데이터와 명령 전제를 확인해 주세요.')
        raise SystemExit(1) from None
