package trino

import data.pii

default allow := false

user := pii.users[input.context.identity.user]

role := pii.roles[user.role]

operation := input.action.operation

resource := input.action.resource

session_operations := {"ExecuteQuery"}

catalog_operations := {"AccessCatalog", "FilterCatalogs", "ShowSchemas"}

schema_operations := {"FilterSchemas", "ShowTables"}

read_operations := {"FilterTables", "FilterColumns", "ShowColumns", "SelectFromColumns"}

write_operations := {"CreateTable", "InsertIntoTable", "DropTable"}

schema_key(r) := sprintf("%s.%s", [r.catalogName, r.schemaName])

table_key(r) := sprintf("%s.%s.%s", [r.catalogName, r.schemaName, r.tableName])

readable_catalogs contains catalog if {
	some schema in role.read
	catalog := split(schema, ".")[0]
}

hidden_columns(table) := object.get(role, ["hidden_columns", table_key(table)], [])

touches_hidden(table) if {
	some column in object.get(table, "columns", [])
	column in hidden_columns(table)
}

allow if role.unrestricted

allow if {
	role
	operation in session_operations
}

allow if {
	operation in catalog_operations
	resource.catalog.name in readable_catalogs
}

allow if {
	operation in schema_operations
	schema_key(resource.schema) in role.read
}

allow if {
	operation in read_operations
	schema_key(resource.table) in role.read
	not touches_hidden(resource.table)
}

allow if {
	operation in read_operations
	resource.table.schemaName == "information_schema"
	resource.table.catalogName in readable_catalogs
}

allow if {
	operation in write_operations
	schema_key(resource.table) in role.write
}

rowFilters contains {"expression": expression} if {
	column := role.row_filter[table_key(resource.table)]
	expression := sprintf("%s = '%s'", [column, user.country])
}

render("email", column) := sprintf("regexp_replace(%s, '^[^@]+', '****')", [column.columnName])

render("last4", column) := sprintf("lpad(substr(%s, -4), length(%s), '*')", [column.columnName, column.columnName])

render("null", column) := sprintf("CAST(NULL AS %s)", [column.columnType])

mask(column) := render(role.masks[table_key(column)][column.columnName], column)

columnMask := {"expression": mask(resource.column)}

batchColumnMasks contains {"index": index, "viewExpression": {"expression": expression}} if {
	some index, entry in input.action.filterResources
	expression := mask(entry.column)
}
