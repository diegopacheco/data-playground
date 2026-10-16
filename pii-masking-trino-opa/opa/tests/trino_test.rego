package trino_test

import data.trino

customers := {"catalogName": "postgres", "schemaName": "public", "tableName": "customers"}

orders := {"catalogName": "postgres", "schemaName": "public", "tableName": "orders"}

scratch_copy := {"catalogName": "scratch", "schemaName": "default", "tableName": "copy_bruno"}

context(user) := {"identity": {"user": user, "groups": []}, "softwareStack": {"trinoVersion": "483"}}

table_request(user, operation, table) := {"context": context(user), "action": {"operation": operation, "resource": {"table": table}}}

select_request(user, columns) := table_request(user, "SelectFromColumns", object.union(customers, {"columns": columns}))

column(name, type) := {"column": object.union(customers, {"columnName": name, "columnType": type})}

mask_request(user) := {"context": context(user), "action": {"operation": "GetColumnMask", "filterResources": [
	column("customer_id", "integer"),
	column("email", "varchar"),
	column("national_id", "varchar"),
	column("phone", "varchar"),
	column("credit_card", "varchar"),
	column("balance", "decimal(10,2)"),
]}}

single_mask_request(user, name) := {"context": context(user), "action": {"operation": "GetColumnMask", "resource": column(name, "varchar")}}

pii_masks := {
	{"index": 1, "viewExpression": {"expression": "regexp_replace(email, '^[^@]+', '****')"}},
	{"index": 2, "viewExpression": {"expression": "lpad(substr(national_id, -4), length(national_id), '*')"}},
	{"index": 3, "viewExpression": {"expression": "CAST(NULL AS varchar)"}},
	{"index": 4, "viewExpression": {"expression": "lpad(substr(credit_card, -4), length(credit_card), '*')"}},
}

test_unknown_user_cannot_even_execute_a_query if {
	not trino.allow with input as {"context": context("mallory"), "action": {"operation": "ExecuteQuery"}}
}

test_unknown_user_cannot_select_any_column if {
	not trino.allow with input as select_request("mallory", ["customer_id"])
}

test_admin_selects_every_pii_column if {
	trino.allow with input as select_request("alice", ["email", "national_id", "phone", "credit_card", "balance"])
}

test_admin_gets_no_mask_and_no_row_filter if {
	count(trino.batchColumnMasks) == 0 with input as mask_request("alice")
	count(trino.rowFilters) == 0 with input as table_request("alice", "GetRowFilters", customers)
}

test_analyst_gets_email_last4_and_null_masks_by_index if {
	trino.batchColumnMasks == pii_masks with input as mask_request("bruno")
}

test_analyst_single_column_mask_matches_batch if {
	trino.columnMask == {"expression": "lpad(substr(credit_card, -4), length(credit_card), '*')"} with input as single_mask_request("bruno", "credit_card")
}

test_analyst_unmasked_column_has_no_single_mask if {
	not trino.columnMask with input as single_mask_request("bruno", "country")
}

test_analyst_sees_every_country if {
	count(trino.rowFilters) == 0 with input as table_request("bruno", "GetRowFilters", customers)
}

test_regional_analyst_is_masked_like_the_analyst if {
	trino.batchColumnMasks == pii_masks with input as mask_request("rita")
}

test_regional_analyst_is_filtered_to_own_country_on_both_tables if {
	trino.rowFilters == {{"expression": "country = 'BR'"}} with input as table_request("rita", "GetRowFilters", customers)
	trino.rowFilters == {{"expression": "country = 'BR'"}} with input as table_request("rita", "GetRowFilters", orders)
}

test_row_filter_follows_the_country_in_the_data_document if {
	trino.rowFilters == {{"expression": "country = 'JP'"}} with input as table_request("rita", "GetRowFilters", customers)
		with data.pii.users.rita.country as "JP"
}

test_support_selects_contact_columns if {
	trino.allow with input as select_request("sam", ["customer_id", "name", "email", "phone", "country"])
}

test_support_is_denied_when_one_hidden_column_is_selected if {
	not trino.allow with input as select_request("sam", ["customer_id", "national_id"])
	not trino.allow with input as select_request("sam", ["credit_card"])
	not trino.allow with input as select_request("sam", ["balance"])
}

test_support_hidden_columns_are_filtered_out_of_select_star if {
	not trino.allow with input as table_request("sam", "FilterColumns", object.union(customers, {"columns": ["national_id"]}))
	trino.allow with input as table_request("sam", "FilterColumns", object.union(customers, {"columns": ["email"]}))
}

test_support_gets_contact_columns_unmasked if {
	count(trino.batchColumnMasks) == 0 with input as mask_request("sam")
}

test_support_has_no_scratch_catalog if {
	not trino.allow with input as {"context": context("sam"), "action": {"operation": "AccessCatalog", "resource": {"catalog": {"name": "scratch"}}}}
	trino.allow with input as {"context": context("sam"), "action": {"operation": "AccessCatalog", "resource": {"catalog": {"name": "postgres"}}}}
}

test_analyst_writes_only_in_scratch if {
	trino.allow with input as table_request("bruno", "CreateTable", scratch_copy)
	trino.allow with input as table_request("bruno", "DropTable", scratch_copy)
	not trino.allow with input as table_request("bruno", "CreateTable", customers)
	not trino.allow with input as table_request("bruno", "DropTable", customers)
	not trino.allow with input as table_request("bruno", "InsertIntoTable", customers)
}

test_analyst_cannot_create_views if {
	not trino.allow with input as table_request("bruno", "CreateView", scratch_copy)
}

test_changing_the_mask_kind_in_data_changes_the_expression if {
	trino.columnMask == {"expression": "CAST(NULL AS varchar)"} with input as single_mask_request("bruno", "email")
		with data.pii.roles.analyst.masks["postgres.public.customers"].email as "null"
}
