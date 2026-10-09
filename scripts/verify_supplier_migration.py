"""Verify upgrade and downgrade using a disposable copy of a pre-migration database."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from flask_migrate import upgrade, downgrade
from app import create_app, db

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('database', type=Path)
parser.add_argument('--temporary-directory', type=Path, default=Path('instance'))
args = parser.parse_args()
source = args.database.resolve()
with TemporaryDirectory(prefix='tdm-migration-', dir=args.temporary_directory.resolve()) as temporary:
    target = Path(temporary) / 'migration-test.db'
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        with closing(sqlite3.connect(target)) as copy:
            original.backup(copy)
            assert copy.execute('SELECT version_num FROM alembic_version').fetchone()[0] == 'c4f1a8d9e221', 'Use a pre-migration database at c4f1a8d9e221'
            tables = [row[0] for row in copy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before = {table: copy.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables if table != 'alembic_version'}
    app = create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{target.as_posix()}'})
    with app.app_context():
        upgrade(revision='d8e2b6a41001')
        with closing(sqlite3.connect(target)) as copy:
            for table, rows in before.items():
                result = copy.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                if table == 'supplier_order_costs':
                    result = [row[:-1] for row in result]
                assert result == rows, table
            assert copy.execute('PRAGMA foreign_key_check').fetchall() == []
            assert copy.execute('SELECT version_num FROM alembic_version').fetchone()[0] == 'd8e2b6a41001'
        print('Upgrade passed; all pre-existing rows preserved; foreign keys valid.')
        downgrade(revision='c4f1a8d9e221')
        with closing(sqlite3.connect(target)) as copy:
            for table, rows in before.items():
                assert copy.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() == rows, table
        print('Downgrade passed on disposable copy; original database never opened for writing.')
        db.session.remove()
        db.engine.dispose()
