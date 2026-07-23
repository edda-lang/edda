# tinysql

A small embedded SQL engine — open a file-backed database, run `CREATE TABLE` /
`INSERT` / `SELECT` / `UPDATE` / `DELETE` statements, and commit changes back to
disk. Tables live in memory as typed rows (`int` / `text` / `bool`); mutations
persist through a file rename, and reads open the store with a read-only filesystem.

## Install

```
edda add tinysql
```

Then import the module you need:

```edda
import tinysql.db
import tinysql.exec.exec
import tinysql.model.schema
import tinysql.model.error
```

## Usage

```edda
import tinysql.db

function seed(rfs: ReadOnlyFilesystem, fs: Filesystem, path: String, allocator: Allocator) -> usize
    with {rfs, fs, allocator, err: error.SqlError}
{
    var database = db.open(rfs, path, allocator)?
    db.execute_sql(mutable database, fs, path, "CREATE TABLE users (id int, name text)", allocator)?
    let result = db.execute_sql(mutable database, fs, path, "INSERT INTO users VALUES (1, 'ada')", allocator)?
    db.commit(database, fs, path, allocator)?
    return result.affected
}
```

`db.open` loads an existing store (or starts an empty database when the path does not
exist) from a `ReadOnlyFilesystem`. `db.execute_sql` parses and runs one statement
against the in-memory `Database`, auto-persisting mutating statements through the
`Filesystem`, and returns a `ResultSet` — its `columns: [String]`, `rows: [schema.Row]`,
and `affected: usize` fields carry query output and row counts. `db.commit` flushes the
current state to disk. Every entry point raises `error.SqlError` (parse errors, missing
tables, type mismatches, I/O and allocation failures) through the row.

## Public surface

- **`db`** — the top-level engine: `open` (load a database), `execute_sql` (run one statement), and `commit` (persist to disk).
- **`exec.exec`** — the `ResultSet` record and `execute`, which runs a parsed `Statement` against an open `Database`.
- **`model.schema`** — the `Database`, `Table`, `Column`, and `Row` storage types plus `new_database`, `table_index`, and `column_index`.
- **`model.value`** — the `Value` / `ColumnType` cell types and comparison helpers (`equals`, `compare`, `type_matches`).
- **`model.ast`** — parsed query shapes: `Statement`, `Projection`, `WhereClause`, `Conjunction`, `Comparison`, `CompareOp`, `Assignment`.
- **`model.error`** — the `SqlError` enum carried in every fallible row.
