"""Reconcile supplier migrations with tables pre-created by db.create_all."""
import sqlalchemy as sa
from alembic import op


def _validate_columns(table, actual, expected):
    for column in expected:
        found = actual.get(column.name)
        if found is None:
            raise RuntimeError(f'{table}: colonna richiesta mancante: {column.name}')
        if not isinstance(found['type'], type(column.type)):
            raise RuntimeError(f'{table}.{column.name}: tipo incompatibile con la migrazione')
        expected_length = getattr(column.type, 'length', None)
        actual_length = getattr(found['type'], 'length', None)
        if expected_length and actual_length and actual_length < expected_length:
            raise RuntimeError(f'{table}.{column.name}: lunghezza insufficiente')
        if not column.primary_key and found['nullable'] != column.nullable:
            raise RuntimeError(f'{table}.{column.name}: nullabilita incompatibile')


def create_table_if_needed(name, *definitions, unique_keys=()):
    if op.get_context().as_sql:
        return op.create_table(name, *definitions)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        return op.create_table(name, *definitions)
    columns = [value for value in definitions if isinstance(value, sa.Column)]
    _validate_columns(name, {value['name']: value for value in inspector.get_columns(name)}, columns)
    if set(inspector.get_pk_constraint(name)['constrained_columns']) != {column.name for column in columns if column.primary_key}:
        raise RuntimeError(f'{name}: chiave primaria incompatibile')
    existing_uniques = {tuple(sorted(value['column_names'])) for value in inspector.get_unique_constraints(name)}
    existing_uniques.update(tuple(sorted(value['column_names'])) for value in inspector.get_indexes(name) if value['unique'])
    for key in unique_keys:
        if tuple(sorted(key)) not in existing_uniques:
            raise RuntimeError(f'{name}: vincolo univoco mancante per {key}')
    foreign_keys = inspector.get_foreign_keys(name)
    for column in columns:
        for foreign_key in column.foreign_keys:
            target_table, target_column = foreign_key.target_fullname.rsplit('.', 1)
            if not any(value['constrained_columns'] == [column.name] and value['referred_table'] == target_table
                       and value['referred_columns'] == [target_column]
                       and value.get('options', {}).get('ondelete') == foreign_key.ondelete for value in foreign_keys):
                raise RuntimeError(f'{name}.{column.name}: chiave esterna incompatibile')


def create_index_if_needed(name, table, columns):
    if not op.get_context().as_sql:
        for index in sa.inspect(op.get_bind()).get_indexes(table):
            if index['column_names'] == columns and not index['unique']:
                return
            if index['name'] == name:
                raise RuntimeError(f'{table}: indice {name} incompatibile')
    op.create_index(name, table, columns)


def add_column_if_needed(table, column):
    if not op.get_context().as_sql:
        columns = {value['name']: value for value in sa.inspect(op.get_bind()).get_columns(table)}
        if column.name in columns:
            _validate_columns(table, columns, [column])
            return
    op.add_column(table, column)
