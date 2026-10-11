package com.github.diegopacheco.paimonflink;

import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.types.Row;
import org.apache.flink.util.CloseableIterator;

import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;

public final class SqlConsole {

    public static void main(String[] args) throws Exception {
        TableEnvironment env = Lakehouse.batch();
        for (String sql : args) {
            query(env, sql).forEach(row -> System.out.println(csv(row)));
        }
        System.exit(0);
    }

    public static List<Row> query(TableEnvironment env, String sql) throws Exception {
        List<Row> rows = new ArrayList<>();
        try (CloseableIterator<Row> it = env.executeSql(sql).collect()) {
            it.forEachRemaining(rows::add);
        }
        return rows;
    }

    private static String csv(Row row) {
        StringJoiner line = new StringJoiner(",");
        for (int i = 0; i < row.getArity(); i++) {
            line.add(String.valueOf(row.getField(i)));
        }
        return line.toString();
    }
}
